"""Deterministic controls. A failed coverage gate prevents amount certification."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext

from .contracts import DIMENSIONS, Manifest, Policy, Row, canonical, decimal_text, digest, money, total

RULE_VERSION = "2026.11.2"


def mapped(row: Row, policy: Policy, side: str) -> tuple[dict, Decimal | None]:
    pov = row.pov.model_dump()
    amount = money(row.amount) if row.amount is not None else None
    if side == "GL":
        account = pov["account"]
        if account not in policy.account_map or account not in policy.sign_map:
            raise ValueError(f"Unapproved account mapping for {account}")
        pov["account"] = policy.account_map[account]
        if amount is not None:
            with localcontext() as context:
                context.prec = 100
                amount *= money(policy.sign_map[account])
    return pov, amount


def lineage(batch_id, manifest, row):
    return {"batch_id": batch_id, "sha256": manifest.sha256, "line": row.line, "record_id": row.record_id}


def result(rule, status, explanation, pov=None, expected=None, actual=None, refs=None, parameters=None):
    with localcontext() as context:
        context.prec = 100
        delta = expected - actual if expected is not None and actual is not None else None
    item = {
        "rule": rule, "rule_version": RULE_VERSION, "status": status, "explanation": explanation,
        "pov": pov or {}, "expected": decimal_text(expected) if expected is not None else None,
        "actual": decimal_text(actual) if actual is not None else None,
        "variance": decimal_text(delta) if delta is not None else None,
        "lineage": refs or [], "parameters": parameters or {},
    }
    item["fingerprint"] = digest(item)
    return item


def coverage(batch_id: str, manifest: Manifest, rows: list[Row], policy: Policy, raw: bytes,
             approved: bool, now: datetime) -> list[dict]:
    failures = []

    def block(message, row=None):
        failures.append(result("C01 Coverage", "BLOCKED", message,
                               row.pov.model_dump() if row else None,
                               refs=[lineage(batch_id, manifest, row)] if row else [],
                               parameters={"batch_id": batch_id, "sha256": manifest.sha256}))

    if not approved or manifest.policy_id != policy.id:
        block("Mapping and precision policy requires independent approval")
    if digest(raw) != manifest.sha256 or len(raw) != manifest.byte_count:
        block("Original artifact hash or byte count differs from its source manifest")
    if len(rows) != manifest.row_count or not rows:
        block("Source row count differs or the extraction universe is empty")
    if not manifest.complete or not manifest.precision_verified:
        block("Source completeness or stored precision has not been attested")
    extracted = datetime.fromisoformat(manifest.extracted_at.replace("Z", "+00:00"))
    age = (now - extracted).total_seconds()
    if age < -300 or age > policy.maximum_age_seconds:
        block("Evidence timestamp is future-dated or exceeds the approved freshness window")
    if not policy.effective_from <= extracted.date().isoformat() <= policy.effective_to:
        block("Evidence falls outside the mapping policy's effective dates")
    expected = [pov.key() for pov in manifest.expected_povs]
    if not expected or len(set(expected)) != len(expected):
        block("Declared POV universe is empty or duplicated")
    ids = Counter(row.record_id for row in rows)
    observed = []
    sums = defaultdict(list)
    journal_counts = Counter(row.journal_id for row in rows if row.journal_id)
    for row in rows:
        if ids[row.record_id] > 1:
            block(f"Duplicate source record {row.record_id}", row)
        if row.amount is None or row.state != "VALUE":
            block("Missing or access-restricted amount cannot be interpreted as zero", row)
        try:
            pov, amount = mapped(row, policy, manifest.side)
        except ValueError as error:
            block(str(error), row)
            continue
        observed.append(canonical(pov))
        if set(pov["custom"]) != set(policy.custom_dimensions):
            block("Enabled custom dimensions do not match the approved dimension inventory", row)
        for dimension in DIMENSIONS:
            if dimension not in policy.members or pov[dimension] not in policy.members[dimension]:
                block(f"Unapproved {dimension} member {pov[dimension]}", row)
        for name, member in pov["custom"].items():
            if member not in policy.members.get("custom." + name, []):
                block(f"Unapproved custom member {name}", row)
        if row.pov.currency not in policy.currency_scales:
            block("Currency minor unit policy is unavailable", row)
        if row.amount is not None:
            sums[row.pov.currency].append(money(row.amount))
    if set(expected) != set(observed):
        block(f"POV coverage differs. Missing {len(set(expected) - set(observed))}, unexpected {len(set(observed) - set(expected))}")
    if manifest.side == "FCCS" and len(observed) != len(set(observed)):
        block("Duplicate FCCS cells at the complete POV grain")
    if set(sums) != set(manifest.totals_by_currency):
        block("Currency control totals do not cover the returned currencies")
    for currency, values in sums.items():
        if currency in manifest.totals_by_currency and total(values) != money(manifest.totals_by_currency[currency]):
            block(f"Source control total differs for {currency}")
    if journal_counts != Counter(manifest.journals):
        block("Journal header counts do not match all returned journal lines")
    return failures or [result("C01 Coverage", "PASS", "Hashes, counts, precision and full declared scope verified",
                               parameters={"batch_id": batch_id, "sha256": manifest.sha256})]


def validate(gl, fccs, policy: Policy, approved: bool, now=None, prior=None) -> dict:
    """Each batch is (id, manifest, normalized source rows, original CSV bytes)."""
    now = now or datetime.now(timezone.utc)
    with localcontext() as context:
        context.prec = 100
        return _validate(gl, fccs, policy, approved, now, prior)


def _validate(gl, fccs, policy, approved, now, prior):
    checks = []
    for batch in (gl, fccs):
        checks.extend(coverage(*batch[:3], policy, batch[3], approved, now))
    if gl[1].side != "GL" or fccs[1].side != "FCCS":
        checks.append(result("C01 Coverage", "BLOCKED", "Independent GL and FCCS sides are required"))
    if gl[1].source_system == fccs[1].source_system:
        checks.append(result("C01 Coverage", "BLOCKED", "Independent source systems must be identified"))
    if {p.key() for p in gl[1].expected_povs} != {p.key() for p in fccs[1].expected_povs}:
        checks.append(result("C07 Missing POV", "BLOCKED", "Source and FCCS declared universes differ"))
    if any(check["status"] == "BLOCKED" for check in checks):
        return finish(checks, policy)

    groups = {"GL": defaultdict(list), "FCCS": defaultdict(list)}
    references = {}
    for batch in (gl, fccs):
        batch_id, manifest, rows, _ = batch
        for row in rows:
            pov, amount = mapped(row, policy, manifest.side)
            entry = (pov, amount, lineage(batch_id, manifest, row))
            groups[manifest.side][canonical(pov)].append(entry)
            references[f"{manifest.side}:{row.record_id}"] = entry

    for key in sorted(set(groups["GL"]) | set(groups["FCCS"])):
        source, target = groups["GL"].get(key, []), groups["FCCS"].get(key, [])
        entries = source + target
        if not source or not target:
            checks.append(result("C07 Missing POV", "BLOCKED", "A required side is missing", entries[0][0],
                                 refs=[entry[2] for entry in entries]))
            continue
        expected, actual = total(entry[1] for entry in source), total(entry[1] for entry in target)
        description = "Exact stored amounts match"
        if expected != actual:
            description = "Source minus FCCS differs at full stored precision"
            if expected == -actual and expected != 0:
                description = "Account signs are reversed"
        checks.append(result("C04 Reconciliation", "PASS" if expected == actual else "FAIL", description,
                             source[0][0], expected, actual, [entry[2] for entry in entries],
                             {"mapping_version": policy.id, "tolerance": "0", "rounding": "none"}))

    if "trial_balance" in policy.required_controls:
        for side, group in groups.items():
            buckets = defaultdict(list)
            for entries in group.values():
                for entry in entries:
                    group_pov = {k: v for k, v in entry[0].items() if k not in {"account", "intercompany"}}
                    buckets[canonical(group_pov)].append(entry)
            for entries in buckets.values():
                balance = total(entry[1] for entry in entries)
                checks.append(result("C06 Trial balance", "PASS" if balance == 0 else "FAIL",
                                     f"{side} signed trial balance", entries[0][0], Decimal("0"), balance,
                                     [entry[2] for entry in entries]))
    else:
        reason = policy.exclusions.get("trial_balance")
        checks.append(result("C06 Trial balance", "NOT_APPLICABLE" if reason else "BLOCKED",
                             reason or "Trial balance has no approved applicability decision"))

    for name in ("journals", "intercompany", "fx", "hierarchy", "consolidation", "prior_period"):
        if name not in policy.required_controls:
            reason = policy.exclusions.get(name)
            checks.append(result(name, "NOT_APPLICABLE" if reason else "BLOCKED",
                                 reason or "Control has no approved applicability decision"))
            continue
        if name == "journals":
            checks.extend(journal_checks(gl, fccs, policy))
        elif name == "intercompany":
            checks.extend(intercompany_checks(groups["FCCS"]))
        elif name == "prior_period":
            checks.extend(prior_checks(gl, prior, policy))
        else:
            checks.extend(derived_checks(name, fccs, references, policy))
    return finish(checks, policy)


def journal_checks(gl, fccs, policy):
    checks = []
    for batch_id, manifest, rows, _ in (gl, fccs):
        if not manifest.journals:
            checks.append(result("C09 Journal coverage", "BLOCKED", f"{manifest.side} journal inventory required"))
        for journal in sorted(manifest.journals):
            lines = [row for row in rows if row.journal_id == journal]
            grain = {(r.pov.entity, r.pov.currency, r.pov.period, r.pov.year) for r in lines}
            if len(grain) != 1:
                checks.append(result("C09 Journal coverage", "BLOCKED", "Journal mixes entity, currency or period"))
                continue
            balance = total(money(row.amount) for row in lines)
            checks.append(result("C10 Journal balance", "PASS" if balance == 0 else "FAIL",
                                 f"{manifest.side} journal {journal}", lines[0].pov.model_dump(),
                                 Decimal("0"), balance, [lineage(batch_id, manifest, row) for row in lines],
                                 {"journal_id": journal, "line_count": len(lines)}))
    if set(gl[1].journals) != set(fccs[1].journals):
        checks.append(result("C09 Journal coverage", "BLOCKED",
                             "Independent source and FCCS journal identities do not match",
                             parameters={"missing_in_fccs": sorted(set(gl[1].journals) - set(fccs[1].journals)),
                                         "unexpected_in_fccs": sorted(set(fccs[1].journals) - set(gl[1].journals))}))
    journal_cells = {"GL": defaultdict(list), "FCCS": defaultdict(list)}
    for batch_id, manifest, rows, _ in (gl, fccs):
        for row in rows:
            if row.journal_id:
                pov, amount = mapped(row, policy, manifest.side)
                journal_cells[manifest.side][(row.journal_id, canonical(pov))].append(
                    (pov, amount, lineage(batch_id, manifest, row)))
    for key in sorted(set(journal_cells["GL"]) | set(journal_cells["FCCS"])):
        source, target = journal_cells["GL"].get(key, []), journal_cells["FCCS"].get(key, [])
        entries = source + target
        refs = [entry[2] for entry in entries]
        if not source or not target:
            checks.append(result("C11 Journal reconciliation", "BLOCKED",
                                 "Journal line POV is missing from one side", entries[0][0], refs=refs,
                                 parameters={"journal_id": key[0]}))
            continue
        expected, actual = total(e[1] for e in source), total(e[1] for e in target)
        checks.append(result("C11 Journal reconciliation", "PASS" if expected == actual else "FAIL",
                             "Independent journal amounts at the full POV grain", entries[0][0],
                             expected, actual, refs, {"journal_id": key[0], "tolerance": "0"}))
    return checks


def intercompany_checks(group):
    entries = [entry for values in group.values() for entry in values if entry[0]["intercompany"] != "ICP_None"]
    checks, seen = [], set()
    for entry in entries:
        pov, amount, ref = entry
        mirror = dict(pov, entity=pov["intercompany"], intercompany=pov["entity"])
        pair = tuple(sorted([canonical(pov), canonical(mirror)]))
        if pair in seen:
            continue
        seen.add(pair)
        peers = group.get(canonical(mirror), [])
        if len(peers) != 1:
            checks.append(result("C13 Intercompany", "BLOCKED", "Reciprocal counterparty is unavailable", pov, refs=[ref]))
        else:
            other = peers[0]
            checks.append(result("C13 Intercompany", "PASS" if amount == -other[1] else "FAIL",
                                 "Reciprocal entity balances at the same account, currency and stage", pov,
                                 amount, -other[1], [ref, other[2]]))
    return checks or [result("C13 Intercompany", "BLOCKED", "No intercompany evidence supplied")]


def derived_checks(name, fccs, references, policy):
    records = fccs[1].controls.get(name, [])
    if not records:
        return [result(name, "BLOCKED", "Required calculation evidence is unavailable")]
    if records != policy.formulas.get(name):
        return [result(name, "BLOCKED", "Calculation parameters differ from the independently approved policy")]
    checks = []
    for spec in records:
        try:
            target = references[spec["target"]]
            inputs = [references[key] for key in spec["inputs"]]
            if not inputs or spec["policy_id"] != policy.id:
                raise ValueError("Unapproved derived calculation")
            expected = total(entry[1] for entry in inputs)
            if name == "fx":
                if len(inputs) != 1 or spec["rounding"] not in ("HALF_EVEN", "HALF_UP"):
                    raise ValueError("A single FX basis and approved rounding are required")
                if spec["rate_type"] not in ("Average", "Closing", "Historical"):
                    raise ValueError("Unsupported rate type")
                if spec["period"] != target[0]["period"] or spec["year"] != target[0]["year"]:
                    raise ValueError("FX rate period differs")
                if spec["from_currency"] != inputs[0][0]["currency"] or spec["to_currency"] != target[0]["currency"]:
                    raise ValueError("FX rate currencies differ")
                rate = money(spec["rate"])
                if rate <= 0:
                    raise ValueError("FX rate must be positive")
                expected *= rate
                unrounded = decimal_text(expected)
                mode = ROUND_HALF_EVEN if spec["rounding"] == "HALF_EVEN" else ROUND_HALF_UP
                expected = expected.quantize(Decimal(1).scaleb(-policy.currency_scales[target[0]["currency"]]), rounding=mode)
                params = dict(spec, unrounded_expected=unrounded, stage="translation output")
            else:
                if any(entry[0]["currency"] != target[0]["currency"] for entry in inputs):
                    raise ValueError("Rollup currency differs")
                params = spec
                if name == "consolidation":
                    if spec["method"] != "proportional":
                        raise ValueError("Consolidation method is unsupported")
                    ownership = money(spec["ownership"])
                    if ownership < 0 or ownership > 1:
                        raise ValueError("Ownership must be between 0 and 1")
                    expected *= ownership
            refs = [entry[2] for entry in inputs] + [target[2]]
            checks.append(result(name, "PASS" if expected == target[1] else "FAIL",
                                 "Approved evidence formula evaluated using Decimal", target[0], expected, target[1], refs, params))
        except (KeyError, ValueError, TypeError, ArithmeticError) as error:
            checks.append(result(name, "BLOCKED", f"Calculation evidence is incomplete or invalid ({type(error).__name__})"))
    return checks


def prior_checks(gl, prior, policy):
    if prior is None:
        return [result("C11 Prior period", "BLOCKED", "An approved prior snapshot is required")]
    checks = []
    old = defaultdict(list)
    for row in prior[2]:
        pov, amount = mapped(row, policy, "GL")
        old[canonical({k: v for k, v in pov.items() if k not in {"period", "year"}})].append((amount, row))
    current = defaultdict(list)
    for row in gl[2]:
        pov, amount = mapped(row, policy, "GL")
        key = canonical({k: v for k, v in pov.items() if k not in {"period", "year"}})
        current[key].append((pov, amount, row))
    for key in sorted(set(current) | set(old)):
        rows = current.get(key, [])
        previous = old.get(key, [])
        if not rows:
            checks.append(result("C11 Prior period", "BLOCKED", "Current period POV is unavailable",
                                 previous[0][1].pov.model_dump()))
            continue
        pov = rows[0][0]
        amount = total(value for _, value, _ in rows)
        if not previous:
            checks.append(result("C11 Prior period", "BLOCKED", "Prior POV is unavailable", pov))
        else:
            previous_amount = total(value for value, _ in previous)
            checks.append(result("C11 Prior period", "PASS" if amount == previous_amount else "FAIL",
                                 "Period movement requires review", pov, amount, previous_amount,
                                 [lineage(gl[0], gl[1], row) for _, _, row in rows]
                                 + [lineage(prior[0], prior[1], r) for _, r in previous]))
    return checks


def finish(checks, policy):
    states = {item["status"] for item in checks}
    status = "BLOCKED" if "BLOCKED" in states else "FAIL" if "FAIL" in states else "PASS"
    body = {"status": status, "rule_version": RULE_VERSION, "policy_id": policy.id,
            "policy_sha256": digest(policy.model_dump()), "checks": checks,
            "counts": dict(Counter(item["status"] for item in checks))}
    body["result_sha256"] = digest(body)
    return body

import copy
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from packages.reconciliation.contracts import Manifest, Policy, Row, digest, money
from packages.reconciliation.engine import coverage, journal_checks, validate
from packages.source_connectors.csv_import import parse_csv
from scripts.fixtures import make_fixtures

NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)


def inputs():
    policy, bundles = make_fixtures()
    batches = []
    for side in ("GL", "FCCS"):
        raw, manifest = bundles[side]
        batches.append((side, Manifest.model_validate(manifest), parse_csv(raw), raw))
    return batches[0], batches[1], Policy.model_validate(policy)


def execute(gl, fccs, policy, approved=True):
    return validate(gl, fccs, policy, approved, now=NOW)


def cell(output, entity, account):
    return next(check for check in output["checks"] if check["rule"] == "C04 Reconciliation"
                and check["pov"]["entity"] == entity and check["pov"]["account"] == account)


def test_one_cent_and_offsetting_differences():
    result = execute(*inputs())
    first, second = cell(result, "US100", "400100"), cell(result, "US100", "400200")
    assert first["variance"] == "0.01"
    assert second["variance"] == "-0.01"
    assert first["status"] == second["status"] == "FAIL"
    assert Decimal(first["variance"]) + Decimal(second["variance"]) == 0


def test_currency_minor_units_and_high_precision_fx():
    result = execute(*inputs())
    assert cell(result, "JP300", "400100")["variance"] == "-1"
    assert cell(result, "KW400", "400100")["variance"] == "-0.001"
    fx = next(check for check in result["checks"] if check["rule"] == "fx")
    assert fx["status"] == "PASS"
    assert fx["parameters"]["rate"] == "0.880000004212"
    assert len(fx["parameters"]["unrounded_expected"].split(".")[1]) > 18


def test_subcent_difference_is_never_rounded_away():
    gl, fccs, policy = inputs()
    fccs[2][0].amount = "100.009"
    fccs[1].totals_by_currency["USD"] = str(Decimal(fccs[1].totals_by_currency["USD"]) + Decimal("0.009"))
    output = execute(gl, fccs, policy)
    assert cell(output, "US100", "400100")["variance"] == "0.001"
    assert cell(output, "US100", "400100")["status"] == "FAIL"


@pytest.mark.parametrize("value", [0.01, float("nan"), "NaN", "Infinity", "1e-2", "1,000.00", "1.000,00", "$10", "", " 1.0", "+1", "01", "1_000", "9" * 39, "0." + "1" * 19])
def test_reject_unsafe_amounts(value):
    with pytest.raises(ValueError):
        money(value)


@given(st.integers(min_value=-10**18, max_value=10**18))
def test_decimal_cent_property(cents):
    amount = Decimal(cents).scaleb(-2)
    assert money(format(amount, "f")) + money("0.01") - amount == Decimal("0.01")


@pytest.mark.parametrize("failure", ["missing", "restricted", "duplicate_id", "duplicate_cell", "period", "currency", "mapping", "custom", "hash", "count", "bytes", "incomplete", "precision", "journals", "stale", "empty_scope"])
def test_completeness_failures_prevent_numeric_validation(failure):
    gl, fccs, policy = inputs()
    if failure == "missing": fccs[2][0].amount = None
    elif failure == "restricted": fccs[2][0].state = "RESTRICTED"
    elif failure == "duplicate_id": gl[2][1].record_id = gl[2][0].record_id
    elif failure == "duplicate_cell": fccs[2][1].pov = fccs[2][0].pov
    elif failure == "period": fccs[2][0].pov.period = "Dec"
    elif failure == "currency": fccs[2][0].pov.currency = "GBP"
    elif failure == "mapping": del policy.account_map["400100"]
    elif failure == "custom": fccs[2][0].pov.custom = {}
    elif failure == "hash": fccs[1].sha256 = "0" * 64
    elif failure == "count": fccs[1].row_count += 1
    elif failure == "bytes": fccs[1].byte_count += 1
    elif failure == "incomplete": fccs[1].complete = False
    elif failure == "precision": fccs[1].precision_verified = False
    elif failure == "journals": fccs[1].journals["J-US100"] = 3
    elif failure == "stale": policy.maximum_age_seconds = 1
    elif failure == "empty_scope": fccs[1].expected_povs = []
    output = execute(gl, fccs, policy)
    assert output["status"] == "BLOCKED"
    assert all(check["rule"] != "C04 Reconciliation" for check in output["checks"])


def test_unapproved_policy_blocks():
    assert execute(*inputs(), approved=False)["status"] == "BLOCKED"


def test_incorrect_sign():
    gl, fccs, policy = inputs()
    row = next(row for row in fccs[2] if row.record_id == "GB200-400100")
    row.amount = "-100.00"
    fccs[1].totals_by_currency["EUR"] = "-200.00"
    check = cell(execute(gl, fccs, policy), "GB200", "400100")
    assert check["status"] == "FAIL" and check["explanation"] == "Account signs are reversed"


def test_unapproved_derived_formula_blocks():
    gl, fccs, policy = inputs()
    fccs[1].controls["fx"][0]["rate"] = "1"
    output = execute(gl, fccs, policy)
    assert next(c for c in output["checks"] if c["rule"] == "fx")["status"] == "BLOCKED"


def test_replay_is_deterministic():
    first = execute(*inputs())
    second = execute(*inputs())
    assert first == second


def test_original_scale_and_negative_zero_retained():
    assert str(money("-0.000")) == "-0.000"
    assert str(money("100.0100")) == "100.0100"


def test_journal_and_intercompany_controls_detect_failures():
    gl, fccs, policy = inputs()
    row = next(row for row in fccs[2] if row.record_id == "US100-610100")
    row.amount = "50.01"
    fccs[1].totals_by_currency["USD"] = str(Decimal(fccs[1].totals_by_currency["USD"]) + Decimal("0.01"))
    output = execute(gl, fccs, policy)
    assert any(c["status"] == "FAIL" and c["rule"] == "C10 Journal balance" for c in output["checks"])
    assert any(c["status"] == "FAIL" and c["rule"] == "C13 Intercompany" for c in output["checks"])


def test_missing_gl_leaf_is_blocked():
    gl, fccs, policy = inputs()
    gl[2].pop()
    assert execute(gl, fccs, policy)["status"] == "BLOCKED"


def test_prior_snapshot_required_when_enabled():
    gl, fccs, policy = inputs()
    policy.required_controls.append("prior_period")
    assert execute(gl, fccs, policy)["status"] == "BLOCKED"


def test_trial_balance_cannot_be_silently_omitted():
    gl, fccs, policy = inputs()
    policy.required_controls.remove("trial_balance")
    checks = execute(gl, fccs, policy)["checks"]
    assert next(c for c in checks if c["rule"] == "C06 Trial balance")["status"] == "BLOCKED"


def test_different_journal_inventory_is_blocked_even_when_balanced():
    gl, fccs, policy = inputs()
    fccs[1].journals["UNMATCHED"] = fccs[1].journals.pop("J-US100")
    for row in fccs[2]:
        if row.journal_id == "J-US100":
            row.journal_id = "UNMATCHED"
    checks = journal_checks(gl, fccs, policy)
    assert all(c["status"] == "PASS" for c in checks if c["rule"] == "C10 Journal balance")
    assert any(c["status"] == "BLOCKED" and c["rule"] == "C09 Journal coverage" for c in checks)


def test_balanced_journals_cannot_hide_line_reassignments():
    gl, fccs, policy = inputs()
    for batch in (gl, fccs):
        batch[1].journals["J-US100-2"] = 2
        for row in batch[2]:
            if row.record_id in {"US100-400100", "US100-400200"}:
                row.journal_id = "J-US100-2"
                row.amount = "50.00" if row.record_id.endswith("400100") else "-50.00"
    for row in fccs[2]:
        if row.journal_id in {"J-US100", "J-US100-2"}:
            row.journal_id = "J-US100-2" if row.journal_id == "J-US100" else "J-US100"
    checks = journal_checks(gl, fccs, policy)
    assert all(c["status"] == "PASS" for c in checks if c["rule"] == "C10 Journal balance")
    assert any(c["status"] == "BLOCKED" and c["rule"] == "C11 Journal reconciliation" for c in checks)

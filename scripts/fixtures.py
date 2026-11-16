"""Deterministic synthetic balances, including offsetting cent discrepancies."""
import csv
import io
import json
import zipfile
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from packages.reconciliation.contracts import DIMENSIONS, canonical, decimal_text, digest, money, total
from packages.source_connectors.csv_import import COLUMNS

ENTITIES = {"US100": "USD", "GB200": "EUR", "JP300": "JPY", "KW400": "KWD", "GROUP": "USD", "SHARE": "USD"}
ACCOUNTS = ["400100", "400200", "100100", "610100", "210100", "150100", "130100", "399900"]


def base_pov(entity, account):
    return {"environment": "TEST", "application": "FCCS_DEMO", "cube": "Consol", "scenario": "Actual",
            "year": "FY26", "period": "Nov", "view": "FCCS_Periodic", "entity": entity,
            "account": account, "intercompany": "ICP_None", "movement": "FCCS_Mvmts_NetIncome",
            "data_source": "FCCS_Managed Data", "consolidation": "FCCS_Entity Input",
            "currency": ENTITIES[entity], "custom": {"Department": "Corporate"}}


def make_fixtures():
    with localcontext() as context:
        context.prec = 100
        return _make_fixtures()


def _make_fixtures():
    source = []
    for entity, currency in ENTITIES.items():
        scale = {"USD": 2, "EUR": 2, "JPY": 0, "KWD": 3}[currency]
        amounts = {"400100": "100", "400200": "200", "610100": "50", "210100": "-50"}
        for account, amount in amounts.items():
            source.append(dict(record_id=f"{entity}-{account}", **base_pov(entity, account),
                               amount=format(Decimal(amount), f".{scale}f"), state="VALUE",
                               journal_id=f"J-{entity}" if account in {"610100", "210100"} else ""))
    source[0]["amount"], source[1]["amount"] = "100.01", "199.99"
    for entity, amount in [("US100", "1234.56789123456789"), ("GB200", "1086.42")]:
        source.append(dict(record_id=f"{entity}-FX", **base_pov(entity, "150100"), amount=amount, state="VALUE", journal_id=""))
    rate = "0.880000004212"
    fx = (money("1234.56789123456789") * money(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    next(row for row in source if row["record_id"] == "GB200-FX")["amount"] = decimal_text(fx)
    # Both sides of an intercompany pair use USD and the same dimensional grain.
    for entity, partner, amount in [("US100", "GROUP", "75.00"), ("GROUP", "US100", "-75.00")]:
        pov = base_pov(entity, "130100")
        pov["intercompany"] = partner
        source.append(dict(record_id=f"{entity}-IC", **pov, amount=amount, state="VALUE", journal_id=""))
    next(row for row in source if row["record_id"] == "GROUP-400100")["amount"] = "300.00"
    next(row for row in source if row["record_id"] == "SHARE-400100")["amount"] = "150.00"
    for entity in ENTITIES:
        balance = total(money(row["amount"]) for row in source if row["entity"] == entity)
        source.append(dict(record_id=f"{entity}-EQUITY", **base_pov(entity, "399900"),
                           amount=decimal_text(-balance), state="VALUE", journal_id=""))
    target = [dict(row) for row in source]
    next(row for row in target if row["record_id"] == "US100-400100")["amount"] = "100.00"
    next(row for row in target if row["record_id"] == "US100-400200")["amount"] = "200.00"
    next(row for row in target if row["record_id"] == "KW400-400100")["amount"] = "100.001"
    next(row for row in target if row["record_id"] == "JP300-400100")["amount"] = "101"
    next(row for row in target if row["record_id"] == "GROUP-IC")["amount"] = "-74.99"
    members = {dimension: sorted({row[dimension] for row in source}) for dimension in DIMENSIONS}
    members["custom.Department"] = ["Corporate"]
    policy = {"id": "demo-policy-v1", "name": "Synthetic November control policy", "effective_from": "2026-01-01",
              "effective_to": "2036-12-31", "currency_scales": {"USD": 2, "EUR": 2, "JPY": 0, "KWD": 3},
              "members": members, "custom_dimensions": ["Department"],
              "account_map": {account: account for account in ACCOUNTS},
              "sign_map": {account: "1" for account in ACCOUNTS},
              "required_controls": ["trial_balance", "journals", "intercompany", "fx", "hierarchy", "consolidation"],
              "exclusions": {"prior_period": "Synthetic opening baseline. Historical comparison is available between captured runs."},
              "maximum_age_seconds": 315360000}
    controls = {
        "fx": [{"target": "FCCS:GB200-FX", "inputs": ["GL:US100-FX"], "rate": rate,
                "rate_type": "Closing", "period": "Nov", "year": "FY26", "from_currency": "USD",
                "to_currency": "EUR", "rounding": "HALF_EVEN", "policy_id": policy["id"], "rate_id": "synthetic-rate-1"}],
        "hierarchy": [{"target": "FCCS:GROUP-400100", "inputs": ["GL:US100-400100", "GL:US100-400200"], "policy_id": policy["id"]}],
        "consolidation": [{"target": "FCCS:SHARE-400100", "inputs": ["FCCS:GROUP-400100"], "ownership": "0.5",
                           "method": "proportional", "policy_id": policy["id"]}],
    }
    policy["formulas"] = controls
    bundles = {}
    for side, rows in [("GL", source), ("FCCS", target)]:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row, custom=canonical(row["custom"])))
        raw = output.getvalue().encode()
        manifest = {"version": "1", "dataset_id": f"November 2026 {side} synthetic snapshot", "side": side,
                    "source_system": f"SYNTHETIC_{side}", "extracted_at": "2026-11-11T12:00:00+00:00",
                    "row_count": len(rows), "byte_count": len(raw), "sha256": digest(raw), "complete": True,
                    "precision_verified": True, "policy_id": policy["id"], "unit": "units",
                    "expected_povs": [{**{key: row[key] for key in DIMENSIONS}, "custom": row["custom"]} for row in rows],
                    "totals_by_currency": {currency: decimal_text(total(money(row["amount"]) for row in rows if row["currency"] == currency)) for currency in set(ENTITIES.values())},
                    "journals": {f"J-{entity}": 2 for entity in ENTITIES}, "controls": controls if side == "FCCS" else {}}
        bundles[side] = (raw, manifest)
    return policy, bundles


def zip_package(raw, manifest):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.csv", raw)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return stream.getvalue()


if __name__ == "__main__":
    root = Path("fixtures")
    root.mkdir(exist_ok=True)
    policy, bundles = make_fixtures()
    (root / "policy.json").write_text(json.dumps(policy, indent=2))
    for side, (raw, manifest) in bundles.items():
        (root / f"{side.lower()}.zip").write_bytes(zip_package(raw, manifest))
        (root / f"{side.lower()}.csv").write_bytes(raw)
        (root / f"{side.lower()}.manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Generated synthetic fixtures")

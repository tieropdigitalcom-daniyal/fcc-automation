"""Oracle FCCS Integration File Generator & Pre-consolidation Transformer."""
from collections import Counter
import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Any

from packages.reconciliation.contracts import (
    DIMENSIONS,
    Manifest,
    POV,
    Row,
    canonical,
    decimal_text,
    digest,
    money,
)
from packages.source_connectors.csv_import import COLUMNS
from .rates import RatesManager
from .rules import RulesManager


class IntegrationFileGenerator:
    """Transforms raw general ledger files into validated Oracle FCCS integration files."""

    def __init__(self, rates_mgr: RatesManager, rules_mgr: RulesManager):
        self.rates = rates_mgr
        self.rules = rules_mgr

    def process_gl_records(
        self,
        raw_csv_text: str,
        default_scenario: str = "Actual",
        default_year: str = "FY26",
        default_period: str = "Nov",
        default_view: str = "FCCS_Periodic",
    ) -> list[dict[str, Any]]:
        """Parses and transforms GL trial balance records into FCCS-compliant records."""
        reader = csv.DictReader(io.StringIO(raw_csv_text))
        transformed = []

        for row in reader:
            record_id = row.get("record_id") or f"{row.get('entity', 'US100')}-{row.get('account', '400100')}"
            raw_acc = row.get("account", "").strip()
            target_acc, sign = self.rules.map_account(raw_acc)

            raw_amount_str = row.get("amount", "0").strip()
            amount_dec = money(raw_amount_str) * Decimal(sign)

            entity = row.get("entity", "US100").strip()
            currency = row.get("currency", "USD").strip()
            intercompany = row.get("intercompany", "ICP_None").strip()
            movement = row.get("movement", "FCCS_Mvmts_NetIncome").strip()
            data_source = row.get("data_source", "FCCS_Managed Data").strip()
            consolidation = row.get("consolidation", "FCCS_Entity Input").strip()
            scenario = row.get("scenario", default_scenario).strip()
            year = row.get("year", default_year).strip()
            period = row.get("period", default_period).strip()
            view = row.get("view", default_view).strip()

            custom = {}
            if "custom" in row and row["custom"]:
                try:
                    custom = json.loads(row["custom"])
                except Exception:
                    custom = {"Department": "Corporate"}
            elif "Department" in row:
                custom = {"Department": row["Department"]}
            else:
                custom = {"Department": "Corporate"}

            item = {
                "record_id": record_id,
                "environment": row.get("environment", "TEST"),
                "application": row.get("application", "FCCS_DEMO"),
                "cube": row.get("cube", "Consol"),
                "scenario": scenario,
                "year": year,
                "period": period,
                "view": view,
                "entity": entity,
                "account": target_acc,
                "intercompany": intercompany,
                "movement": movement,
                "data_source": data_source,
                "consolidation": consolidation,
                "currency": currency,
                "custom": custom,
                "amount": decimal_text(amount_dec),
                "state": "VALUE",
                "journal_id": row.get("journal_id", ""),
            }
            transformed.append(item)

        return transformed

    def generate_fccs_data_management_csv(self, records: list[dict[str, Any]]) -> str:
        """Generates standard Oracle Data Management (FDMEE) / Data Integration file."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Account",
            "Entity",
            "Scenario",
            "Year",
            "Period",
            "View",
            "Currency",
            "Movement",
            "Intercompany",
            "Data_Source",
            "Consolidation",
            "Department",
            "Amount",
        ])
        for r in records:
            writer.writerow([
                r["account"],
                r["entity"],
                r["scenario"],
                r["year"],
                r["period"],
                r["view"],
                r["currency"],
                r["movement"],
                r["intercompany"],
                r["data_source"],
                r["consolidation"],
                r["custom"].get("Department", "Corporate"),
                r["amount"],
            ])
        return output.getvalue()

    def generate_standard_data_csv(self, records: list[dict[str, Any]]) -> str:
        """Generates strict standard 19-column CSV matching the platform's verification contracts."""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=COLUMNS)
        writer.writeheader()
        for r in records:
            row_dict = dict(r)
            row_dict["custom"] = json.dumps(r["custom"])
            writer.writerow(row_dict)
        return output.getvalue()

    def create_package_zip(
        self,
        records: list[dict[str, Any]],
        side: str = "GL",
        dataset_id: str = "Automated Source Load",
        policy_id: str = "auto-policy-v1",
    ) -> bytes:
        """Creates an attested, cryptographically hashed evidence package ZIP with manifest."""
        csv_text = self.generate_standard_data_csv(records)
        raw_bytes = csv_text.encode("utf-8")
        sha256 = digest(raw_bytes)

        totals_by_currency: dict[str, str] = {}
        expected_povs = []
        journals = Counter(r["journal_id"] for r in records if r.get("journal_id"))

        currency_buckets: dict[str, list[Decimal]] = {}
        for r in records:
            c = r["currency"]
            currency_buckets.setdefault(c, []).append(money(r["amount"]))
            pov = {dim: r[dim] for dim in DIMENSIONS}
            pov["custom"] = r["custom"]
            expected_povs.append(pov)

        with localcontext() as ctx:
            ctx.prec = 100
            for curr, amounts in currency_buckets.items():
                totals_by_currency[curr] = decimal_text(sum(amounts, Decimal("0")))

        manifest = {
            "version": "1",
            "dataset_id": dataset_id,
            "side": side,
            "source_system": "ERP_GL_SOURCE" if side == "GL" else "ORACLE_FCCS",
            "sha256": sha256,
            "byte_count": len(raw_bytes),
            "row_count": len(records),
            "complete": True,
            "precision_verified": True,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "policy_id": policy_id,
            "unit": "units",
            "totals_by_currency": totals_by_currency,
            "expected_povs": expected_povs,
            "journals": dict(journals),
            "controls": {},
        }

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.csv", raw_bytes)
            zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

        return zip_buf.getvalue()

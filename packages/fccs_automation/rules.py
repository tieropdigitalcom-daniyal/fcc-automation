"""Oracle FCCS Consolidation, Elimination, and Account Rules Engine."""
import csv
import io
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Literal

from packages.reconciliation.contracts import Policy, money


@dataclass
class AccountMapping:
    source_account: str
    target_account: str
    sign: int = 1
    description: str = ""
    category: str = "Operating"


@dataclass
class ConsolidationRule:
    parent_entity: str
    child_entity: str
    ownership: str = "1.0"
    method: Literal["full", "proportional", "equity"] = "full"
    elimination_icp: str = "ICP_None"


class RulesManager:
    """Manages mappings, consolidation logic, sign conventions, and control criteria."""

    def __init__(self):
        self.account_mappings: dict[str, AccountMapping] = {}
        self.consolidation_rules: list[ConsolidationRule] = []
        self.currency_scales: dict[str, int] = {
            "USD": 2,
            "EUR": 2,
            "GBP": 2,
            "JPY": 0,
            "KWD": 3,
            "CAD": 2,
            "AUD": 2,
        }
        self.dimensions_members: dict[str, list[str]] = {
            "environment": ["TEST", "PROD"],
            "application": ["FCCS_DEMO", "FCCS_CORP"],
            "cube": ["Consol"],
            "scenario": ["Actual", "Budget", "Forecast"],
            "year": ["FY24", "FY25", "FY26", "FY27"],
            "period": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            "view": ["FCCS_Periodic", "FCCS_YTD"],
            "entity": ["US100", "GB200", "JP300", "KW400", "GROUP", "SHARE"],
            "account": ["100100", "130100", "150100", "210100", "399900", "400100", "400200", "610100"],
            "intercompany": ["ICP_None", "US100", "GB200", "JP300", "KW400", "GROUP"],
            "movement": ["FCCS_Mvmts_NetIncome", "FCCS_Mvmts_OpeningBalance", "FCCS_Mvmts_Additions", "FCCS_Mvmts_Transfers"],
            "data_source": ["FCCS_Managed Data", "FCCS_Intercompany Eliminations", "FCCS_Data Input"],
            "consolidation": ["FCCS_Entity Input", "FCCS_Entity Consol", "FCCS_Elimination", "FCCS_Contribution"],
            "currency": ["USD", "EUR", "GBP", "JPY", "KWD"],
            "custom.Department": ["Corporate", "Operations", "Finance", "Sales"],
        }
        self.custom_dimensions: list[str] = ["Department"]
        self.required_controls: list[str] = [
            "trial_balance",
            "journals",
            "intercompany",
            "fx",
            "hierarchy",
            "consolidation",
        ]

        # Seed standard default mappings
        for acc in ["100100", "130100", "150100", "210100", "399900", "400100", "400200", "610100"]:
            self.add_account_mapping(AccountMapping(source_account=acc, target_account=acc, sign=1))

        self.consolidation_rules.append(
            ConsolidationRule(parent_entity="GROUP", child_entity="US100", ownership="1.0", method="full")
        )
        self.consolidation_rules.append(
            ConsolidationRule(parent_entity="GROUP", child_entity="GB200", ownership="1.0", method="full")
        )
        self.consolidation_rules.append(
            ConsolidationRule(parent_entity="SHARE", child_entity="GROUP", ownership="0.5", method="proportional")
        )

    def add_account_mapping(self, mapping: AccountMapping):
        self.account_mappings[mapping.source_account] = mapping

    def map_account(self, source_account: str) -> tuple[str, int]:
        mapping = self.account_mappings.get(source_account)
        if not mapping:
            # Default pass-through if unmapped
            return source_account, 1
        return mapping.target_account, mapping.sign

    def to_policy_dict(self, policy_id: str = "auto-policy-v1") -> dict:
        return {
            "id": policy_id,
            "name": "Autonomous FCCS Integration Policy",
            "effective_from": "2026-01-01",
            "effective_to": "2036-12-31",
            "currency_scales": self.currency_scales,
            "members": self.dimensions_members,
            "custom_dimensions": self.custom_dimensions,
            "account_map": {k: v.target_account for k, v in self.account_mappings.items()},
            "sign_map": {k: str(v.sign) for k, v in self.account_mappings.items()},
            "required_controls": self.required_controls,
            "exclusions": {},
            "maximum_age_seconds": 315360000,
            "formulas": {
                "fx": [],
                "hierarchy": [
                    {
                        "target": f"FCCS:{r.parent_entity}-400100",
                        "inputs": [f"GL:{r.child_entity}-400100"],
                        "policy_id": policy_id,
                    }
                    for r in self.consolidation_rules
                    if r.method == "full"
                ],
                "consolidation": [
                    {
                        "target": f"FCCS:{r.parent_entity}-400100",
                        "inputs": [f"FCCS:{r.child_entity}-400100"],
                        "ownership": r.ownership,
                        "method": r.method,
                        "policy_id": policy_id,
                    }
                    for r in self.consolidation_rules
                    if r.method == "proportional"
                ],
            },
        }

    def load_from_policy(self, policy: dict):
        if "currency_scales" in policy:
            self.currency_scales = policy["currency_scales"]
        if "members" in policy:
            self.dimensions_members = policy["members"]
        if "custom_dimensions" in policy:
            self.custom_dimensions = policy["custom_dimensions"]
        if "account_map" in policy and "sign_map" in policy:
            self.account_mappings = {
                acc: AccountMapping(
                    source_account=acc,
                    target_account=policy["account_map"].get(acc, acc),
                    sign=int(policy["sign_map"].get(acc, "1")),
                )
                for acc in policy["account_map"]
            }

    def export_dm_mappings_csv(self) -> str:
        """Exports Oracle Data Management (FDMEE) Account Dimension Mapping format."""
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Source_Account", "Target_Account", "Sign", "Category", "Description"])
        for m in self.account_mappings.values():
            writer.writerow([m.source_account, m.target_account, m.sign, m.category, m.description])
        return out.getvalue()

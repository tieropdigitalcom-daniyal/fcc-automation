"""Standalone Automated Pipeline Runner for Oracle FCCS Integration and Validation.

Usage:
    python -m scripts.fccs_agent_pipeline
    python -m scripts.fccs_agent_pipeline --gl-file fixtures/gl.csv --output-dir runtime/automation_output
"""
import argparse
import sys
from pathlib import Path

from packages.fccs_automation.agent import FCCSAutomationAgent
from packages.fccs_automation.rates import FXRate, RatesManager
from packages.fccs_automation.rules import AccountMapping, ConsolidationRule, RulesManager


def main():
    parser = argparse.ArgumentParser(description="Autonomous Oracle FCCS Pipeline & Validation Agent")
    parser.add_argument("--gl-file", default="fixtures/gl.csv", help="Path to raw source General Ledger CSV file")
    parser.add_argument("--output-dir", default="runtime/automation_output", help="Directory to save generated FCCS files and reports")
    args = parser.parse_args()

    gl_path = Path(args.gl_file)
    if not gl_path.exists():
        print(f"Error: GL file not found at {gl_path.resolve()}", file=sys.stderr)
        sys.exit(1)

    print("=" * 75)
    print("🚀 STARTING AUTONOMOUS ORACLE FCCS AGENT PIPELINE")
    print("=" * 75)

    # 1. Initialize Rates Manager
    rates_mgr = RatesManager()
    rates_mgr.add_rate(FXRate(from_currency="USD", to_currency="EUR", rate="0.880000004212", rate_type="Closing"))
    rates_mgr.add_rate(FXRate(from_currency="USD", to_currency="GBP", rate="0.770000000000", rate_type="Closing"))
    rates_mgr.add_rate(FXRate(from_currency="USD", to_currency="JPY", rate="152.450000000000", rate_type="Closing"))
    rates_mgr.add_rate(FXRate(from_currency="USD", to_currency="KWD", rate="0.308000000000", rate_type="Closing"))
    print(f"✓ Initialized Rates Manager with {len(rates_mgr.rates)} active currency exchange rates")

    # 2. Initialize Rules Manager
    rules_mgr = RulesManager()
    print(f"✓ Initialized Rules Manager with {len(rules_mgr.account_mappings)} account mappings and {len(rules_mgr.consolidation_rules)} consolidation rules")

    # 3. Create Automation Agent
    agent = FCCSAutomationAgent(rates_mgr=rates_mgr, rules_mgr=rules_mgr)

    # 4. Ingest Source GL File
    raw_gl_text = gl_path.read_text(encoding="utf-8")
    record_count = agent.ingest_gl_source(raw_gl_text)
    print(f"✓ Ingested and mapped {record_count} records from {gl_path.name}")

    # 5. Generate Integration Files
    integration_info = agent.generate_fccs_integration_files()
    print(f"✓ Generated Oracle FCCS Data Management load files ({integration_info['gl_bundle_bytes']} bytes packaged)")

    # 6. Execute Consolidation
    agent.execute_fccs_consolidation()
    print("✓ Automated FCCS consolidation execution & target extraction completed")

    # 7. Validate FCCS Data
    val_result = agent.validate_fccs_data()
    counts = val_result["counts"]
    print(f"✓ Automated validation completed: Status = {val_result['status']}")
    print(f"  • PASS:    {counts.get('PASS', 0)} controls verified down to exact cent")
    print(f"  • FAIL:    {counts.get('FAIL', 0)} variances flagged for review")
    print(f"  • BLOCKED: {counts.get('BLOCKED', 0)} missing coverage items")

    # 8. Export All Deliverables
    out_dir = Path(args.output_dir)
    agent.export_all_deliverables(out_dir)

    print("\n" + "=" * 75)
    print(f"📁 ALL FCCS AUTOMATION DELIVERABLES EXPORTED TO: {out_dir.resolve()}")
    print("=" * 75)
    print("  1. fccs_data_management_load.csv -> Integration file ready to load into Oracle FCCS")
    print("  2. fccs_exchange_rates.csv       -> Exchange rates file for FCCS Rate dimension")
    print("  3. fccs_account_mappings.csv     -> Data Management FDMEE mapping file")
    print("  4. fccs_validation_report.json   -> Complete verification report & control audit")
    print("  5. fccs_validation_summary.txt   -> Human-readable audit summary")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()

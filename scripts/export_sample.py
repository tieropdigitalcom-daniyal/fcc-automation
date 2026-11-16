from pathlib import Path
from sqlalchemy import select

from services.api.config import settings
from services.api.database import Run, SessionLocal
from services.api.reports import bundle_report, csv_report, pdf_report, report_document
import json

if settings.app_mode != "demo":
    raise RuntimeError("Sample report command is for synthetic data only")
with SessionLocal() as db:
    run = db.scalar(select(Run).where(Run.state == "FAIL").order_by(Run.created.desc()))
    if run is None:
        raise RuntimeError("Seed the synthetic validation first")
    document = report_document(db, run)
    output = Path("reports")
    output.mkdir(exist_ok=True)
    (output / "sample-audit.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    (output / "sample-audit.csv").write_bytes(csv_report(document))
    (output / "sample-audit.pdf").write_bytes(pdf_report(document))
    (output / "sample-evidence-bundle.zip").write_bytes(bundle_report(document))
    print("Sample audit report exported from", run.id[:12])

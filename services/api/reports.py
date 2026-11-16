import csv
import io
import json
import zipfile
from html import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from packages.reconciliation.contracts import canonical, digest
from .config import settings
from .database import Batch, ExceptionCase, PolicyRecord
from .storage import EvidenceStore
from sqlalchemy import select


def report_document(db, run):
    batches = [db.get(Batch, run.gl_id), db.get(Batch, run.fccs_id)]
    if run.prior_id:
        batches.append(db.get(Batch, run.prior_id))
    cases = db.scalars(select(ExceptionCase).where(ExceptionCase.run_id == run.id)).all()
    return {"report_schema": "1", "data_mode": settings.app_mode, "run_id": run.id,
            "created_by": run.created_by, "created": run.created, "completed": run.completed,
            "scope": run.entities, "result": run.result,
            "policy": db.get(PolicyRecord, run.policy_id).document,
            "evidence": [{"batch_id": batch.id, "original_sha256": batch.sha256, "manifest": batch.manifest} for batch in batches],
            "dispositions": [{"id": case.id, "state": case.state, "owner": case.owner} for case in cases]}


def safe_csv(value):
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def csv_report(document):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["rule", "status", "entity", "account", "currency", "source", "fccs", "variance", "explanation", "lineage", "parameters"])
    for check in document["result"]["checks"]:
        pov = check["pov"]
        writer.writerow([safe_csv(value) for value in [check["rule"], check["status"], pov.get("entity"), pov.get("account"),
            pov.get("currency"), check["expected"], check["actual"], check["variance"], check["explanation"],
            canonical(check["lineage"]), canonical(check["parameters"])]])
    return output.getvalue().encode("utf-8-sig")


def pdf_report(document):
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13
    story = [Paragraph("FCCS Validation &amp; Audit Agent", styles["Title"]),
             Paragraph("Synthetic evidence report" if document["data_mode"] == "demo" else "Validation evidence report", styles["Heading2"]),
             Paragraph(f"Outcome <b>{escape(document['result']['status'])}</b>", styles["BodyText"]),
             Paragraph("Run " + document["run_id"], styles["BodyText"]),
             Paragraph("Scope " + escape(", ".join(document["scope"])), styles["BodyText"]),
             Paragraph("Exact variance is source minus FCCS. Original failures remain in the report after review.", styles["BodyText"]),
             Spacer(1, 14)]
    data = [[Paragraph(value, styles["BodyText"]) for value in ["Control / entity / account", "Status", "Exact variance"]]]
    for check in document["result"]["checks"]:
        if check["status"] in {"FAIL", "BLOCKED"}:
            label = escape(f"{check['rule']} / {check['pov'].get('entity', 'Scope')} / {check['pov'].get('account', '-')}")
            variance = escape(str(check["variance"]) if check["variance"] is not None else "Unavailable")
            data.append([Paragraph(label, styles["BodyText"]), check["status"], Paragraph(variance, styles["BodyText"])])
    table = Table(data, colWidths=[3.4 * inch, .85 * inch, 1.9 * inch], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eeea")),
                              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                              ("TOPPADDING", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 0), (-1, -1), .3, colors.lightgrey)]))
    story.extend([table, Spacer(1, 20), Paragraph("Evidence fingerprints", styles["Heading2"])])
    for item in document["evidence"]:
        story.extend([Paragraph(escape(item["manifest"]["dataset_id"]), styles["BodyText"]),
                      Paragraph(item["original_sha256"], styles["BodyText"])])
    story.extend([Spacer(1, 12), Paragraph("Result fingerprint " + document["result"]["result_sha256"], styles["BodyText"]),
                  Paragraph("The JSON and original CSV files in the evidence bundle contain full POV, lineage, formulas, mapping and precision policy. Finance approval of live scope remains required.", styles["BodyText"])])
    SimpleDocTemplate(output, rightMargin=38, leftMargin=38, topMargin=38, bottomMargin=38).build(story)
    return output.getvalue()


def bundle_report(document):
    files = {"report.json": json.dumps(document, indent=2).encode(), "checks.csv": csv_report(document), "summary.pdf": pdf_report(document)}
    for item in document["evidence"]:
        files[f"evidence/{item['batch_id']}.csv"] = EvidenceStore().get(item["original_sha256"])
    files["SHA256SUMS.json"] = json.dumps({name: digest(value) for name, value in files.items()}, indent=2).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return stream.getvalue()

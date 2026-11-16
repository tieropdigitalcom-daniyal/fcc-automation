"""Bounded UTF-8 imports. Archives are inspected in memory and never extracted."""
import csv
import io
import json
import zipfile
from pathlib import PurePosixPath

from packages.reconciliation.contracts import DIMENSIONS, Manifest, POV, Row

MAX_BYTES = 20_000_000
COLUMNS = ["record_id", *DIMENSIONS, "custom", "amount", "state", "journal_id"]


def unpack(data: bytes) -> tuple[bytes, dict]:
    if len(data) > MAX_BYTES:
        raise ValueError("Archive exceeds 20 MB")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) != 2 or {entry.filename for entry in entries} != {"data.csv", "manifest.json"}:
            raise ValueError("ZIP must contain exactly data.csv and manifest.json at its root")
        for entry in entries:
            if entry.flag_bits & 1 or entry.file_size > MAX_BYTES or PurePosixPath(entry.filename).is_absolute():
                raise ValueError("Unsafe or oversized archive member")
        if sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise ValueError("Expanded archive exceeds 20 MB")
        raw = archive.read("data.csv")
        manifest_bytes = archive.read("manifest.json")
    return raw, json.loads(manifest_bytes.decode("utf-8-sig"))


def parse_csv(raw: bytes) -> list[Row]:
    if len(raw) > MAX_BYTES:
        raise ValueError("CSV exceeds 20 MB")
    text = raw.decode("utf-8-sig", errors="strict")
    if "\x00" in text:
        raise ValueError("NUL bytes are forbidden")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if reader.fieldnames != COLUMNS:
        raise ValueError("CSV columns must match the version 1 schema exactly")
    rows = []
    for entry in reader:
        if None in entry or any(v is None for v in entry.values()):
            raise ValueError(f"Malformed CSV at line {reader.line_num}")
        pov = POV(**{key: entry[key] for key in DIMENSIONS}, custom=json.loads(entry["custom"]))
        row = Row(record_id=entry["record_id"], pov=pov, amount=entry["amount"] or None,
                  state=entry["state"], journal_id=entry["journal_id"], line=reader.line_num)
        rows.append(row)
        if len(rows) > 100000:
            raise ValueError("CSV exceeds 100,000 records")
    return rows


def read_package(data: bytes):
    try:
        raw, metadata = unpack(data)
    except zipfile.BadZipFile as error:
        raise ValueError("Invalid or corrupted ZIP archive") from error
    manifest = Manifest.model_validate(metadata)
    rows = parse_csv(raw)
    return raw, manifest, rows

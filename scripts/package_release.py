"""Package reviewed source and synthetic reports, excluding local runtime state."""
import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path


EXCLUDED_DIRECTORIES = {
    ".git", ".venv", "node_modules", ".next", "runtime", "__pycache__",
    ".pytest_cache", ".hypothesis", "test-results", "playwright-report",
}
EXCLUDED_SUFFIXES = {".pyc", ".tsbuildinfo", ".pem", ".key", ".p12", ".pfx"}


def source_files(root):
    for directory, children, filenames in os.walk(root):
        children[:] = sorted(name for name in children if name not in EXCLUDED_DIRECTORIES)
        for name in sorted(filenames):
            path = Path(directory) / name
            if path.is_symlink() or path.suffix in EXCLUDED_SUFFIXES:
                continue
            if name.startswith(".env") and name != ".env.example":
                continue
            if name == "SOURCE_SHA256.json":
                continue
            yield path


def package(destination):
    root = Path(__file__).resolve().parents[1]
    destination = Path(destination).resolve()
    if root == destination or root in destination.parents:
        raise ValueError("Write the release archive outside its source directory")
    paths = list(source_files(root))
    hashes = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    manifest = root / "SOURCE_SHA256.json"
    manifest.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths + [manifest]:
            archive.write(path, "fccs-validation/" + path.relative_to(root).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive failed its CRC check")
        for name, expected in hashes.items():
            if hashlib.sha256(archive.read("fccs-validation/" + name)).hexdigest() != expected:
                raise ValueError("Packaged source hash mismatch: " + name)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(checksum + "  " + destination.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(destination), "files": len(paths) + 1,
                      "bytes": destination.stat().st_size, "sha256": checksum}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    package(parser.parse_args().destination)

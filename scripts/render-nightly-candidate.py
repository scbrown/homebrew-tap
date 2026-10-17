#!/usr/bin/env python3
"""Render a temporary CI formula from the two verified build artifacts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tarfile

spec = importlib.util.spec_from_file_location("generate", Path(__file__).with_name("generate.py"))
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


def candidate(root, assets, version, sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("candidate requires the full selected source SHA")
    if not re.fullmatch(r"\d+\.\d+\.\d+-nightly\.\d{14}\." + sha[:12], version):
        raise ValueError("candidate version does not identify the selected source")
    manifest = json.loads((root / "manifest.json").read_text())
    row = manifest["previews"]["caboodle-nightly"]
    rows = []
    for platform, values in manifest["platforms"].items():
        archive = assets / row["asset"].format(ver=version, **values)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        expected = Path(str(archive) + ".sha256").read_text().split()
        if expected != [digest, archive.name]:
            raise ValueError("candidate archive/checksum identity mismatch")
        with tarfile.open(archive) as package:
            if sorted(package.getnames()) != ["NIGHTLY-SOURCE.json", "caboodle", "tambo"]:
                raise ValueError("candidate archive contains unexpected paths")
            source = json.load(package.extractfile("NIGHTLY-SOURCE.json"))
        if source.get("source_sha") != sha or source.get("version") != version:
            raise ValueError("candidate archive source identity mismatch")
        rows.append((platform, archive.resolve().as_uri(), digest))
    return generate.render("caboodle-nightly", row, version, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("version")
    parser.add_argument("sha")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    text = candidate(root, args.assets, args.version, args.sha)
    (root / "Formula/caboodle-nightly.rb").write_text(text)

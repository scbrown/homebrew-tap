#!/usr/bin/env python3
"""Apply a recorded version-only patch to an exact Caboodle source checkout."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tomllib


def prepare(root, sha, version):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("source SHA must be a full commit identity")
    if not re.fullmatch(r"\d+\.\d+\.\d+-nightly\.\d{14}\." + sha[:12], version):
        raise ValueError("nightly version must identify its source SHA and UTC build time")
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != sha or subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"]):
        raise ValueError("nightly source must be the clean, exact selected commit")
    manifest = root / "Cargo.toml"
    lock = root / "Cargo.lock"
    package = tomllib.loads(manifest.read_text())["package"]
    name, old = package["name"], package["version"]
    if version.split("-nightly.")[0] != old:
        raise ValueError("nightly base version differs from the source package")
    text, count = re.subn(r'(?m)^version = "' + re.escape(old) + r'"$',
                          f'version = "{version}"', manifest.read_text(), count=1)
    if count != 1:
        raise ValueError("cannot identify the package version")
    pattern = r'(\[\[package\]\]\nname = "' + re.escape(name) + r'"\nversion = ")' + re.escape(old) + '"'
    locked, count = re.subn(pattern, lambda m: m[1] + version + '"', lock.read_text())
    if count != 1:
        raise ValueError("cannot identify the single root package in Cargo.lock")
    manifest.write_text(text)
    lock.write_text(locked)
    (root / "NIGHTLY-SOURCE.json").write_text(json.dumps({
        "repository": "scbrown/tambo", "source_sha": sha, "package": name,
        "source_version": old, "version": version,
        "patch": "Cargo.toml and the root Cargo.lock package version only",
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("sha")
    parser.add_argument("version")
    args = parser.parse_args()
    prepare(args.root, args.sha, args.version)

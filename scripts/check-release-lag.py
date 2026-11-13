#!/usr/bin/env python3
"""Read-only stable release/formula lag check; never generates or installs."""
from datetime import datetime, timezone
import json
import re
import sys

from generate import ROOT, latest_stable


def verdict(row, release, formula, now, platform_count=2):
    tag = release["tag_name"]
    prefix = row["tag_prefix"]
    if (release.get("draft") or release.get("prerelease")
            or not re.fullmatch(re.escape(prefix) + r"\d+\.\d+\.\d+", tag)):
        raise ValueError("not a stable release")
    published = datetime.strptime(release["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp()
    if published > now:
        raise ValueError("release timestamp is in the future")
    # The generator emits one source URL per architecture (or one wheel).
    # Ignore dependency resource URLs; never execute formula Ruby to inspect it.
    urls = re.findall(r'^\s*url\s+"(https://github\.com/[^"\s]+/releases/download/[^"\s]+)"',
                      formula, re.MULTILINE)
    expected_urls = 1 if row.get("kind") in ("python", "python-wheels") else platform_count
    if len(urls) != expected_urls:
        raise ValueError("incomplete release URLs in formula")
    expected = row["repo"].rsplit("/", 1)[1]
    tags = []
    for url in urls:
        match = re.fullmatch(r"https://github\.com/(scbrown|intigraph)/([^/]+)/releases/download/([^/]+)/[^/]+", url)
        if not match or match[2] != expected:
            raise ValueError("formula source repository differs")
        tags.append(match[3])
    current = all(value == tag for value in tags)
    age = now - published
    return {"release": tag, "formula_tags": sorted(set(tags)),
            "lag_seconds": 0 if current else int(age),
            "state": "current" if current else "late" if age > 7200 else "pending"}


def check(root, now):
    manifest = json.loads((root / "manifest.json").read_text())
    rows = manifest["formulas"]
    if not isinstance(rows, dict) or not rows or not manifest["platforms"]:
        raise ValueError("empty formula/platform coverage")
    releases, results = {}, {}
    for name, row in rows.items():
        try:
            key = (row["repo"], row["tag_prefix"])
            if key not in releases:
                releases[key] = latest_stable(*key)
            results[name] = verdict(row, releases[key],
                                    (root / "Formula" / (name + ".rb")).read_text(), now,
                                    len(manifest["platforms"]))
        except Exception:
            # Remote output and exception text are not diagnostic identifiers.
            results[name] = {"state": "unknown"}
    return results


def main():
    results = check(ROOT, datetime.now(timezone.utc).timestamp())
    print(json.dumps(results, sort_keys=True))
    for name, result in results.items():
        if result["state"] == "late":
            print(f"::error::{name}: tap formula is more than 2h behind its stable release")
        elif result["state"] == "unknown":
            print(f"::error::{name}: release/formula lag could not be measured")
    return 2 if any(r["state"] == "unknown" for r in results.values()) else int(
        any(r["state"] == "late" for r in results.values()))


if __name__ == "__main__":
    sys.exit(main())

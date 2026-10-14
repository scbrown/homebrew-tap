#!/usr/bin/env python3
"""Assert that `brew info --json=v2 --installed` reports a formula from this tap.

This is the ownership receipt caboodle records, so CI proves it.
"""
import json
import subprocess
import sys

full_name = sys.argv[1]
info = json.loads(subprocess.run(["brew", "info", "--json=v2", "--installed"],
                                 check=True, capture_output=True, text=True).stdout)
rows = [f for f in info["formulae"] if f["full_name"] == full_name]
if len(rows) != 1 or not rows[0].get("installed"):
    sys.exit(f"{full_name}: not reported as installed by brew info")
print(f"{full_name} {rows[0]['installed'][0]['version']} tap={rows[0]['tap']}")

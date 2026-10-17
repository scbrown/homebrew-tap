#!/usr/bin/env python3
"""Offline before/after demonstration; no release or installation is requested."""
import importlib.util
from pathlib import Path
import subprocess
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
baseline = {"__name__": "baseline", "__file__": str(root / "scripts/generate.py")}
exec(subprocess.check_output(["git", "-C", str(root), "show",
                            "4f21c25bfccdf973cec2174617ea1b62f4a62454:scripts/generate.py"]), baseline)
spec = importlib.util.spec_from_file_location("generate", root / "scripts/generate.py")
current = importlib.util.module_from_spec(spec)
spec.loader.exec_module(current)
print("before preview class:", baseline["class_name"]("caboodle@nightly"))
print("after preview class:", current.class_name("caboodle-nightly"))
print("stable class control:", current.class_name("caboodle"))
releases = [
    {"tag_name": "v0.3.7", "draft": False, "prerelease": False},
    {"tag_name": "v9.0.0", "draft": False, "prerelease": True},
    {"tag_name": "caboodle-nightly-v0.3.7-nightly.20261017010000.aaaaaaaaaaaa",
     "draft": False, "prerelease": True},
]
with patch.object(current, "get", return_value=releases):
    print("stable release control:", current.latest_stable("example/fixture", "v")["tag_name"])
    print("preview selection:", current.latest_preview("example/fixture", "caboodle-nightly-v")["tag_name"])
print("Scope: offline generator controls; no publish, dispatch, brew or host install.")

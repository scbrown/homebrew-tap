#!/usr/bin/env python3
"""Offline lag controls: no installs, dispatches, tokens or network."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("release_lag", Path(__file__).with_name("check-release-lag.py"))
lag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lag)
ROW = {"repo": "intigraph/tool", "tag_prefix": "tool-v"}
RELEASE = {"tag_name": "tool-v1.2.3", "published_at": "2026-01-01T00:00:00Z",
           "draft": False, "prerelease": False}
STAMP = 1767225600


def formula(tag, owner="intigraph"):
    return "\n".join(f'  url "https://github.com/{owner}/tool/releases/download/{tag}/{arch}.tar.gz"'
                     for arch in ("arm", "intel"))


class Lag(unittest.TestCase):
    def test_cli_is_quiet_current_and_fails_late_or_unknown(self):
        for state, code, error in (("current", 0, False), ("pending", 0, False),
                                   ("late", 1, True), ("unknown", 2, True)):
            output = io.StringIO()
            with patch.object(lag, "check", return_value={"tool": {"state": state}}), contextlib.redirect_stdout(output):
                self.assertEqual(lag.main(), code)
            self.assertEqual("::error::" in output.getvalue(), error)

    def test_current_is_quiet_even_for_old_release_and_legacy_owner(self):
        result = lag.verdict(ROW, RELEASE, formula("tool-v1.2.3", "scbrown"), STAMP + 999999)
        self.assertEqual((result["state"], result["lag_seconds"]), ("current", 0))

    def test_real_lag_threshold_is_publication_age_not_check_age(self):
        for age, state in ((7199, "pending"), (7200, "pending"), (7201, "late")):
            self.assertEqual(lag.verdict(ROW, RELEASE, formula("tool-v1.2.2"), STAMP + age)["state"], state)

    def test_mixed_architectures_are_not_current(self):
        text = formula("tool-v1.2.3").replace("tool-v1.2.3/intel", "tool-v1.2.2/intel")
        self.assertEqual(lag.verdict(ROW, RELEASE, text, STAMP + 7201)["state"], "late")

    def test_missing_or_foreign_formula_and_future_clock_are_unknown(self):
        for text, now in (("", STAMP), (formula("tool-v1.2.3").splitlines()[0], STAMP),
                          (formula("tool-v1.2.3").replace("/tool/", "/foreign/"), STAMP),
                          (formula("tool-v1.2.3"), STAMP - 1)):
            with self.assertRaises(ValueError):
                lag.verdict(ROW, RELEASE, text, now)

    def test_drafts_and_prereleases_are_not_stable(self):
        for field in ("draft", "prerelease"):
            with self.assertRaises(ValueError):
                lag.verdict(ROW, dict(RELEASE, **{field: True}), formula("tool-v1.2.3"), STAMP)

    def test_read_failure_does_not_hide_other_formula_or_read_same_repo_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("Formula").mkdir()
            root.joinpath("manifest.json").write_text(json.dumps({
                "formulas": {"one": ROW, "two": ROW}, "platforms": {"arm": {}, "intel": {}}}))
            root.joinpath("Formula/two.rb").write_text(formula("tool-v1.2.3"))
            with patch.object(lag, "latest_stable", return_value=RELEASE) as fetch:
                results = lag.check(root, STAMP)
            fetch.assert_called_once_with("intigraph/tool", "tool-v")
            self.assertEqual(results["one"]["state"], "unknown")
            self.assertEqual(results["two"]["state"], "current")

    def test_wheel_resource_urls_are_not_source_versions(self):
        text = formula("tool-v1.2.3").splitlines()[0] + '\n url "https://files.pythonhosted.org/dependency.whl"'
        self.assertEqual(lag.verdict(dict(ROW, kind="python-wheels"), RELEASE, text, STAMP)["state"], "current")


if __name__ == "__main__":
    unittest.main()

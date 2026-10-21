"""Release admission controls; never fetch or publish in these tests."""
import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path
import subprocess
import tempfile
import tomllib
import hashlib
import io
import json
import tarfile
import os
import sys
import textwrap

spec = importlib.util.spec_from_file_location("generate", __file__.replace("test-nightly.py", "generate.py"))
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)
spec = importlib.util.spec_from_file_location("prepare", __file__.replace("test-nightly.py", "prepare-nightly.py"))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
spec = importlib.util.spec_from_file_location("candidate", __file__.replace("test-nightly.py", "render-nightly-candidate.py"))
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def release(tag, prerelease=False, draft=False):
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft}


class ReleaseControls(unittest.TestCase):
    def test_update_trusts_conflict_peers_before_install_and_preserves_failures(self):
        workflow = Path(__file__).resolve().parents[1] / '.github/workflows/update.yml'
        section = workflow.read_text().split('      - name: Install, test and audit changed formulas\n', 1)[1]
        block = section.split('        run: |\n', 1)[1].split('      - name: Commit\n', 1)[0]
        command = textwrap.dedent(block)
        for failure in ('', 'trust', 'audit'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); tools = root / 'bin'; tools.mkdir()
                (root / 'Formula').mkdir()
                for name in ('caboodle', 'caboodle-nightly'):
                    (root / 'Formula' / (name + '.rb')).write_text('# private fixture\n')
                brew = tools / 'brew'
                brew.write_text('#!' + sys.executable + '\n' + r"""
import os, sys, pathlib, json
root = pathlib.Path(os.environ['FIXTURE'])
args = sys.argv[1:]
if args == ['--repository']:
    print(root / 'brew'); sys.exit(0)
with (root / 'calls').open('a') as log: log.write(json.dumps(args) + '\n')
if args[0] == 'trust':
    if os.environ['FAILURE'] == 'trust': sys.exit(17)
    with (root / 'trusted').open('a') as stream: stream.write(args[-1] + '\n')
if args[0] == 'install':
    trusted = (root / 'trusted').read_text().splitlines() if (root / 'trusted').exists() else []
    if 'scbrown/tap/caboodle-nightly' not in trusted:
        print('untrusted conflict peer', file=sys.stderr); sys.exit(18)
if args[0] == 'audit' and os.environ['FAILURE'] == 'audit': sys.exit(19)
""")
                brew.chmod(0o755)
                git = tools / 'git'
                git.write_text('#!/bin/sh\nif [ "$1" = diff ]; then echo Formula/caboodle.rb; fi\n')
                git.chmod(0o755)
                env = os.environ | {'PATH': str(tools) + os.pathsep + os.environ['PATH'],
                                    'FIXTURE': str(root), 'FAILURE': failure, 'GITHUB_WORKSPACE': str(root)}
                result = subprocess.run(['bash', '-c', command], cwd=root, env=env, capture_output=True, text=True)
                calls = [json.loads(line) for line in (root / 'calls').read_text().splitlines()]
                if failure == 'trust':
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(any(call[0] == 'install' for call in calls))
                else:
                    self.assertEqual(result.returncode, 19 if failure == 'audit' else 0, result.stderr)
                    first_install = next(i for i, call in enumerate(calls) if call[0] == 'install')
                    self.assertEqual({call[-1] for call in calls[:first_install] if call[0] == 'trust'},
                                     {'scbrown/tap/caboodle', 'scbrown/tap/caboodle-nightly'})
                    self.assertIn(['test', 'scbrown/tap/caboodle'], calls)
                    self.assertIn(['audit', '--strict', 'scbrown/tap/caboodle'], calls)

    def test_empty_brew_fixture_is_read_only(self):
        fixture = Path(__file__).with_name("empty-brew-fixture.sh")
        self.assertEqual(subprocess.run(["sh", str(fixture), "update", "--quiet"], capture_output=True).returncode, 0)
        receipt = subprocess.run(["sh", str(fixture), "info", "--json=v2", "scbrown/tap/quipu"], capture_output=True, check=True)
        self.assertEqual(json.loads(receipt.stdout), {"formulae": []})
        self.assertEqual(subprocess.run(["sh", str(fixture), "install", "scbrown/tap/quipu"], capture_output=True).returncode, 93)

    def test_stable_never_adopts_preview_or_draft(self):
        rows = [release("v0.3.7"), release("v9.0.0", draft=True),
                release("v9.0.0", prerelease=True), release("v0.3.8")]
        with patch.object(generate, "get", return_value=rows):
            self.assertEqual(generate.latest_stable("a/b", "v")["tag_name"], "v0.3.8")

    def test_preview_requires_published_exact_nightly_identity(self):
        old = "caboodle-nightly-v0.3.7-nightly.20261017000000.aaaaaaaaaaaa"
        new = "caboodle-nightly-v0.3.7-nightly.20261017010000.bbbbbbbbbbbb"
        rows = [release(old, True), release(new, True), release("caboodle-nightly-v9.0.0"),
                release(new.replace("010000", "020000"), True, True),
                release("caboodle-nightly-v0.3.7-nightly.latest", True)]
        with patch.object(generate, "get", return_value=rows):
            self.assertEqual(generate.latest_preview("a/b", "caboodle-nightly-v")["tag_name"], new)
        with patch.object(generate, "get", return_value=[release(new)]):
            with self.assertRaises(generate.Refused):
                generate.latest_preview("a/b", "caboodle-nightly-v")

    def test_preview_class_and_version_readback(self):
        self.assertEqual(generate.class_name("caboodle"), "Caboodle")
        self.assertEqual(generate.class_name("caboodle-nightly"), "CaboodleNightly")
        self.assertEqual(generate.class_name("caboodle@0.3"), "CaboodleAT03")
        with self.assertRaises(generate.Refused):
            generate.class_name("caboodle@nightly")
        row = {"desc": "Nightly Caboodle", "repo": "a/b", "bins": ["caboodle"],
               "license": "MIT", "version_args": "--version", "explicit_version": True,
               "conflicts_with": "caboodle"}
        version = "0.3.7-nightly.20261017010000.bbbbbbbbbbbb"
        text = generate.render("caboodle-nightly", row, version,
                               [("macos-arm", "https://example.test/arm", "a" * 64),
                                ("macos-intel", "https://example.test/intel", "b" * 64)])
        self.assertIn("class CaboodleNightly < Formula", text)
        self.assertIn(f'version "{version}"', text)
        self.assertIn('conflicts_with "caboodle"', text)
        self.assertIn("assert_match version.to_s", text)


class SourceControls(unittest.TestCase):
    def source(self, root):
        (root / "Cargo.toml").write_text('[package]\nname = "tambo"\nversion = "0.3.7"\n[dependencies]\nother = "0.3.7"\n')
        (root / "Cargo.lock").write_text('version = 3\n[[package]]\nname = "other"\nversion = "0.3.7"\n[[package]]\nname = "tambo"\nversion = "0.3.7"\n')
        def git(*args):
            return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "fixture")
        return git("rev-parse", "HEAD").decode().strip()

    def test_only_root_versions_change_and_dirty_source_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = self.source(root)
            version = f"0.3.7-nightly.20261017010000.{sha[:12]}"
            prepare.prepare(root, sha, version)
            manifest = tomllib.loads((root / "Cargo.toml").read_text())
            lock = tomllib.loads((root / "Cargo.lock").read_text())
            self.assertEqual(manifest["package"]["version"], version)
            self.assertEqual(manifest["dependencies"]["other"], "0.3.7")
            self.assertEqual([p["version"] for p in lock["package"]], ["0.3.7", version])
            with self.assertRaises(ValueError):
                prepare.prepare(root, sha, version)

    def test_wrong_commit_refuses_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source(root)
            before = {p.name: p.read_bytes() for p in root.glob("Cargo.*")}
            sha = "a" * 40
            with self.assertRaises(ValueError):
                prepare.prepare(root, sha, "0.3.7-nightly.20261017010000." + sha[:12])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.glob("Cargo.*")})
            self.assertFalse((root / "NIGHTLY-SOURCE.json").exists())


class CandidateControls(unittest.TestCase):
    sha = "a" * 40
    version = "0.3.7-nightly.20261017010000." + sha[:12]
    root = Path(__file__).resolve().parents[1]

    def archive(self, assets, target, source_sha=None):
        archive = assets / f"caboodle-v{self.version}-{target}.tar.gz"
        metadata = json.dumps({"source_sha": source_sha or self.sha, "version": self.version}).encode()
        with tarfile.open(archive, "w:gz") as package:
            for name, data in [("caboodle", b"fixture"), ("tambo", b"fixture"),
                               ("NIGHTLY-SOURCE.json", metadata)]:
                item = tarfile.TarInfo(name)
                item.size = len(data)
                package.addfile(item, io.BytesIO(data))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n")
        return archive

    def test_both_platforms_and_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            self.archive(assets, "aarch64-apple-darwin")
            self.archive(assets, "x86_64-apple-darwin")
            text = candidate.candidate(self.root, assets, self.version, self.sha)
            self.assertIn("CaboodleNightly", text)
            self.assertEqual(text.count("file://"), 2)
            self.archive(assets, "x86_64-apple-darwin", "b" * 40)
            with self.assertRaisesRegex(ValueError, "source identity mismatch"):
                candidate.candidate(self.root, assets, self.version, self.sha)

    def test_partial_or_corrupt_archive_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            arm = self.archive(assets, "aarch64-apple-darwin")
            with self.assertRaises(FileNotFoundError):
                candidate.candidate(self.root, assets, self.version, self.sha)
            self.archive(assets, "x86_64-apple-darwin")
            arm.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum identity mismatch"):
                candidate.candidate(self.root, assets, self.version, self.sha)


if __name__ == "__main__":
    unittest.main()

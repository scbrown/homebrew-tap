# Scheduled update conflict-peer trust

This is a source-fixture transcript, not a recording or an installed Mac result.
No terminal recording tool was used. The fixture executes the actual update
workflow shell block with private `brew` and `git` programs. Only the stable
formula changes; installing it loads the unchanged nightly conflict peer.

Reproduce with the regression test on the candidate:

```sh
python3 scripts/test-nightly.py ReleaseControls.test_update_trusts_conflict_peers_before_install_and_preserves_failures
```

On base `4169b3fc8b07c192643297c1333eed83ef975df5`, adding this same regression
test without changing the workflow produced:

```text
AssertionError: 18 != 0 : untrusted conflict peer
Ran 1 test in 0.130s
FAILED (failures=3)
```

After the workflow preflight, the full source suite produced:

```text
Ran 9 tests in 0.408s
OK
```

The successful fixture verifies both checked-out formula identities are trusted
before the first install, then runs the unchanged install, test and strict audit.
A trust failure prevents installation; an audit failure retains its failing exit.
The candidate revision is the commit carrying this file. These private controls
do not prove real Homebrew installation, a natural scheduled run, or delivery.
Retain this small transcript with the source regression; no external artifact
store or new retention service is required.

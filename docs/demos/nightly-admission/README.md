# Nightly admission

Run `python3 scripts/demo-nightly.py` from a clone with the baseline commit
available. [The transcript](output.log) shows the previously invalid preview
`caboodle@nightly` spelling replaced by `caboodle-nightly` / `CaboodleNightly`, with the stable class and stable release
selection kept as positive controls. The preview selects only a published,
timestamped prerelease tied to a source commit.

`python3 scripts/test-nightly.py` additionally checks partial archives, corrupt
bytes, a mismatched source commit, and the version-only source patch. The native
candidate build reports its full nightly version. Actual macOS release builds,
Homebrew installation and publication are separate CI/runtime checks; this
offline demonstration does not claim they ran.

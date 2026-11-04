# scbrown/tap

Homebrew formulas for the agent tool stack: prebuilt macOS archives for Apple
silicon and Intel, each pinned to the sha256 its own release publishes.

```sh
brew install scbrown/tap/tambo
```

| Formula | Commands | Source |
| --- | --- | --- |
| `bobbin` | `bobbin` | [scbrown/bobbin](https://github.com/scbrown/bobbin) |
| `caboodle` | `caboodle` (the former name of `tambo`) | [scbrown/tambo](https://github.com/scbrown/tambo) |
| `chaski` | `chaski`, `chaski-event`, `chaski-once` | [intigraph/chaski](https://github.com/intigraph/chaski) |
| `desire-path` | `dp` | [scbrown/desire-path](https://github.com/scbrown/desire-path) |
| `quipu` | `quipu`, `quipu-server`, `qp` | [scbrown/quipu](https://github.com/scbrown/quipu) |
| `seeds` | `sd` | [scbrown/seeds](https://github.com/scbrown/seeds) |
| `shantytown` | `st` | [scbrown/shantytown](https://github.com/scbrown/shantytown) |
| `tambo` | `tambo` | [scbrown/tambo](https://github.com/scbrown/tambo) |
| `yupana` | `yupana`, `hank` | [scbrown/yupana](https://github.com/scbrown/yupana) |

## How formulas stay current

Formulas are generated, never hand-edited. Once an hour the `update` workflow
runs `scripts/generate.py`, which reads each repository's latest stable release
from `manifest.json`, downloads every macOS asset and checks it against the
release's own `SHA256SUMS` or `.sha256` sidecar. It refuses a formula whose asset
is missing or whose bytes do not match, and leaves the previous formula in
place. Changed formulas are installed, tested and audited on macOS before they
are committed. A new release reaches `brew upgrade` within about an hour.

## Holding a version

```sh
brew pin quipu      # keep the installed version through brew upgrade
brew unpin quipu
```

## Caboodle preview channel

Homebrew uses `caboodle-nightly` (rather than a nonnumeric `@nightly` suffix).
`caboodle-nightly` is an opt-in preview built daily from an exact `scbrown/tambo`
main commit. Both macOS architectures run the upstream tests and build before
an immutable prerelease is published here. Its version includes the UTC build
time and source commit; `NIGHTLY-SOURCE.json` records the version-only build
patch. The formula checks the published archive checksums before it changes.
The stable generator excludes prereleases.

After the first successful nightly publication, switch with:

```sh
brew unlink caboodle && brew install scbrown/tap/caboodle-nightly
```

Return to an already installed stable formula with:

```sh
brew unlink caboodle-nightly && brew link caboodle
```

Hold the installed preview through upgrades with `brew pin caboodle-nightly`;
resume with `brew unpin caboodle-nightly`. Other formulas currently offer the
stable and pinned channels. A preview is never selected by the stable Mac stack
consumer: installing a preview is an explicit user choice.

## Development

```sh
python3 scripts/generate.py --check   # report drift without writing
python3 scripts/generate.py quipu     # regenerate one formula
python3 scripts/generate.py --preview caboodle-nightly
python3 scripts/test-nightly.py       # offline release/source admission controls
```

`qp` and `hank` are relative links beside `quipu` and `yupana`; each formula's
`brew test` checks the link.

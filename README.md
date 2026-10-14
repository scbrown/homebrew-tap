# scbrown/tap

Homebrew formulas for the agent tool stack: prebuilt macOS archives for Apple
silicon and Intel, each pinned to the sha256 its own release publishes.

```sh
brew install scbrown/tap/caboodle
```

| Formula | Commands | Source |
| --- | --- | --- |
| `bobbin` | `bobbin` | [scbrown/bobbin](https://github.com/scbrown/bobbin) |
| `caboodle` | `caboodle` | [scbrown/caboodle](https://github.com/scbrown/caboodle) |
| `desire-path` | `dp` | [scbrown/desire-path](https://github.com/scbrown/desire-path) |
| `quipu` | `quipu`, `quipu-server`, `qp` | [scbrown/quipu](https://github.com/scbrown/quipu) |
| `seeds` | `sd` | [scbrown/seeds](https://github.com/scbrown/seeds) |
| `shantytown` | `st` | [scbrown/shantytown](https://github.com/scbrown/shantytown) |
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

## Development

```sh
python3 scripts/generate.py --check   # report drift without writing
python3 scripts/generate.py quipu     # regenerate one formula
```

`qp` and `hank` are relative links beside `quipu` and `yupana`; each formula's
`brew test` checks the link.

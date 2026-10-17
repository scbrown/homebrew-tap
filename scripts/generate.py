#!/usr/bin/env python3
"""Regenerate Formula/*.rb from manifest.json and each repo's latest stable release.

Every asset sha256 comes from the release's own checksum file or sidecar, and is
then checked against the downloaded bytes. A formula is rewritten only when its
release changed. Any missing asset or checksum mismatch refuses that formula and
leaves the existing file untouched; the exit status is 1 if anything refused.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import zipfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"


class Refused(RuntimeError):
    pass


def get(url, *, raw=False):
    """Fetch with curl: present on every runner, and the token stays out of argv.

    The whole request config, including any Authorization header, goes to curl
    on stdin, so it never appears in a process listing.
    """
    config = [f'url = "{url}"', "fail", "silent", "show-error", "location",
              "max-time = 300", "retry = 3",
              'header = "User-Agent: scbrown-homebrew-tap"',
              'header = "Accept: ' + ("application/octet-stream" if raw else "application/vnd.github+json") + '"']
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(API):
        config.append(f'header = "Authorization: Bearer {token}"')
    result = subprocess.run(["curl", "--config", "-"], input="\n".join(config).encode(),
                            capture_output=True)
    if result.returncode:
        raise Refused(f"fetch failed ({result.returncode}): {result.stderr.decode(errors='replace').strip()[:200]}")
    return result.stdout if raw else json.loads(result.stdout)


def latest_stable(repo, prefix):
    releases = get(f"{API}/repos/{repo}/releases?per_page=30")
    stable = [r for r in releases if not r["draft"] and not r["prerelease"]
              and r["tag_name"].startswith(prefix)
              and re.fullmatch(r"\d+\.\d+\.\d+", r["tag_name"][len(prefix):])]
    if not stable:
        raise Refused(f"{repo}: no stable release with prefix {prefix!r}")
    return max(stable, key=lambda r: tuple(int(x) for x in r["tag_name"][len(prefix):].split(".")))


def latest_preview(repo, prefix):
    """Only explicitly published, immutable nightly prereleases enter this lane."""
    releases = get(f"{API}/repos/{repo}/releases?per_page=30")
    previews = [r for r in releases if not r["draft"] and r["prerelease"]
                and r["tag_name"].startswith(prefix)
                and re.fullmatch(r"\d+\.\d+\.\d+-nightly\.\d{14}\.[0-9a-f]{12}",
                                 r["tag_name"][len(prefix):])]
    if not previews:
        raise Refused(f"{repo}: no published nightly release with prefix {prefix!r}")
    return max(previews, key=lambda r: r["tag_name"][len(prefix):].split("-nightly.")[1])


def parse_sums(text):
    sums = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            sums[parts[1].lstrip("*").rsplit("/", 1)[-1]] = parts[0]
    return sums


def resolve(name, row, platforms, blobs=None):
    """Return (version, [(platform, url, sha256)]) verified against the release.

    When ``blobs`` is a dict, the verified bytes of each asset are kept in it.
    """
    select = latest_preview if row.get("channel") == "nightly" else latest_stable
    release = select(row["repo"], row["tag_prefix"])
    tag = release["tag_name"]
    ver = tag[len(row["tag_prefix"]):]
    assets = {a["name"]: a for a in release["assets"]}
    wanted = []
    for key, plat in platforms.items():
        asset = row["asset"].format(tag=tag, ver=ver, **plat)
        wanted.append((key, asset))
        if row.get("kind") in ("python", "python-wheels"):
            break  # one universal wheel
    sums = {}
    if row["sums"] != "sidecar":
        if row["sums"] not in assets:
            raise Refused(f"{name} {tag}: checksum file {row['sums']} missing")
        sums = parse_sums(get(assets[row["sums"]]["url"], raw=True).decode())
    out = []
    for key, asset in wanted:
        if asset not in assets:
            raise Refused(f"{name} {tag}: asset {asset} missing")
        if row["sums"] == "sidecar":
            side = asset + ".sha256"
            if side not in assets:
                raise Refused(f"{name} {tag}: sidecar {side} missing")
            expected = get(assets[side]["url"], raw=True).decode().split()[0]
        else:
            expected = sums.get(asset)
        if not expected or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise Refused(f"{name} {tag}: no checksum for {asset}")
        data = get(assets[asset]["url"], raw=True)
        actual = hashlib.sha256(data).hexdigest()
        if blobs is not None:
            blobs[asset] = data
        if actual != expected:
            raise Refused(f"{name} {tag}: {asset} sha256 {actual} != published {expected}")
        out.append((key, assets[asset]["browser_download_url"], actual))
    return ver, out


PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.+!-]*)")


def wheel_contents(name, wheel):
    """Console scripts and exact dependency pins read from a release wheel.

    Any dependency that is not a bare exact pin (a range, an extra, or an
    environment marker) is refused: the formula must be reproducible.
    """
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        info = {n.rsplit("/", 1)[-1]: n for n in archive.namelist() if ".dist-info/" in n}
        metadata = archive.read(info["METADATA"]).decode()
        entries = archive.read(info["entry_points.txt"]).decode() if "entry_points.txt" in info else ""
    pins = []
    for line in metadata.splitlines():
        if line.startswith("Requires-Dist:"):
            spec = line.split(":", 1)[1].strip()
            match = PIN.fullmatch(spec)
            if not match:
                raise Refused(f"{name}: dependency {spec!r} is not an exact == pin")
            pins.append(match.groups())
    scripts, section = [], None
    for line in entries.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[console_scripts]" and "=" in line:
            command, target = (part.strip() for part in line.split("=", 1))
            module, _, function = target.partition(":")
            scripts.append((command, module, function))
    if not scripts:
        raise Refused(f"{name}: wheel declares no console scripts")
    return sorted(scripts), sorted(pins)


def pypi_wheels(name, project, version, python):
    """Verified wheel resources for one pin: universal, or one per macOS arch."""
    files = get(f"https://pypi.org/pypi/{project}/{version}/json")["urls"]
    universal = [f for f in files if f["filename"].endswith("-py3-none-any.whl")]
    tag = "cp" + python.replace(".", "")
    picks = ({"all": universal[0]} if universal else {
        "macos-arm": next((f for f in files if f"-{tag}-{tag}-macosx_" in f["filename"]
                           and f["filename"].endswith("_arm64.whl")), None),
        "macos-intel": next((f for f in files if f"-{tag}-{tag}-macosx_" in f["filename"]
                             and f["filename"].endswith("_x86_64.whl")), None)})
    out = {}
    for key, f in picks.items():
        if f is None:
            raise Refused(f"{name}: no {tag} macOS wheel ({key}) for {project}=={version}")
        actual = hashlib.sha256(get(f["url"], raw=True)).hexdigest()
        if actual != f["digests"]["sha256"]:
            raise Refused(f"{name}: {f['filename']} sha256 {actual} != PyPI {f['digests']['sha256']}")
        out[key] = (f["url"], actual)
    return out


def render_wheels(name, row, ver, rows, scripts, deps):
    """A formula that unpacks verified wheels into libexec; no pip, no build."""
    (_, url, sha), = rows
    py = row["python"]
    wheel = url.rsplit("/", 1)[-1].replace(ver, "#{version}")
    lines = [
        "# typed: false",
        "# frozen_string_literal: true",
        "",
        "# GENERATED by scripts/generate.py from manifest.json; do not edit by hand.",
        f"class {class_name(name)} < Formula",
        f'  desc "{row["desc"]}"',
        f'  homepage "https://github.com/{row["repo"]}"',
        f'  url "{url}", using: :nounzip',
        f'  sha256 "{sha}"',
        f'  license "{row["license"]}"',
        "",
        f'  depends_on "python@{py}"',
    ]

    def resource(project, pin_url, pin_sha, indent):
        pad = " " * indent
        return [f'{pad}resource "{project.lower()}" do',
                f'{pad}  url "{pin_url}", using: :nounzip',
                f'{pad}  sha256 "{pin_sha}"',
                f"{pad}end"]

    shared = [(p, v, w) for p, v, w in deps if "all" in w]
    per_arch = [(p, v, w) for p, v, w in deps if "all" not in w]
    for project, _, wheels in shared:
        lines += [""] + resource(project, *wheels["all"], 2)
    for block, key in (("on_arm", "macos-arm"), ("on_intel", "macos-intel")):
        if per_arch:
            lines += ["", f"  {block} do"]
            for project, _, wheels in per_arch:
                lines += resource(project, *wheels[key], 4)
            lines.append("  end")
    lines += [
        "",
        "  def install",
        f'    python = Formula["python@{py}"].opt_bin/"python{py}"',
        '    site = libexec/"site"',
        "    site.mkpath",
        f'    system python, "-m", "zipfile", "-e", buildpath/"{wheel}", site',
        "    resources.each do |r|",
        '      r.stage { system python, "-m", "zipfile", "-e", Dir["*.whl"].first, site }',
        "    end",
    ]
    for command, module, function in scripts:
        lines += [
            f'    (bin/"{command}").write <<~SH',
            "      #!/bin/bash",
            f'      PYTHONPATH="#{{site}}" exec "#{{python}}" -c "import sys; from {module} import {function}; sys.exit({function}())" "$@"',
            "    SH",
            f'    chmod 0755, bin/"{command}"',
        ]
    lines += ["  end", "", "  test do"]
    first = row["version_bin"]
    lines.append(f'    assert_match version.to_s, shell_output("#{{bin}}/{first} {row["version_args"]}")')
    lines += [f'    system bin/"{command}", "--help"' for command, _, _ in scripts if command != first]
    for project, _, _ in deps:
        module = row.get("imports", {}).get(project, project.lower())
        lines.append(f'    system Formula["python@{py}"].opt_bin/"python{py}", "-c", '
                     f'"import sys; sys.path.insert(0, \'#{{libexec}}/site\'); import {module}"')
    lines += ["  end", "end", ""]
    return "\n".join(lines)


def class_name(name):
    base, sep, version = name.partition("@")
    if sep and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
        raise Refused("Homebrew @ suffixes require a numeric version; use a -nightly name")
    return "".join(part.capitalize() for part in re.split(r"[-_]", base)) + (
        "AT" + version.replace(".", "") if sep else "")


def render(name, row, ver, rows):
    lines = [
        "# typed: false",
        "# frozen_string_literal: true",
        "",
        "# GENERATED by scripts/generate.py from manifest.json; do not edit by hand.",
        f"class {class_name(name)} < Formula",
    ]
    lines += [
        f'  desc "{row["desc"]}"',
        f'  homepage "https://github.com/{row.get("homepage_repo", row["repo"])}"',
    ]
    if row.get("kind") == "python":
        # Pure-python wheel with no dependencies: unpack it and call its entry
        # point. Homebrew venvs ship without pip and refuse binary wheels, so
        # this avoids pip and any build backend at install time.
        (_, url, sha), = rows
        wheel = url.rsplit("/", 1)[-1].replace(ver, "#{version}")
        module, func = row["entry"].split(":")
        lines += [
            f'  url "{url}", using: :nounzip',
            f'  sha256 "{sha}"',
            *([f'  version "{ver}"'] if row.get("explicit_version") else []),
            f'  license "{row["license"]}"',
            "",
            '  depends_on "python@3.13"',
            "",
            "  def install",
            '    python = Formula["python@3.13"].opt_bin/"python3.13"',
            '    (libexec/"site").mkpath',
            f'    system python, "-m", "zipfile", "-e", buildpath/"{wheel}", libexec/"site"',
        ]
        for b in row["bins"]:
            lines += [
                f'    (bin/"{b}").write <<~SH',
                "      #!/bin/bash",
                f'      PYTHONPATH="#{{libexec}}/site" exec "#{{python}}" -c "import sys; from {module} import {func}; sys.exit({func}())" "$@"',
                "    SH",
                f'    chmod 0755, bin/"{b}"',
            ]
        lines.append("  end")
    else:
        by = dict((k, (u, s)) for k, u, s in rows)
        lines += [
            *([f'  version "{ver}"'] if row.get("explicit_version") else []),
            f'  license "{row["license"]}"',
            *([f'  conflicts_with "{row["conflicts_with"]}", because: "both install the same commands"']
              if row.get("conflicts_with") else []),
            "",
            "  on_macos do",
            "    on_arm do",
            f'      url "{by["macos-arm"][0]}"',
            f'      sha256 "{by["macos-arm"][1]}"',
            "    end",
            "    on_intel do",
            f'      url "{by["macos-intel"][0]}"',
            f'      sha256 "{by["macos-intel"][1]}"',
            "    end",
            "  end",
            "",
            "  def install",
        ]
        if row.get("libexec"):
            lines.append('    libexec.install Dir["*"]')
            lines += [f'    bin.install_symlink libexec/"{b}"' for b in row["bins"]]
        else:
            lines.append("    bin.install " + ", ".join(f'"{b}"' for b in row["bins"]))
        # Aliases are relative links beside their target (caboodle verifies qp -> quipu).
        lines += [f'    bin.install_symlink bin/"{target}" => "{alias}"'
                  for alias, target in sorted(row.get("links", {}).items())]
        lines.append("  end")
    first = row["bins"][0]
    lines += [
        "",
        "  test do",
        f'    assert_match version.to_s, shell_output("#{{bin}}/{first} {row["version_args"]}")',
    ]
    lines += [f'    assert_equal "{target}", (bin/"{alias}").readlink.to_s'
              for alias, target in sorted(row.get("links", {}).items())]
    lines += [
        "  end",
        "end",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="formulas to regenerate (default: all)")
    parser.add_argument("--check", action="store_true", help="report drift; write nothing")
    parser.add_argument("--preview", action="store_true",
                        help="select opt-in preview formulas instead of stable formulas")
    args = parser.parse_args(argv)
    manifest = json.loads((ROOT / "manifest.json").read_text())
    formulas = manifest.get("previews", {}) if args.preview else manifest["formulas"]
    names = args.names or sorted(formulas)
    failed = changed = 0
    for name in names:
        row = formulas[name]
        path = ROOT / "Formula" / f"{name}.rb"
        try:
            blobs = {}
            ver, rows = resolve(name, row, manifest["platforms"], blobs)
            if row.get("kind") == "python-wheels":
                scripts, pins = wheel_contents(name, next(iter(blobs.values())))
                deps = [(p, v, pypi_wheels(name, p, v, row["python"])) for p, v in pins]
                text = render_wheels(name, row, ver, rows, scripts, deps)
            else:
                text = render(name, row, ver, rows)
        except (Refused, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            print(f"REFUSED {name}: {error}", file=sys.stderr)
            failed += 1
            continue
        old = path.read_text() if path.exists() else None
        if old == text:
            print(f"current {name} {ver}")
            continue
        changed += 1
        print(f"{'DRIFT' if args.check else 'updated'} {name} {ver}")
        if not args.check:
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)
    print(f"summary changed={changed} refused={failed} total={len(names)}")
    return 1 if failed or (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())

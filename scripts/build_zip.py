#!/usr/bin/env python3
"""Deterministic release ZIP for custom_components/repo_installer (stdlib only).

Same commit -> byte-identical ZIP, on any machine:
- content comes from git (the commit), not from the working copy
- entries sorted, directories included, fixed permissions (0644/0755)
- every timestamp is the commit time (UTC)
- stored, not deflated: compressed bytes would depend on the zlib build
- __pycache__, *.pyc and editor files are never included

Used by `deploy.sh zip` (Forgejo release) and the GitHub release workflow.

    scripts/build_zip.py [--ref HEAD] [--out dist]

Writes <domain>-<version>-<shorthash>.zip and <domain>.zip (identical bytes)
and prints "<sha256>  <path>" for both, versioned name first.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
import zipfile

DOMAIN = "repo_installer"
SRC = f"custom_components/{DOMAIN}"
SHORT_HASH_LEN = 7  # fixed, git's auto length differs between clones

EXCLUDED_DIRS = {"__pycache__", ".idea", ".vscode"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".swp", ".swo", ".orig", ".rej", "~")
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db"}


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    ).stdout


def excluded(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return (
        any(p in EXCLUDED_DIRS for p in parts)
        or name in EXCLUDED_NAMES
        or name.endswith(EXCLUDED_SUFFIXES)
        or name.startswith(".#")
    )


def build(repo: Path, ref: str = "HEAD") -> tuple[bytes, str, str]:
    """Return (zip bytes, version, short hash) for `ref`."""
    commit_time = int(git(repo, "log", "-1", "--format=%ct", ref).strip())
    short = git(repo, "rev-parse", f"--short={SHORT_HASH_LEN}", ref).decode().strip()
    listing = git(repo, "ls-tree", "-r", "-z", "--full-tree", ref, "--", SRC)

    files: dict[str, tuple[str, str]] = {}  # path in zip -> (mode, blob)
    for record in listing.split(b"\0"):
        if not record:
            continue
        meta, path = record.decode().split("\t", 1)
        mode, kind, blob = meta.split()
        if kind != "blob":
            continue
        if mode == "120000":
            raise SystemExit(f"symlink not allowed in release: {path}")
        rel = PurePosixPath(path).relative_to("custom_components").as_posix()
        if not excluded(rel):
            files[rel] = (mode, blob)
    if f"{DOMAIN}/manifest.json" not in files:
        raise SystemExit(f"{SRC}/manifest.json missing in {ref}")

    manifest = json.loads(git(repo, "cat-file", "blob", files[f"{DOMAIN}/manifest.json"][1]))
    version = str(manifest["version"])

    dirs = {
        PurePosixPath(*PurePosixPath(p).parts[:i]).as_posix() + "/"
        for p in files
        for i in range(1, len(PurePosixPath(p).parts))
    }
    date_time = time.gmtime(max(commit_time, 315532800))[:6]  # ZIP can't go before 1980

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
        for name in sorted(dirs | set(files)):
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.create_system = 3  # unix, so the permission bits below count
            info.compress_type = zipfile.ZIP_STORED
            if name.endswith("/"):
                info.external_attr = (0o40755 << 16) | 0x10
                zf.writestr(info, b"")
            else:
                info.external_attr = 0o100644 << 16
                zf.writestr(info, git(repo, "cat-file", "blob", files[name][1]))
    return out.getvalue(), version, short


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--out", default="dist")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args(argv)

    data, version, short = build(Path(args.repo), args.ref)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    for name in (f"{DOMAIN}-{version}-{short}.zip", f"{DOMAIN}.zip"):
        (out / name).write_bytes(data)
        print(f"{digest}  {out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

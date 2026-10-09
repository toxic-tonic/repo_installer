"""Blocking file operations: validate a release ZIP and swap it into place.

Everything here runs in the executor. Nothing from the ZIP is executed or
imported; it is only extracted and moved.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
import zipfile

from .const import (
    BACKUP_DIR,
    DOMAIN_RE,
    KEEP_BACKUPS,
    MAX_UNPACKED_BYTES,
    MAX_ZIP_ENTRIES,
    STAGING_DIR,
)


class InstallError(Exception):
    """The ZIP was rejected or could not be installed."""


def read_installed_version(components_dir: Path, domain: str) -> str | None:
    """Version from custom_components/<domain>/manifest.json, None if absent."""
    try:
        manifest = json.loads((components_dir / domain / "manifest.json").read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    version = manifest.get("version")
    return str(version) if version is not None else None


def _validate_zip(zf: zipfile.ZipFile, domain: str, version: str) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise InstallError(f"ZIP has too many entries ({len(infos)})")
    total = 0
    for info in infos:
        name = info.filename
        path = PurePosixPath(name)
        if (
            "\\" in name
            or path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or path.parts[0] != domain
        ):
            raise InstallError(f"Unexpected path in ZIP: {name!r} (expected only {domain}/…)")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise InstallError(f"Symlink in ZIP: {name!r}")
        total += info.file_size
        if total > MAX_UNPACKED_BYTES:
            raise InstallError("ZIP content exceeds size limit")

    try:
        manifest = json.loads(zf.read(f"{domain}/manifest.json"))
    except KeyError as err:
        raise InstallError(f"ZIP has no {domain}/manifest.json") from err
    except ValueError as err:
        raise InstallError(f"Invalid manifest.json in ZIP: {err}") from err
    if manifest.get("domain") != domain:
        raise InstallError(f"manifest.json domain is {manifest.get('domain')!r}, expected {domain!r}")
    if str(manifest.get("version")) != version:
        raise InstallError(
            f"manifest.json version is {manifest.get('version')!r}, release is {version!r}"
        )


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9.+_]", "_", value) or "unknown"


def rotate_backups(backup_root: Path, domain: str, keep: int = KEEP_BACKUPS) -> None:
    """Keep only the newest `keep` backups of `domain`."""
    if not backup_root.is_dir():
        return
    ours = [
        p for p in backup_root.iterdir()
        if p.is_dir() and p.name.split("-", 1)[0] == domain
    ]
    ours.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in ours[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def install_zip(components_dir: Path, domain: str, version: str, data: bytes) -> Path | None:
    """Install the ZIP for `domain`; returns the backup path (None on first install)."""
    if not DOMAIN_RE.match(domain):
        raise InstallError(f"Invalid domain {domain!r}")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as err:
        raise InstallError(f"Not a ZIP file: {err}") from err

    with zf:
        _validate_zip(zf, domain, version)
        staging_root = components_dir / STAGING_DIR
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{domain}-", dir=staging_root))
        try:
            zf.extractall(staging)
            new_dir = staging / domain
            if not (new_dir / "manifest.json").is_file():
                raise InstallError("Extraction did not produce manifest.json")
            return _swap(components_dir, domain, new_dir)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            try:
                staging_root.rmdir()
            except OSError:
                pass


def _swap(components_dir: Path, domain: str, new_dir: Path) -> Path | None:
    """Move the old folder to the backup area, then rename the new one in.

    Both steps are renames on the same filesystem; if the second fails the
    first is rolled back, so the integration folder is never half-written.
    """
    target = components_dir / domain
    backup: Path | None = None
    if target.exists() or target.is_symlink():
        old_version = read_installed_version(components_dir, domain) or "unknown"
        backup_root = components_dir / BACKUP_DIR
        backup_root.mkdir(exist_ok=True)
        backup = backup_root / f"{domain}-{_safe_name(old_version)}"
        if backup.exists():
            backup = backup.with_name(f"{backup.name}-{time.strftime('%Y%m%d%H%M%S')}")
        os.rename(target, backup)
        now = time.time()
        os.utime(backup, (now, now), follow_symlinks=False)
    try:
        os.rename(new_dir, target)
    except OSError:
        if backup is not None:
            os.rename(backup, target)
        raise
    if backup is not None:
        rotate_backups(components_dir / BACKUP_DIR, domain)
    return backup

"""Version comparison without external dependencies.

Semver-like: numeric core (1.2 == 1.2.0), a pre-release (1.0.0-rc.1, 1.0.0b1)
sorts before the plain release. Unlike semver, build metadata counts and is
compared naturally, so 2024.5.9+ultra10 > 2024.5.9+ultra9 > 2024.5.9.
"""

from __future__ import annotations

import re

_VERSION_RE = re.compile(
    r"^v?(?P<core>\d+(?:\.\d+)*)"
    r"(?:[-.]?(?P<pre>[0-9A-Za-z][0-9A-Za-z.-]*?))?"
    r"(?:\+(?P<build>[0-9A-Za-z][0-9A-Za-z.+-]*))?$"
)


def _natural(text: str) -> tuple:
    # Numeric parts sort before alphanumeric ones, as in semver identifiers.
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.findall(r"\d+|[A-Za-z]+", text)
    )


def _parse(version: str) -> tuple[tuple[int, ...], str | None, str | None] | None:
    match = _VERSION_RE.match(version.strip())
    if not match:
        return None
    core = [int(p) for p in match["core"].split(".")]
    while len(core) > 1 and core[-1] == 0:
        core.pop()
    return tuple(core), match["pre"], match["build"]


def version_key(version: str) -> tuple:
    """Sort key; unparsable versions sort by natural order after parsable ones."""
    parsed = _parse(version)
    if parsed is None:
        return (1, _natural(version))
    core, pre, build = parsed
    pre_key = (1,) if pre is None else (0, _natural(pre))
    build_key = (0,) if build is None else (1, _natural(build))
    return (0, core, pre_key, build_key)


def is_newer(latest: str, installed: str) -> bool:
    return latest != installed and version_key(latest) > version_key(installed)


def is_prerelease(version: str) -> bool:
    """True for 1.0.0-rc.1 / 1.0.0b1; build metadata (+ultra1) is not a pre-release."""
    parsed = _parse(version)
    return parsed is not None and parsed[1] is not None


def looks_like_version(text: str) -> bool:
    return bool(re.match(r"^v?\d", text.strip()))

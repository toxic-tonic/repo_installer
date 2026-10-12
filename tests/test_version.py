"""Version comparison: semver plus counted build suffixes (+ultra10 > +ultra9)."""

from __future__ import annotations

import pytest

from custom_components.repo_installer.version import is_newer, is_prerelease


@pytest.mark.parametrize(
    ("latest", "installed", "newer"),
    [
        ("2024.5.9+ultra2", "2024.5.9+ultra1", True),
        ("2024.5.9+ultra10", "2024.5.9+ultra9", True),
        ("2024.5.9+ultra1", "2024.5.9", True),
        ("2024.5.9+ultra1", "2024.5.9+ultra2", False),
        ("2024.5.9+ultra1", "2024.5.9+ultra1", False),
        ("2024.5.10", "2024.5.9+ultra9", True),
        ("0.10.0", "0.9.9", True),
        ("1.0.0", "1.0.0-rc.1", True),  # release beats its pre-release
        ("1.0.0-rc.1", "1.0.0", False),
        ("1.0.0-rc.2", "1.0.0-rc.1", True),
        ("1.0.0-beta", "1.0.0-alpha", True),
        ("1.1.0b1", "1.0.9", True),
        ("1.0.0", "1.0.0b1", True),
        ("1.0", "1.0.0", False),
        ("v1.2.0", "1.1.0", True),
    ],
)
def test_is_newer(latest, installed, newer):
    assert is_newer(latest, installed) is newer


@pytest.mark.parametrize(
    ("version", "pre"),
    [("1.0.0-rc.1", True), ("1.1.0b1", True), ("2024.5.9+ultra1", False), ("1.0.0", False)],
)
def test_is_prerelease(version, pre):
    assert is_prerelease(version) is pre

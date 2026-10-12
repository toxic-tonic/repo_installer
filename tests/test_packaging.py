"""Store preparation: hacs.json, manifest, translations, brand, deterministic ZIP, release checks."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile

import pytest

from custom_components.repo_installer.installer import install_zip

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "custom_components" / "repo_installer"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"_script_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_zip = load_script("build_zip")
release_meta = load_script("release_meta")
placeholders = load_script("placeholders")

# keys accepted by HACS' hacs.json validator (extra keys are rejected there)
HACS_KEYS = {"name", "content_in_root", "zip_release", "filename", "hide_default_branch",
             "country", "homeassistant", "hacs", "persistent_directory", "render_readme"}


# --- hacs.json / manifest / translations ----------------------------------------------

def test_hacs_json():
    data = json.loads((ROOT / "hacs.json").read_text())
    assert set(data) <= HACS_KEYS
    assert data["name"] == "Repo Installer"
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d+", data["homeassistant"])
    assert data["render_readme"] is True
    # HACS would unpack a zip_release asset straight into custom_components/<domain>/,
    # our assets contain <domain>/… – so HACS installs from the tagged source instead.
    assert "zip_release" not in data and "filename" not in data
    assert data["hide_default_branch"] is True


def test_manifest_required_fields_and_order():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    for key in ("domain", "name", "version", "codeowners", "documentation", "issue_tracker",
                "iot_class", "config_flow", "requirements", "integration_type"):
        assert key in manifest, key
    assert manifest["domain"] == "repo_installer"
    assert manifest["config_flow"] is True
    assert manifest["requirements"] == []
    assert manifest["iot_class"] in {"cloud_polling", "local_polling"}
    assert manifest["integration_type"] == "service"
    assert all(o.startswith("@") for o in manifest["codeowners"])
    keys = list(manifest)
    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])  # hassfest: domain, name, then alphabetical


def test_version_consistent_with_changelog():
    version = json.loads((INTEGRATION / "manifest.json").read_text())["version"]
    assert release_meta.check(f"v{version}") == version


def _keys(tree, prefix=""):
    if isinstance(tree, dict):
        return {k for key, value in tree.items() for k in _keys(value, f"{prefix}{key}.")}
    return {prefix.rstrip(".")}


def test_translations_complete():
    strings = json.loads((INTEGRATION / "strings.json").read_text())
    en = json.loads((INTEGRATION / "translations" / "en.json").read_text())
    de = json.loads((INTEGRATION / "translations" / "de.json").read_text())
    assert en == strings
    assert _keys(de) == _keys(strings)
    for text in json.dumps(strings), json.dumps(de):
        assert not re.search(r"https?://", text)  # hassfest forbids URLs in strings


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", head[16:24])


def test_brand_assets():
    brand = INTEGRATION / "brand"  # HACS brands check and HA >= 2026.3 look here
    assert _png_size(brand / "icon.png") == (256, 256)
    assert _png_size(brand / "icon@2x.png") == (512, 512)
    if (brand / "logo.png").exists():
        assert 128 <= min(_png_size(brand / "logo.png")) <= 256


def test_placeholders_known():
    """Every <UPPER_CASE> token in the repo is a defined placeholder (no typos)."""
    unknown = set()
    skip = {ROOT / "scripts" / "placeholders.py", Path(__file__).resolve()}
    for path in placeholders.tracked_files():
        if path.suffix in {".png", ".zip"} or not path.is_file() or path.resolve() in skip:
            continue
        for match in placeholders.TOKEN_RE.finditer(path.read_text(encoding="utf-8")):
            if match[1] not in placeholders.PLACEHOLDERS:
                unknown.add((path.relative_to(ROOT).as_posix(), match[0]))
    assert unknown == set()
    # all applied for the release (scripts/placeholders.py list must be empty)
    assert placeholders.occurrences() == []


# --- deterministic ZIP ------------------------------------------------------------------

def git(repo: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={**os.environ, **(env or {})}).stdout


@pytest.fixture
def fake_repo(tmp_path) -> Path:
    repo = tmp_path / "src"
    integ = repo / "custom_components" / "repo_installer"
    (integ / "providers").mkdir(parents=True)
    (integ / "manifest.json").write_text(json.dumps({"domain": "repo_installer", "version": "9.9.9"}))
    (integ / "__init__.py").write_text("X = 1\n")
    (integ / "providers" / "a.py").write_text("A = 1\n")
    (integ / "__pycache__").mkdir()
    (integ / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"junk")
    (integ / "old.py~").write_text("backup")
    (repo / "README.md").write_text("not in the zip")
    git(repo, "init", "-q")
    git(repo, "add", "-A", "-f")
    date = {"GIT_AUTHOR_DATE": "2026-01-02T03:04:06Z", "GIT_COMMITTER_DATE": "2026-01-02T03:04:06Z",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t"}
    git(repo, "commit", "-q", "-m", "x", env=date)
    return repo


def test_zip_deterministic_across_clones(fake_repo, tmp_path):
    first, version, short = build_zip.build(fake_repo)
    second, _, _ = build_zip.build(fake_repo)
    assert first == second
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(fake_repo), str(clone)], check=True)
    os.utime(clone / "custom_components/repo_installer/__init__.py", (0, 0))  # mtime irrelevant
    (clone / "custom_components/repo_installer/__init__.py").chmod(0o600)  # so are file modes
    third, _, _ = build_zip.build(clone)
    assert hashlib.sha256(third).hexdigest() == hashlib.sha256(first).hexdigest()
    assert version == "9.9.9" and len(short) == 7


def test_zip_layout(fake_repo):
    data, _, _ = build_zip.build(fake_repo)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
    names = [i.filename for i in infos]
    assert names == sorted(names)
    assert names == [
        "repo_installer/", "repo_installer/__init__.py", "repo_installer/manifest.json",
        "repo_installer/providers/", "repo_installer/providers/a.py",
    ]  # no __pycache__, *.pyc, editor backups, nothing outside the integration
    for info in infos:
        assert info.date_time == (2026, 1, 2, 3, 4, 6)  # ZIP: 2 s resolution
        assert info.compress_type == zipfile.ZIP_STORED
        mode = info.external_attr >> 16
        assert mode == (0o40755 if info.filename.endswith("/") else 0o100644)


def test_zip_of_this_repo_is_installable(tmp_path):
    """The real release ZIP (HEAD) passes the installer's own validation."""
    data, version, _ = build_zip.build(ROOT)
    assert data == build_zip.build(ROOT)[0]
    comp = tmp_path / "custom_components"
    comp.mkdir()
    assert install_zip(comp, "repo_installer", version, data) is None
    assert (comp / "repo_installer" / "manifest.json").is_file()


def test_build_writes_both_names(fake_repo, tmp_path, capsys):
    out = tmp_path / "dist"
    build_zip.main(["--repo", str(fake_repo), "--out", str(out)])
    files = sorted(p.name for p in out.iterdir())
    short = git(fake_repo, "rev-parse", "--short=7", "HEAD").strip()
    assert files == ["repo_installer-9.9.9-" + short + ".zip", "repo_installer.zip"]
    assert (out / files[0]).read_bytes() == (out / files[1]).read_bytes()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split()[0] == lines[1].split()[0] == hashlib.sha256((out / files[0]).read_bytes()).hexdigest()


# --- release metadata (used by the GitHub release workflow) -----------------------------

CHANGELOG = """# Changelog

## [1.1.0-rc.1] - 2026-02-01

### Added
- rc

## [1.0.0] - 2026-01-01

### Added
- first

[1.0.0]: https://example.invalid/v1.0.0
"""


@pytest.fixture
def meta_files(tmp_path):
    manifest = tmp_path / "manifest.json"
    changelog = tmp_path / "CHANGELOG.md"
    manifest.write_text(json.dumps({"version": "1.0.0"}))
    changelog.write_text(CHANGELOG)
    return manifest, changelog


def test_release_check_ok(meta_files):
    assert release_meta.check("v1.0.0", *meta_files) == "1.0.0"


@pytest.mark.parametrize(
    ("tag", "manifest_version", "message"),
    [
        ("1.0.0", "1.0.0", "does not start with v"),
        ("v1.0.1", "1.0.0", "!= manifest.json version 1.0.0"),
        ("v2.0.0", "2.0.0", "no section ## [2.0.0]"),
    ],
)
def test_release_check_mismatch(meta_files, tag, manifest_version, message):
    manifest, changelog = meta_files
    manifest.write_text(json.dumps({"version": manifest_version}))
    with pytest.raises(release_meta.ReleaseError, match=re.escape(message)):
        release_meta.check(tag, manifest, changelog)


def test_release_notes(meta_files):
    notes = release_meta.notes("1.0.0", "a" * 64, meta_files[1])
    assert notes == "### Added\n- first\n\nSHA-256: " + "a" * 64 + "\n"
    rc = release_meta.notes("1.1.0-rc.1", "b" * 64, meta_files[1])
    assert "- rc" in rc and "first" not in rc  # only its own section


def test_release_notes_empty_section(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [1.0.0] - 2026-01-01\n\n## [0.9.0]\n- x\n")
    with pytest.raises(release_meta.ReleaseError, match="empty"):
        release_meta.notes("1.0.0", "a" * 64, changelog)


@pytest.mark.parametrize(("version", "pre"), [("1.1.0-rc.1", True), ("0.2.0", False), ("1.0.0b1", True)])
def test_release_prerelease(version, pre):
    assert release_meta.is_prerelease(version) is pre


def test_release_cli_exit_codes():
    script = str(ROOT / "scripts" / "release_meta.py")
    bad = subprocess.run(["python3", script, "check", "v0.0.0-never"], capture_output=True, text=True)
    assert bad.returncode == 1 and "ERROR" in bad.stderr
    usage = subprocess.run(["python3", script], capture_output=True, text=True)
    assert usage.returncode == 2

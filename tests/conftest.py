"""Shared fixtures: fake Forgejo releases, fake target integration, temp config dir."""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import zipfile

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

BASE = "http://forgejo.test:3000"
REPO = "toxic/demo-integration"
TARGET = "demo_target"
API = f"{BASE}/api/v1/repos/{REPO}"


def pytest_configure(config):
    """The plugin ships its own custom_components package; add ours in front."""
    import custom_components

    ours = str(pathlib.Path(__file__).parent.parent / "custom_components")
    if ours not in custom_components.__path__:
        custom_components.__path__.insert(0, ours)
    config.addinivalue_line("markers", "live: reads from the real Forgejo at 172.16.1.36")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def components_dir(hass, tmp_path) -> pathlib.Path:
    """Point HA's config dir at a temp dir with custom_components/demo_target 1.0.0."""
    hass.config.config_dir = str(tmp_path)
    comp = tmp_path / "custom_components"
    write_target(comp, "1.0.0")
    return comp


def write_target(comp: pathlib.Path, version: str, domain: str = TARGET) -> None:
    d = comp / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"domain": domain, "version": version}))
    (d / "__init__.py").write_text(f"VERSION = {version!r}\n")


def make_zip(version: str, domain: str = TARGET, manifest_version: str | None = None,
             extra: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{domain}/", "")
        zf.writestr(f"{domain}/manifest.json", json.dumps(
            {"domain": domain, "version": manifest_version or version}))
        zf.writestr(f"{domain}/__init__.py", f"VERSION = {version!r}\n")
        for name, content in (extra or {}).items():
            zf.writestr(name, content)
    return buf.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_json(version: str, sha256: str | None, *, prerelease: bool = False,
                 asset_url: str | None = None, rid: int = 1) -> dict:
    tag = "v" + version.replace("+", "-")
    name = f"{TARGET}-{version}-abc1234.zip"
    body = f"Änderungen …\n\n**Commit:** `abc1234`\n"
    if sha256:
        body += f"**SHA-256 ZIP:** `{sha256}`\n"
    return {
        "id": rid,
        "tag_name": tag,
        "name": version,
        "body": body,
        "html_url": f"{BASE}/{REPO}/releases/tag/{tag}",
        "draft": False,
        "prerelease": prerelease,
        "assets": [{
            "name": name,
            "browser_download_url": asset_url
            or f"{BASE}/{REPO}/releases/download/{tag}/{name.replace('+', '%2B')}",
        }],
    }


def mock_release(aioclient_mock, version: str, zip_bytes: bytes | None, *,
                 sha256: str | None = None) -> dict:
    """Register /releases/latest and the asset download."""
    rel = release_json(version, sha256 or (sha(zip_bytes) if zip_bytes else None))
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    if zip_bytes is not None:
        aioclient_mock.get(rel["assets"][0]["browser_download_url"], content=zip_bytes)
    return rel

"""Shared fixtures: fake Git APIs (Forgejo/Gitea, GitHub, GitLab), fake target integration."""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
from urllib.parse import quote
import zipfile

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

DOMAIN = "repo_installer"
TARGET = "demo_target"

# Forgejo/Gitea
BASE = "http://forgejo.test:3000"
REPO = "toxic/demo-integration"
REPO_URL = f"{BASE}/{REPO}"
API = f"{BASE}/api/v1/repos/{REPO}"

# GitHub
GH_REPO = "owner/demo"
GH_URL = f"https://github.com/{GH_REPO}"
GH_API = f"https://api.github.com/repos/{GH_REPO}"

# GitLab (self-hosted under a sub path, nested group)
GL_BASE = "https://git.example/gitlab"
GL_PATH = "group/sub/demo"
GL_URL = f"{GL_BASE}/{GL_PATH}"
GL_API = f"{GL_BASE}/api/v4/projects/{quote(GL_PATH, safe='')}"
GL_ID = 42


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


@pytest.fixture
def empty_components_dir(hass, tmp_path) -> pathlib.Path:
    """Config dir with an empty custom_components."""
    hass.config.config_dir = str(tmp_path)
    comp = tmp_path / "custom_components"
    comp.mkdir()
    return comp


def write_target(comp: pathlib.Path, version: str, domain: str = TARGET) -> None:
    d = comp / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"domain": domain, "version": version}))
    (d / "__init__.py").write_text(f"VERSION = {version!r}\n")


def leftovers(comp: pathlib.Path) -> list[str]:
    """Everything in custom_components except the target folder."""
    return sorted(p.name for p in comp.iterdir() if p.name != TARGET) if comp.exists() else []


def make_zip(version: str, domain: str = TARGET, manifest_version: str | None = None,
             manifest_domain: str | None = None, extra: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{domain}/", "")
        zf.writestr(f"{domain}/manifest.json", json.dumps(
            {"domain": manifest_domain or domain, "version": manifest_version or version}))
        zf.writestr(f"{domain}/__init__.py", f"VERSION = {version!r}\n")
        for name, content in (extra or {}).items():
            zf.writestr(name, content)
    return buf.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def body_with(sha256: str | None) -> str:
    body = "Änderungen …\n\n**Commit:** `abc1234`\n"
    if sha256:
        body += f"**SHA-256:** `{sha256}`\n"
    return body


# --- Forgejo/Gitea ----------------------------------------------------------

def gitea_repo_json(path: str = REPO) -> dict:
    owner = path.split("/")[0]
    return {"id": 1, "full_name": path, "owner": {"login": owner}, "empty": False,
            "clone_url": f"{BASE}/{path}.git"}


def release_json(version: str, sha256: str | None, *, prerelease: bool = False,
                 asset_url: str | None = None, rid: int = 1, base: str = BASE,
                 repo: str = REPO) -> dict:
    tag = "v" + version.replace("+", "-")
    name = f"{TARGET}-{version}-abc1234.zip"
    return {
        "id": rid,
        "tag_name": tag,
        "name": version,
        "body": body_with(sha256),
        "html_url": f"{base}/{repo}/releases/tag/{tag}",
        "draft": False,
        "prerelease": prerelease,
        "assets": [{
            "name": name,
            "browser_download_url": asset_url
            or f"{base}/{repo}/releases/download/{tag}/{name.replace('+', '%2B')}",
        }],
    }


def mock_release(aioclient_mock, version: str, zip_bytes: bytes | None, *,
                 sha256: str | None = None, api: str = API, **kwargs) -> dict:
    """Register Forgejo /releases/latest and the asset download."""
    rel = release_json(version, sha256 or (sha(zip_bytes) if zip_bytes else None), **kwargs)
    aioclient_mock.get(f"{api}/releases/latest", json=rel)
    if zip_bytes is not None:
        aioclient_mock.get(rel["assets"][0]["browser_download_url"], content=zip_bytes)
    return rel


# --- GitHub -------------------------------------------------------------------

def github_repo_json(path: str = GH_REPO) -> dict:
    return {"id": 7, "node_id": "R_x", "full_name": path, "owner": {"login": path.split("/")[0]},
            "clone_url": f"https://github.com/{path}.git"}


def github_release_json(version: str, sha256: str | None, *, prerelease: bool = False,
                        asset_id: int = 99, api: str = GH_API) -> dict:
    name = f"{TARGET}-{version}-abc1234.zip"
    return {
        "id": 1,
        "tag_name": f"v{version}",
        "name": f"v{version}",
        "body": body_with(sha256),
        "html_url": f"https://github.com/{GH_REPO}/releases/tag/v{version}",
        "draft": False,
        "prerelease": prerelease,
        "assets": [{
            "name": name,
            "url": f"{api}/releases/assets/{asset_id}",
            "browser_download_url": f"https://github.com/{GH_REPO}/releases/download/v{version}/{name}",
        }],
    }


# --- GitLab -------------------------------------------------------------------

def gitlab_project_json(path: str = GL_PATH) -> dict:
    return {"id": GL_ID, "path_with_namespace": path, "web_url": f"{GL_BASE}/{path}"}


def gitlab_release_json(version: str, sha256: str | None, *, link_url: str | None = None,
                        extra_links: list[dict] | None = None) -> dict:
    name = f"{TARGET}-{version}-abc1234.zip"
    url = link_url or f"{GL_BASE}/api/v4/projects/{GL_ID}/packages/generic/{TARGET}/{version}/{name}"
    return {
        "tag_name": f"v{version}",
        "name": version,
        "description": body_with(sha256),
        "upcoming_release": False,
        "_links": {"self": f"{GL_URL}/-/releases/v{version}"},
        "assets": {
            "sources": [{"format": "zip", "url": f"{GL_URL}/-/archive/v{version}/demo-v{version}.zip"}],
            "links": [{"name": name, "url": url, "direct_asset_url": url, "link_type": "package"}]
            + (extra_links or []),
        },
    }

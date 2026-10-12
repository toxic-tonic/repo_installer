"""Read-only smoke tests against github.com and gitlab.com (run with --live).

Repos (public, stable, maintained by the platform's own community):
- GitHub: hacs/integration – one ZIP asset (hacs.zip), no SHA-256 in the notes.
- gitlab.com: gitlab-org/cli (glab) – maintained by GitLab itself, release
  links point into gitlab.com's generic package registry, i.e. exactly the
  download path the GitLab adapter has to support. No HA integration on
  gitlab.com publishes ZIP release links (searched by topic, 2026-10).

Nothing is installed: rejection paths are checked in a temp dir, downloads
run against a dummy SHA-256 and must fail with "mismatch" after the full
file came through the allowed hosts.
"""

from __future__ import annotations

from dataclasses import replace

import aiohttp
import pytest
import pytest_socket

from custom_components.repo_installer.actions import async_install_release
from custom_components.repo_installer.providers import RepoError, async_detect, parse_repo_url
from custom_components.repo_installer.providers.github import GITHUB_ASSET_HOSTS
from custom_components.repo_installer.providers.gitlab import GITLAB_COM_ASSET_HOSTS

pytestmark = pytest.mark.live

DUMMY_SHA = "0" * 64


@pytest.fixture(autouse=True)
def _allow_network(socket_enabled):
    pytest_socket.socket_allow_hosts(
        ["127.0.0.1", "api.github.com", "github.com", "release-assets.githubusercontent.com",
         "objects.githubusercontent.com", "gitlab.com"],
        allow_unix_socket=True,
    )


@pytest.fixture
async def traced_session():
    """Plain aiohttp session that records every requested host."""
    hosts: list[str] = []

    async def on_start(session, ctx, params):
        hosts.append(params.url.host)

    trace = aiohttp.TraceConfig()
    trace.on_request_start.append(on_start)
    async with aiohttp.ClientSession(trace_configs=[trace]) as session:
        session.hosts = hosts
        yield session


async def assert_rejected_without_remains(hass, tmp_path, provider, release, domain):
    comp = tmp_path / "custom_components"
    comp.mkdir()
    before = list(provider._session.hosts)
    with pytest.raises(RepoError) as err:
        await async_install_release(hass, provider, comp, domain, release)
    assert list(comp.iterdir()) == []
    assert provider._session.hosts == before  # rejected before any download
    return str(err.value)


async def test_github_hacs(hass, tmp_path, traced_session):
    provider = await async_detect(traced_session, parse_repo_url("https://github.com/hacs/integration"), None)
    assert provider.name == "GitHub"
    assert set(traced_session.hosts) == {"api.github.com"}  # host decides, nothing else probed

    release = await provider.async_get_latest_release(False)
    assert release.version[0].isdigit()
    assert release.asset_name == "hacs.zip"
    assert release.asset_url.startswith("https://api.github.com/repos/hacs/integration/releases/assets/")
    assert release.sha256 is None
    assert "SHA-256" in release.problem

    message = await assert_rejected_without_remains(hass, tmp_path, provider, release, "hacs")
    assert "SHA-256" in message

    traced_session.hosts.clear()
    with pytest.raises(RepoError, match="SHA-256 mismatch"):  # full file downloaded
        await provider.async_download_asset(replace(release, problem=None, sha256=DUMMY_SHA))
    assert traced_session.hosts[0] == "api.github.com"
    assert set(traced_session.hosts) <= set(GITHUB_ASSET_HOSTS)
    assert len(traced_session.hosts) >= 2  # redirected to object storage


async def test_gitlab_glab(hass, tmp_path, traced_session):
    provider = await async_detect(traced_session, parse_repo_url("https://gitlab.com/gitlab-org/cli"), None)
    assert provider.name == "GitLab"
    assert set(traced_session.hosts) == {"gitlab.com"}

    release = await provider.async_get_latest_release(False)
    assert release.version[0].isdigit()
    assert "ZIP assets, expected exactly 1" in release.problem  # glab ships 3 Windows ZIPs
    await assert_rejected_without_remains(hass, tmp_path, provider, release, "glab")

    # Same release reduced to one ZIP link: now the missing SHA-256 is the reason
    api = provider.repo_api_url
    async with traced_session.get(f"{api}/releases/{release.tag}") as resp:
        data = await resp.json()
    link = next(l for l in data["assets"]["links"] if l["name"].endswith("windows_386.zip"))
    single = provider._build_release(
        tag=release.tag, name=data.get("name"), body=data.get("description"),
        html_url=release.html_url, prerelease=False,
        zips=[(link["name"], link["direct_asset_url"])],
    )
    assert single.problem == "Release notes contain 0 SHA-256 values, expected exactly 1"
    assert provider.is_own_asset_url(link["direct_asset_url"])
    assert provider.is_own_asset_url(link["url"])  # generic package registry
    (tmp_path / "2").mkdir()
    message = await assert_rejected_without_remains(hass, tmp_path / "2", provider, single, "glab")
    assert "SHA-256" in message

    traced_session.hosts.clear()
    with pytest.raises(RepoError, match="SHA-256 mismatch"):
        await provider.async_download_asset(replace(single, problem=None, sha256=DUMMY_SHA))
    # gitlab.com serves the package itself, no foreign storage host involved
    assert set(traced_session.hosts) == set(GITLAB_COM_ASSET_HOSTS) == {"gitlab.com"}

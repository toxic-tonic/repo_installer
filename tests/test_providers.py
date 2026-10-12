"""Per-adapter behaviour: latest release, pre-releases, asset URL, rate limit, host binding."""

from __future__ import annotations

from aiohttp import ClientError
import pytest
from yarl import URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.repo_installer.providers import (
    RateLimitError,
    RepoError,
    RepoLocation,
    build_provider,
    parse_repo_url,
)
from conftest import (
    API,
    BASE,
    GH_API,
    GH_REPO,
    GL_API,
    GL_BASE,
    GL_PATH,
    REPO,
    github_release_json,
    gitlab_project_json,
    gitlab_release_json,
    make_zip,
    mock_release,
    release_json,
    sha,
)

TOKEN = "s3cr3t-token"


def gitea(hass, base=BASE, repo=REPO, token=None):
    return build_provider(async_get_clientsession(hass), "gitea", RepoLocation(URL(base), repo), token)


def github(hass, token=None):
    return build_provider(
        async_get_clientsession(hass), "github",
        RepoLocation(URL("https://github.com"), GH_REPO), token,
    )


def gitlab(hass, token=None):
    return build_provider(
        async_get_clientsession(hass), "gitlab", RepoLocation(URL(GL_BASE), GL_PATH), token
    )


def headers_of(aioclient_mock, url: str) -> dict:
    for _method, called, _data, headers in aioclient_mock.mock_calls:
        if str(called) == url:
            return dict(headers or {})
    raise AssertionError(f"{url} not called")


# --- URL parsing ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "url", "segments"),
    [
        ("http://172.16.1.36:3000/toxic/linknlink-local", "http://172.16.1.36:3000/toxic/linknlink-local",
         ("toxic", "linknlink-local")),
        ("https://github.com/owner/repo.git/", "https://github.com/owner/repo", ("owner", "repo")),
        ("https://gitlab.com/g/s/p/-/releases", "https://gitlab.com/g/s/p", ("g", "s", "p")),
        ("http://host/git/owner/repo?x=1#y", "http://host/git/owner/repo", ("git", "owner", "repo")),
    ],
)
def test_parse_repo_url(text, url, segments):
    parsed = parse_repo_url(text)
    assert str(parsed.url) == url
    assert parsed.segments == segments


@pytest.mark.parametrize("text", ["ftp://host/a/b", "http://host/onlyone", "not a url", "http:///a/b"])
def test_parse_repo_url_rejects(text):
    with pytest.raises(ValueError):
        parse_repo_url(text)


# --- Forgejo/Gitea -------------------------------------------------------------

async def test_gitea_latest_and_asset(hass, aioclient_mock):
    rel = mock_release(aioclient_mock, "2024.5.9+ultra1", None, sha256="a" * 64)
    release = await gitea(hass).async_get_latest_release(False)
    assert release.version == "2024.5.9+ultra1"  # from the title, the tag is v2024.5.9-ultra1
    assert release.tag == "v2024.5.9-ultra1"
    assert release.sha256 == "a" * 64
    assert release.asset_url == rel["assets"][0]["browser_download_url"]
    assert release.problem is None


async def test_gitea_prerelease_switch(hass, aioclient_mock):
    stable = release_json("1.0.1", "a" * 64)
    pre = release_json("1.1.0b1", "b" * 64, prerelease=True, rid=2)
    aioclient_mock.get(f"{API}/releases/latest", json=stable)
    aioclient_mock.get(f"{API}/releases", json=[pre, stable], params={"draft": "false", "limit": "10"})
    assert (await gitea(hass).async_get_latest_release(False)).version == "1.0.1"
    release = await gitea(hass).async_get_latest_release(True)
    assert release.version == "1.1.0b1"
    assert release.prerelease


async def test_gitea_subpath(hass, aioclient_mock):
    """Self-hosted behind a reverse proxy under /git, plain http."""
    base = "http://proxy.test/git"
    api = f"{base}/api/v1/repos/{REPO}"
    zip_bytes = make_zip("1.0.1")
    mock_release(aioclient_mock, "1.0.1", zip_bytes, api=api, base=base)
    provider = gitea(hass, base=base)
    release = await provider.async_get_latest_release(False)
    assert release.problem is None
    assert release.asset_url.startswith(f"{base}/{REPO}/releases/download/")
    assert await provider.async_download_asset(release) == zip_bytes


async def test_gitea_token_header(hass, aioclient_mock):
    mock_release(aioclient_mock, "1.0.1", None, sha256="a" * 64)
    await gitea(hass, token=TOKEN).async_get_latest_release(False)
    assert headers_of(aioclient_mock, f"{API}/releases/latest")["Authorization"] == f"token {TOKEN}"


async def test_gitea_redirect_same_host_ok(hass, aioclient_mock):
    zip_bytes = make_zip("1.0.1")
    rel = release_json("1.0.1", sha(zip_bytes))
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    aioclient_mock.get(rel["assets"][0]["browser_download_url"], status=302,
                       headers={"Location": "/attachments/abc"})
    aioclient_mock.get(f"{BASE}/attachments/abc", content=zip_bytes)
    provider = gitea(hass, token=TOKEN)
    release = await provider.async_get_latest_release(False)
    assert await provider.async_download_asset(release) == zip_bytes


async def test_redirect_to_foreign_host_rejected(hass, aioclient_mock):
    zip_bytes = make_zip("1.0.1")
    rel = release_json("1.0.1", sha(zip_bytes))
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    aioclient_mock.get(rel["assets"][0]["browser_download_url"], status=302,
                       headers={"Location": "https://evil.test/x.zip"})
    aioclient_mock.get("https://evil.test/x.zip", content=zip_bytes)
    provider = gitea(hass, token=TOKEN)
    release = await provider.async_get_latest_release(False)
    with pytest.raises(RepoError, match="foreign host evil.test"):
        await provider.async_download_asset(release)
    assert all(str(c[1]).startswith(BASE) for c in aioclient_mock.mock_calls)


async def test_error_messages_never_contain_token(hass, aioclient_mock):
    aioclient_mock.get(f"{API}/releases/latest", exc=ClientError(f"boom Authorization: token {TOKEN}"))
    with pytest.raises(RepoError) as err:
        await gitea(hass, token=TOKEN).async_get_latest_release(False)
    assert TOKEN not in str(err.value)


# --- GitHub ---------------------------------------------------------------------

async def test_github_latest_and_asset_download(hass, aioclient_mock):
    zip_bytes = make_zip("1.2.0")
    rel = github_release_json("1.2.0", sha(zip_bytes))
    aioclient_mock.get(f"{GH_API}/releases/latest", json=rel)
    storage = "https://objects.githubusercontent.com/github-production-release-asset/1?sig=x"
    aioclient_mock.get(f"{GH_API}/releases/assets/99", status=302, headers={"Location": storage})
    aioclient_mock.get(storage, content=zip_bytes)

    provider = github(hass, token=TOKEN)
    release = await provider.async_get_latest_release(False)
    assert release.version == "1.2.0"  # leading v of the title stripped
    assert release.asset_url == f"{GH_API}/releases/assets/99"  # API URL, not browser URL
    assert await provider.async_download_asset(release) == zip_bytes

    api_headers = headers_of(aioclient_mock, f"{GH_API}/releases/assets/99")
    assert api_headers["Accept"] == "application/octet-stream"
    assert api_headers["Authorization"] == f"Bearer {TOKEN}"
    # The token never goes to object storage
    assert "Authorization" not in headers_of(aioclient_mock, storage)


async def test_github_prerelease_switch(hass, aioclient_mock):
    stable = github_release_json("1.2.0", "a" * 64)
    pre = github_release_json("1.3.0-rc.1", "b" * 64, prerelease=True)
    aioclient_mock.get(f"{GH_API}/releases/latest", json=stable)
    aioclient_mock.get(f"{GH_API}/releases", json=[pre, stable], params={"per_page": "10"})
    assert (await github(hass).async_get_latest_release(False)).version == "1.2.0"
    assert (await github(hass).async_get_latest_release(True)).version == "1.3.0-rc.1"


async def test_github_rate_limit(hass, aioclient_mock):
    aioclient_mock.get(f"{GH_API}/releases/latest", status=403,
                       headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1760270400"})
    with pytest.raises(RateLimitError, match="Rate-Limit erreicht bis .* ohne Token"):
        await github(hass).async_get_latest_release(False)


async def test_github_foreign_storage_rejected(hass, aioclient_mock):
    zip_bytes = make_zip("1.2.0")
    aioclient_mock.get(f"{GH_API}/releases/latest", json=github_release_json("1.2.0", sha(zip_bytes)))
    aioclient_mock.get(f"{GH_API}/releases/assets/99", status=302,
                       headers={"Location": "https://objects.evil.test/x.zip"})
    provider = github(hass)
    release = await provider.async_get_latest_release(False)
    with pytest.raises(RepoError, match="foreign host"):
        await provider.async_download_asset(release)


async def test_github_asset_of_other_repo_rejected(hass, aioclient_mock):
    rel = github_release_json("1.2.0", "a" * 64, api="https://api.github.com/repos/someone/else")
    aioclient_mock.get(f"{GH_API}/releases/latest", json=rel)
    release = await github(hass).async_get_latest_release(False)
    assert release.problem == "Asset URL does not belong to the configured repository"


# --- GitLab ---------------------------------------------------------------------

async def test_gitlab_links_assets_and_encoded_path(hass, aioclient_mock):
    zip_bytes = make_zip("2.0.0")
    aioclient_mock.get(GL_API, json=gitlab_project_json())
    rel = gitlab_release_json("2.0.0", sha(zip_bytes), extra_links=[
        {"name": "README", "url": f"{GL_BASE}/{GL_PATH}/-/raw/main/README.md"},
    ])
    aioclient_mock.get(f"{GL_API}/releases", json=[rel], params={"per_page": "20"})
    link = rel["assets"]["links"][0]["url"]
    aioclient_mock.get(link, content=zip_bytes)

    provider = gitlab(hass, token=TOKEN)
    release = await provider.async_get_latest_release(False)
    assert "/api/v4/projects/group%2Fsub%2Fdemo" in GL_API
    assert release.version == "2.0.0"
    assert release.asset_url == link  # links asset (generic package by numeric id)
    assert release.problem is None
    assert await provider.async_download_asset(release) == zip_bytes
    assert headers_of(aioclient_mock, link)["PRIVATE-TOKEN"] == TOKEN
    assert "Authorization" not in headers_of(aioclient_mock, link)


async def test_gitlab_prerelease_by_version(hass, aioclient_mock):
    aioclient_mock.get(GL_API, json=gitlab_project_json())
    upcoming = {**gitlab_release_json("3.0.0", "c" * 64), "upcoming_release": True}
    pre = gitlab_release_json("2.1.0-rc.1", "b" * 64)
    stable = gitlab_release_json("2.0.0", "a" * 64)
    aioclient_mock.get(f"{GL_API}/releases", json=[upcoming, pre, stable], params={"per_page": "20"})
    assert (await gitlab(hass).async_get_latest_release(False)).version == "2.0.0"
    release = await gitlab(hass).async_get_latest_release(True)
    assert release.version == "2.1.0-rc.1"
    assert release.prerelease


async def test_gitlab_external_link_not_installable(hass, aioclient_mock):
    aioclient_mock.get(GL_API, json=gitlab_project_json())
    rel = gitlab_release_json("2.0.0", "a" * 64, link_url="https://files.example/demo.zip")
    aioclient_mock.get(f"{GL_API}/releases", json=[rel], params={"per_page": "20"})
    release = await gitlab(hass).async_get_latest_release(False)
    assert release.problem == "Asset URL does not belong to the configured repository"
    with pytest.raises(RepoError):
        await gitlab(hass).async_download_asset(release)


async def test_gitlab_project_upload_link_accepted(hass, aioclient_mock):
    aioclient_mock.get(GL_API, json=gitlab_project_json())
    rel = gitlab_release_json("2.0.0", "a" * 64, link_url=f"{GL_BASE}/{GL_PATH}/uploads/abc/demo.zip")
    aioclient_mock.get(f"{GL_API}/releases", json=[rel], params={"per_page": "20"})
    assert (await gitlab(hass).async_get_latest_release(False)).problem is None


# --- ZIP selection with several assets (stable HACS name + versioned name) ----------

def two_asset_release(version: str, sha256: str, fixed_first: bool = True) -> dict:
    rel = release_json(version, sha256)
    tag = rel["tag_name"]
    fixed = {"name": "demo_target.zip",
             "browser_download_url": f"{BASE}/{REPO}/releases/download/{tag}/demo_target.zip"}
    rel["assets"] = [fixed, *rel["assets"]] if fixed_first else [*rel["assets"], fixed]
    return rel


@pytest.mark.parametrize("fixed_first", [True, False])
async def test_two_zips_versioned_name_wins(hass, aioclient_mock, fixed_first):
    zip_bytes = make_zip("2024.5.9+ultra2")
    rel = two_asset_release("2024.5.9+ultra2", sha(zip_bytes), fixed_first)
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    release = await gitea(hass).async_get_latest_release(False)
    assert release.problem is None
    assert release.asset_name == "demo_target-2024.5.9+ultra2-abc1234.zip"


async def test_two_unversioned_zips_rejected(hass, aioclient_mock):
    rel = release_json("1.0.1", "a" * 64)
    rel["assets"] = [
        {"name": n, "browser_download_url": f"{BASE}/{REPO}/releases/download/v1.0.1/{n}"}
        for n in ("a.zip", "b.zip")
    ]
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    release = await gitea(hass).async_get_latest_release(False)
    assert release.problem == "Release has 2 ZIP assets and none is selectable (versioned name or SHA-256 digest)"
    assert release.asset_url is None


async def test_github_two_zips_by_digest(hass, aioclient_mock):
    """No versioned name: GitHub's per-asset digest decides."""
    rel = github_release_json("1.2.0", "c" * 64)
    rel["assets"] = [
        {"name": "one.zip", "url": f"{GH_API}/releases/assets/1", "digest": "sha256:" + "b" * 64},
        {"name": "two.zip", "url": f"{GH_API}/releases/assets/2", "digest": "sha256:" + "C" * 64},
    ]
    aioclient_mock.get(f"{GH_API}/releases/latest", json=rel)
    release = await github(hass).async_get_latest_release(False)
    assert release.problem is None
    assert release.asset_name == "two.zip"


async def test_no_zip_asset(hass, aioclient_mock):
    rel = release_json("1.0.1", "a" * 64)
    rel["assets"] = []
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    assert (await gitea(hass).async_get_latest_release(False)).problem == "Release has no ZIP asset"

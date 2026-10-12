"""Config flow: auto-detection, manual provider, confirm step, first install, options."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from aiohttp import ClientError
import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import (
    API,
    BASE,
    DOMAIN,
    GH_API,
    GH_URL,
    GL_API,
    GL_BASE,
    GL_PATH,
    GL_URL,
    REPO,
    REPO_URL,
    TARGET,
    github_release_json,
    github_repo_json,
    gitea_repo_json,
    gitlab_project_json,
    gitlab_release_json,
    make_zip,
    mock_release,
    write_target,
)

GL_HOST = "https://git.example"


async def start(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def submit(hass, data):
    result = await start(hass)
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


def mock_unknown_server(aioclient_mock, host=BASE):
    """Everything 404, like a web server that is no Git."""
    import re

    aioclient_mock.get(re.compile(re.escape(host) + ".*"), status=404)


# --- detection --------------------------------------------------------------------

async def test_detect_gitea(hass, components_dir, aioclient_mock):
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_release(aioclient_mock, "1.0.1", None, sha256="a" * 64)
    mock_unknown_server(aioclient_mock)  # GitLab/GitHub-Enterprise probes
    result = await submit(hass, {"url": REPO_URL + "/", "target_domain": TARGET, "token": "secret"})
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["provider"] == "Forgejo/Gitea"
    assert result["description_placeholders"]["latest"] == "1.0.1"
    assert result["description_placeholders"]["installed"] == "1.0.0"
    assert list(result["data_schema"].schema) == []  # installed already: nothing to install here

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{TARGET} ({REPO})"
    assert result["data"] == {
        "url": REPO_URL, "provider": "gitea", "base_url": BASE, "repo_path": REPO,
        "target_domain": TARGET, "token": "secret",
    }
    assert result["options"] == {"include_prereleases": False}
    assert (components_dir / TARGET / "__init__.py").read_text() == "VERSION = '1.0.0'\n"


async def test_detect_github_by_host(hass, components_dir, aioclient_mock):
    aioclient_mock.get(GH_API, json=github_repo_json())
    aioclient_mock.get(f"{GH_API}/releases/latest", json=github_release_json("1.2.0", "a" * 64))
    result = await submit(hass, {"url": GH_URL, "target_domain": TARGET})
    assert result["description_placeholders"]["provider"] == "GitHub"
    # host is unambiguous: only the GitHub API was asked
    assert all(str(c[1]).startswith("https://api.github.com/") for c in aioclient_mock.mock_calls)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["data"]["provider"] == "github"
    assert result["data"]["base_url"] == "https://github.com"


async def test_detect_gitlab_nested_and_subpath(hass, components_dir, aioclient_mock):
    """https://git.example/gitlab/group/sub/demo: sub path vs. nested group is probed."""
    aioclient_mock.get(GL_API, json=gitlab_project_json())
    aioclient_mock.get(f"{GL_API}/releases", json=[gitlab_release_json("2.0.0", "a" * 64)])
    mock_unknown_server(aioclient_mock, GL_HOST)
    result = await submit(hass, {"url": GL_URL, "target_domain": TARGET})
    assert result["description_placeholders"]["provider"] == "GitLab"
    assert result["description_placeholders"]["repository"] == GL_PATH
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["data"]["provider"] == "gitlab"
    assert result["data"]["base_url"] == GL_BASE
    assert result["data"]["repo_path"] == GL_PATH


async def test_unknown_server(hass, components_dir, aioclient_mock):
    mock_unknown_server(aioclient_mock)
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    assert result["errors"] == {"base": "no_compatible_git"}


async def test_html_answer_is_no_git(hass, components_dir, aioclient_mock):
    import re

    aioclient_mock.get(re.compile(re.escape(BASE) + ".*"), text="<html>hello</html>")
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    assert result["errors"] == {"base": "no_compatible_git"}


async def test_manual_provider_is_forced(hass, components_dir, aioclient_mock):
    """Server would be detected as Forgejo; manual GitLab only asks GitLab and fails clearly."""
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_unknown_server(aioclient_mock)
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET, "provider": "gitlab"})
    assert result["errors"] == {"base": "provider_mismatch"}
    assert all("/api/v4/projects/" in str(c[1]) for c in aioclient_mock.mock_calls)


async def test_manual_provider_used(hass, components_dir, aioclient_mock):
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_release(aioclient_mock, "1.0.1", None, sha256="a" * 64)
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET, "provider": "gitea"})
    assert result["description_placeholders"]["provider"] == "Forgejo/Gitea"
    assert not any("/api/v4/" in str(c[1]) or "/api/v3/" in str(c[1])
                   for c in aioclient_mock.mock_calls)


async def test_detection_timeout(hass, components_dir, aioclient_mock):
    """Hanging server: detection gives up after DETECT_TOTAL_TIMEOUT."""
    import re

    async def hang(method, url, data):
        await asyncio.sleep(3600)

    aioclient_mock.get(re.compile(re.escape(BASE) + ".*"), side_effect=hang)
    with patch("custom_components.repo_installer.providers.DETECT_TOTAL_TIMEOUT", 0.2):
        async with asyncio.timeout(5):
            result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_connection_refused(hass, components_dir, aioclient_mock):
    import re

    aioclient_mock.get(re.compile(re.escape(BASE) + ".*"), exc=ClientError())
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_github_rate_limit_in_flow(hass, components_dir, aioclient_mock):
    aioclient_mock.get(GH_API, status=403, headers={"x-ratelimit-remaining": "0"})
    result = await submit(hass, {"url": GH_URL, "target_domain": TARGET})
    assert result["errors"] == {"base": "rate_limited"}


async def test_invalid_token(hass, components_dir, aioclient_mock):
    import re

    aioclient_mock.get(re.compile(re.escape(BASE) + ".*"), status=401)
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET, "token": "bad"})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_input_errors(hass, components_dir, aioclient_mock):
    result = await submit(hass, {"url": "ftp://x/a/b", "target_domain": "Bad-Domain"})
    assert result["errors"] == {"url": "invalid_url", "target_domain": "invalid_domain"}
    result = await submit(hass, {"url": "http://host/onlyowner", "target_domain": TARGET})
    assert result["errors"] == {"url": "invalid_url"}
    assert aioclient_mock.call_count == 0


async def test_already_configured(hass, components_dir, aioclient_mock):
    MockConfigEntry(domain=DOMAIN, unique_id=TARGET, data={}).add_to_hass(hass)
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- first install from the dialog --------------------------------------------------

def mock_gitea_with_zip(aioclient_mock, zip_bytes, sha256=None):
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_release(aioclient_mock, "1.0.1", zip_bytes, sha256=sha256)
    mock_unknown_server(aioclient_mock)


async def test_install_now_into_empty_custom_components(hass, empty_components_dir, aioclient_mock):
    mock_gitea_with_zip(aioclient_mock, make_zip("1.0.1"))
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["installed"] == "–"
    assert "install_now" in result["data_schema"].schema

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"install_now": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (empty_components_dir / TARGET / "__init__.py").read_text() == "VERSION = '1.0.1'\n"
    assert sorted(p.name for p in empty_components_dir.iterdir()) == [TARGET]  # no backup
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"restart_required_{TARGET}") is not None
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get("update.demo_target_toxic_demo_integration")
    assert state.attributes["installed_version"] == "1.0.1"


async def test_install_now_unchecked_only_binds(hass, empty_components_dir, aioclient_mock):
    mock_gitea_with_zip(aioclient_mock, make_zip("1.0.1"))
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"install_now": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert list(empty_components_dir.iterdir()) == []
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get("update.demo_target_toxic_demo_integration")
    assert state.attributes["installed_version"] == ""
    assert state.state == "on"


@pytest.mark.parametrize(
    ("zip_bytes", "sha256", "message"),
    [
        (make_zip("1.0.1"), "f" * 64, "SHA-256 mismatch"),
        (make_zip("1.0.1", manifest_domain="other"), None, "domain is 'other'"),
    ],
    ids=["wrong-sha", "wrong-domain"],
)
async def test_install_now_failure(hass, empty_components_dir, aioclient_mock, zip_bytes, sha256, message):
    mock_gitea_with_zip(aioclient_mock, zip_bytes, sha256)
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"install_now": True})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "install_failed"}
    assert message in result["description_placeholders"]["error"]
    assert list(empty_components_dir.iterdir()) == []  # no remains
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_folder_appears_meanwhile_is_backed_up(hass, empty_components_dir, aioclient_mock):
    """No silent double install: if the folder exists by now, the replace path with backup runs."""
    mock_gitea_with_zip(aioclient_mock, make_zip("1.0.1"))
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    write_target(empty_components_dir, "0.9.0")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"install_now": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    backup = empty_components_dir / ".repo_installer_backup" / f"{TARGET}-0.9.0"
    assert (backup / "__init__.py").read_text() == "VERSION = '0.9.0'\n"


async def test_release_problem_shown_no_install(hass, empty_components_dir, aioclient_mock):
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_release(aioclient_mock, "1.0.1", None)  # no SHA-256 in the notes
    mock_unknown_server(aioclient_mock)
    result = await submit(hass, {"url": REPO_URL, "target_domain": TARGET})
    assert "SHA-256" in result["description_placeholders"]["latest"]
    assert list(result["data_schema"].schema) == []


async def test_two_entries(hass, components_dir, aioclient_mock):
    aioclient_mock.get(API, json=gitea_repo_json())
    aioclient_mock.get(f"{BASE}/api/v1/repos/toxic/other", json=gitea_repo_json("toxic/other"))
    mock_release(aioclient_mock, "1.0.1", None, sha256="a" * 64)
    mock_release(aioclient_mock, "1.0.1", None, sha256="a" * 64, api=f"{BASE}/api/v1/repos/toxic/other",
                 repo="toxic/other")
    mock_unknown_server(aioclient_mock)
    for repo, domain in ((REPO, TARGET), ("toxic/other", "other_target")):
        result = await submit(hass, {"url": f"{BASE}/{repo}", "target_domain": domain})
        answer = {"install_now": False} if "install_now" in result["data_schema"].schema else {}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], answer)
        assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_options_flow(hass, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=TARGET, data={}, options={"include_prereleases": False})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"include_prereleases": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"include_prereleases": True}


async def test_gitlab_dotcom_by_host(hass, components_dir, aioclient_mock):
    api = "https://gitlab.com/api/v4/projects/g%2Fp"
    aioclient_mock.get(api, json={"id": 5, "path_with_namespace": "g/p"})
    aioclient_mock.get(f"{api}/releases", json=[])
    result = await submit(hass, {"url": "https://gitlab.com/g/p", "target_domain": TARGET})
    assert result["description_placeholders"]["provider"] == "GitLab"
    assert "no releases" in result["description_placeholders"]["latest"]


# --- reauth and reconfigure -----------------------------------------------------------

def make_gitea_entry(hass, token="old-tok-4711"):
    data = {"url": REPO_URL, "provider": "gitea", "base_url": BASE, "repo_path": REPO,
            "target_domain": TARGET}
    if token:
        data["token"] = token
    entry = MockConfigEntry(domain=DOMAIN, unique_id=TARGET, title=f"{TARGET} ({REPO})",
                            data=data, options={"include_prereleases": False})
    entry.add_to_hass(hass)
    return entry


async def test_reauth_flow(hass, components_dir, aioclient_mock):
    entry = make_gitea_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    aioclient_mock.get(API, status=401)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": "still-bad"})
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["token"] == "old-tok-4711"

    aioclient_mock.clear_requests()
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_release(aioclient_mock, "1.0.0", None, sha256="a" * 64)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": "new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == "new"
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "token new"


async def test_reconfigure_change_token(hass, components_dir, aioclient_mock):
    entry = make_gitea_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    assert result["description_placeholders"]["token_state"] == "✓"
    assert "old-tok-4711" not in str(result)  # stored token is never sent to the form

    aioclient_mock.get(API, status=403)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": "bad"})
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_release(aioclient_mock, "1.0.0", None, sha256="a" * 64)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": "new"})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["token"] == "new"


async def test_reconfigure_keep_and_remove_token(hass, components_dir, aioclient_mock):
    aioclient_mock.get(API, json=gitea_repo_json())
    mock_release(aioclient_mock, "1.0.0", None, sha256="a" * 64)
    entry = make_gitea_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["token"] == "old-tok-4711"  # empty field keeps it

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"remove_token": True})
    assert result["reason"] == "reconfigure_successful"
    assert "token" not in entry.data


async def test_reconfigure_change_provider(hass, components_dir, aioclient_mock):
    """Switching the provider re-detects for that provider only; mismatch is shown."""
    entry = make_gitea_entry(hass, token=None)
    mock_unknown_server(aioclient_mock)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"provider": "gitlab"})
    assert result["errors"] == {"base": "provider_mismatch"}
    assert entry.data["provider"] == "gitea"

    aioclient_mock.clear_requests()
    gl_api = f"{BASE}/api/v4/projects/toxic%2Fdemo-integration"
    aioclient_mock.get(gl_api, json={"id": 3, "path_with_namespace": REPO})
    aioclient_mock.get(f"{gl_api}/releases", json=[])
    mock_unknown_server(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"provider": "gitlab"})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["provider"] == "gitlab"
    assert entry.data["base_url"] == BASE
    assert entry.data["repo_path"] == REPO


async def test_reconfigure_repository_not_found(hass, components_dir, aioclient_mock):
    entry = make_gitea_entry(hass)
    aioclient_mock.get(API, status=404)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"remove_token": True})
    assert result["errors"] == {"base": "repository_not_found"}
    assert entry.data["token"] == "old-tok-4711"

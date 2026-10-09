"""Config and options flow."""

from __future__ import annotations

from aiohttp import ClientError
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import API, BASE, REPO, TARGET

DOMAIN = "forgejo_updater"
INPUT = {"url": BASE + "/", "repository": REPO, "target_domain": TARGET, "token": "secret"}


async def start(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    return result


async def test_create_entry(hass, aioclient_mock):
    aioclient_mock.get(API, json={"full_name": REPO})
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{TARGET} ({REPO})"
    assert result["data"] == {"url": BASE, "repository": REPO, "target_domain": TARGET, "token": "secret"}
    assert result["options"] == {"include_prereleases": False}
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "token secret"


async def test_errors(hass, aioclient_mock):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"url": "ftp://x", "repository": "noslash", "target_domain": "Bad-Domain"},
    )
    assert result["errors"] == {
        "url": "invalid_url",
        "repository": "invalid_repository",
        "target_domain": "invalid_domain",
    }

    for kwargs, error in (
        ({"exc": ClientError()}, {"base": "cannot_connect"}),
        ({"status": 401}, {"base": "invalid_auth"}),
        ({"status": 404}, {"repository": "repository_not_found"}),
    ):
        aioclient_mock.clear_requests()
        aioclient_mock.get(API, **kwargs)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
        assert result["errors"] == error


async def test_already_configured(hass, aioclient_mock):
    MockConfigEntry(domain=DOMAIN, unique_id=TARGET, data={}).add_to_hass(hass)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_two_entries(hass, aioclient_mock):
    aioclient_mock.get(API, json={})
    aioclient_mock.get(f"{BASE}/api/v1/repos/toxic/other", json={})
    for repo, domain in ((REPO, TARGET), ("toxic/other", "other_target")):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"url": BASE, "repository": repo, "target_domain": domain}
        )
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

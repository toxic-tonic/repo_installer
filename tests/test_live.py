"""Read-only checks against the real Forgejo (toxic/linknlink-local).

Only GET requests: release metadata and the asset ZIP. The ZIP is validated
and installed into a temp dir, never into a real Home Assistant.
"""

from __future__ import annotations

import json

import pytest
import pytest_socket
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.forgejo_updater.api import ForgejoClient
from custom_components.forgejo_updater.installer import install_zip

pytestmark = pytest.mark.live

FORGEJO = "http://172.16.1.36:3000"
REPO = "toxic/linknlink-local"
EXPECTED = "2024.5.9+ultra1"
EXPECTED_SHA = "a39ea03a35ce08ece0c79562c78f963dccedc5ac9b8e9df51ee1bc1a58157a8a"


@pytest.fixture(autouse=True)
def _allow_forgejo(socket_enabled):
    pytest_socket.socket_allow_hosts(["127.0.0.1", "172.16.1.36"], allow_unix_socket=True)


async def test_live_latest_release(hass, tmp_path):
    client = ForgejoClient(async_get_clientsession(hass), FORGEJO, REPO)
    release = await client.async_get_latest_release(include_prereleases=False)
    assert release.version == EXPECTED
    assert release.tag == "v2024.5.9-ultra1"
    assert release.sha256 == EXPECTED_SHA
    assert release.problem is None
    assert release.asset_name == "linknlink-2024.5.9+ultra1-0a3e4c4.zip"

    blob = await client.async_download_asset(release)  # verifies SHA-256
    comp = tmp_path / "custom_components"
    comp.mkdir()
    assert await hass.async_add_executor_job(install_zip, comp, "linknlink", EXPECTED, blob) is None
    assert json.loads((comp / "linknlink" / "manifest.json").read_text())["version"] == EXPECTED


async def test_live_entity(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    target = tmp_path / "custom_components" / "linknlink"
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(json.dumps({"domain": "linknlink", "version": "2024.5.9"}))

    entry = MockConfigEntry(
        domain="forgejo_updater",
        unique_id="linknlink",
        title=f"linknlink ({REPO})",
        data={"url": FORGEJO, "repository": REPO, "target_domain": "linknlink"},
        options={"include_prereleases": False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get("update.linknlink_toxic_linknlink_local")
    assert state.state == STATE_ON
    assert state.attributes["latest_version"] == EXPECTED

    (target / "manifest.json").write_text(json.dumps({"domain": "linknlink", "version": EXPECTED}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("update.linknlink_toxic_linknlink_local").state == STATE_OFF

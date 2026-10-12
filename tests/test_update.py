"""Update entity: detection, install (good/bad SHA-256, bad ZIPs), offline start, backups."""

from __future__ import annotations

import asyncio

from aiohttp import ClientError
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import (
    API,
    BASE,
    DOMAIN,
    REPO,
    REPO_URL,
    TARGET,
    leftovers,
    make_zip,
    mock_release,
    release_json,
    sha,
    write_target,
)

ENTITY = "update.demo_target_toxic_demo_integration"


def make_entry(hass, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TARGET,
        title=f"{TARGET} ({REPO})",
        data={"url": REPO_URL, "provider": "gitea", "base_url": BASE, "repo_path": REPO,
              "target_domain": TARGET},
        options={"include_prereleases": False, **options},
    )
    entry.add_to_hass(hass)
    return entry


async def setup(hass, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def install(hass, version=None):
    data = {"entity_id": ENTITY}
    if version:
        data["version"] = version
    await hass.services.async_call("update", "install", data, blocking=True)


def backups(components_dir):
    root = components_dir / ".repo_installer_backup"
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


async def test_update_detected(hass, components_dir, aioclient_mock):
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"))
    entry = make_entry(hass)
    await setup(hass, entry)

    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "1.0.0"
    assert state.attributes["latest_version"] == "1.0.1"
    assert state.attributes["title"] == TARGET
    assert state.attributes["release_url"].endswith("/releases/tag/v1.0.1")

    ws_notes = await hass.data["entity_components"]["update"].get_entity(ENTITY).async_release_notes()
    assert "SHA-256" in ws_notes


async def test_no_update_when_current(hass, components_dir, aioclient_mock):
    mock_release(aioclient_mock, "1.0.0", make_zip("1.0.0"))
    await setup(hass, make_entry(hass))
    assert hass.states.get(ENTITY).state == STATE_OFF


@pytest.mark.parametrize(
    ("installed", "latest", "newer"),
    [
        ("2024.5.9+ultra1", "2024.5.9+ultra2", True),
        ("2024.5.9+ultra9", "2024.5.9+ultra10", True),
        ("2024.5.9", "2024.5.9+ultra1", True),
        ("2024.5.9+ultra2", "2024.5.9+ultra1", False),
        ("2024.5.9+ultra1", "2024.5.9+ultra1", False),
    ],
)
async def test_version_compare(hass, components_dir, aioclient_mock, installed, latest, newer):
    write_target(components_dir, installed)
    mock_release(aioclient_mock, latest, None, sha256="0" * 64)
    await setup(hass, make_entry(hass))
    assert hass.states.get(ENTITY).state == (STATE_ON if newer else STATE_OFF)


async def test_install_good_sha(hass, components_dir, aioclient_mock):
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"))
    await setup(hass, make_entry(hass))

    await install(hass)
    await hass.async_block_till_done()

    assert (components_dir / TARGET / "__init__.py").read_text() == "VERSION = '1.0.1'\n"
    assert backups(components_dir) == [f"{TARGET}-1.0.0"]
    assert (components_dir / ".repo_installer_backup" / f"{TARGET}-1.0.0" / "__init__.py").read_text() == "VERSION = '1.0.0'\n"
    assert not (components_dir / ".repo_installer_staging").exists()

    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["installed_version"] == "1.0.1"

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"restart_required_{TARGET}")
    assert issue is not None
    assert issue.translation_placeholders == {"domain": TARGET, "version": "1.0.1"}
    assert not issue.is_persistent


async def test_install_wrong_sha(hass, components_dir, aioclient_mock):
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"), sha256="f" * 64)
    await setup(hass, make_entry(hass))

    with pytest.raises(HomeAssistantError, match="SHA-256 mismatch"):
        await install(hass)

    assert (components_dir / TARGET / "__init__.py").read_text() == "VERSION = '1.0.0'\n"
    assert backups(components_dir) == []
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"restart_required_{TARGET}") is None
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_install_without_sha_in_notes(hass, components_dir, aioclient_mock):
    rel = release_json("1.0.1", None)
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    await setup(hass, make_entry(hass))
    with pytest.raises(HomeAssistantError, match="SHA-256"):
        await install(hass)
    assert not aioclient_mock.mock_calls[-1][1].path.endswith(".zip")  # never downloaded


@pytest.mark.parametrize(
    ("zip_bytes", "message"),
    [
        (make_zip("1.0.1", manifest_version="1.0.2"), "version is '1.0.2'"),
        (make_zip("1.0.1", extra={"other/manifest.json": "{}"}), "Unexpected path"),
        (make_zip("1.0.1", extra={f"{TARGET}/../../evil.py": "x"}), "Unexpected path"),
        (make_zip("1.0.1", domain="wrong_domain"), "Unexpected path"),
        (b"not a zip at all", "Not a ZIP"),
    ],
    ids=["manifest-version", "second-folder", "path-traversal", "wrong-domain", "no-zip"],
)
async def test_install_rejects_bad_zip(hass, components_dir, aioclient_mock, zip_bytes, message):
    mock_release(aioclient_mock, "1.0.1", zip_bytes)  # SHA matches the bad ZIP
    await setup(hass, make_entry(hass))
    with pytest.raises(HomeAssistantError, match=message):
        await install(hass)
    assert (components_dir / TARGET / "__init__.py").read_text() == "VERSION = '1.0.0'\n"
    assert backups(components_dir) == []
    assert not (components_dir.parent / "evil.py").exists()


async def test_foreign_asset_url_rejected(hass, components_dir, aioclient_mock):
    zip_bytes = make_zip("1.0.1")
    rel = release_json("1.0.1", sha(zip_bytes),
                       asset_url=f"{BASE}/someone/else/releases/download/v1.0.1/x.zip")
    aioclient_mock.get(f"{API}/releases/latest", json=rel)
    await setup(hass, make_entry(hass))
    with pytest.raises(HomeAssistantError, match="does not belong"):
        await install(hass)


async def test_backup_rotation(hass, components_dir, aioclient_mock):
    entry = make_entry(hass)
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"))
    await setup(hass, entry)
    coordinator = entry.runtime_data

    for version in ("1.0.1", "1.0.2", "1.0.3"):
        aioclient_mock.clear_requests()
        mock_release(aioclient_mock, version, make_zip(version))
        await coordinator.async_refresh()
        await install(hass)
        await asyncio.sleep(0.01)  # distinct mtimes

    assert backups(components_dir) == [f"{TARGET}-1.0.1", f"{TARGET}-1.0.2"]
    assert hass.states.get(ENTITY).attributes["installed_version"] == "1.0.3"


async def test_provider_offline_at_start(hass, components_dir, aioclient_mock):
    """Setup must not wait on the network; entity is unavailable, entry loaded."""
    gate = asyncio.Event()

    async def hang(method, url, data):
        await gate.wait()
        raise ClientError("connection refused")

    aioclient_mock.get(f"{API}/releases/latest", side_effect=hang)
    entry = make_entry(hass)

    async with asyncio.timeout(5):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()  # does not wait for the hanging request
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE

    gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE

    # Server comes back: manual check (homeassistant.update_entity) recovers
    assert await async_setup_component(hass, "homeassistant", {})
    aioclient_mock.clear_requests()
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"))
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": ENTITY}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_timeout_makes_unavailable(hass, components_dir, aioclient_mock):
    aioclient_mock.get(f"{API}/releases/latest", exc=TimeoutError())
    entry = make_entry(hass)
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE


async def test_prereleases(hass, components_dir, aioclient_mock):
    stable = release_json("1.0.1", "a" * 64, rid=1)
    pre = release_json("1.1.0b1", "b" * 64, prerelease=True, rid=2)
    aioclient_mock.get(f"{API}/releases/latest", json=stable)
    aioclient_mock.get(f"{API}/releases", json=[pre, stable], params={"draft": "false", "limit": "10"})

    entry = make_entry(hass)
    await setup(hass, entry)
    assert hass.states.get(ENTITY).attributes["latest_version"] == "1.0.1"

    hass.config_entries.async_update_entry(entry, options={"include_prereleases": True})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY).attributes["latest_version"] == "1.1.0b1"


async def test_not_installed_offers_first_install(hass, empty_components_dir, aioclient_mock):
    """No custom_components/<domain>: shown as not installed, install creates it without backup."""
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"))
    await setup(hass, make_entry(hass))
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON  # not "unknown": install stays offered in the UI
    assert state.attributes["installed_version"] == ""
    assert state.attributes["release_summary"].startswith("Not installed yet.")
    notes = await hass.data["entity_components"]["update"].get_entity(ENTITY).async_release_notes()
    assert notes.startswith("**Not installed yet.")
    assert "SHA-256" in notes

    await install(hass)
    assert (empty_components_dir / TARGET / "manifest.json").is_file()
    assert leftovers(empty_components_dir) == []  # no backup, no staging
    state = hass.states.get(ENTITY)
    assert state.attributes["installed_version"] == "1.0.1"
    assert state.attributes["release_summary"] is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"restart_required_{TARGET}") is not None


async def test_not_installed_hint_german(hass, empty_components_dir, aioclient_mock):
    hass.config.language = "de"
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"))
    await setup(hass, make_entry(hass))
    summary = hass.states.get(ENTITY).attributes["release_summary"]
    assert summary.startswith("Noch nicht installiert.")


async def test_auth_failure_starts_reauth(hass, components_dir, aioclient_mock):
    """HTTP 401 → ConfigEntryAuthFailed → HA starts the reauth flow by itself."""
    aioclient_mock.get(f"{API}/releases/latest", status=401)
    entry = make_entry(hass)
    await setup(hass, entry)
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    assert flows[0]["context"]["entry_id"] == entry.entry_id


async def test_rate_limit_is_no_reauth(hass, components_dir, aioclient_mock):
    """GitHub rate limit (403 + remaining 0) stays its own message, no reauth."""
    from conftest import GH_API, GH_REPO, GH_URL

    aioclient_mock.get(f"{GH_API}/releases/latest", status=403, headers={"x-ratelimit-remaining": "0"})
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=TARGET, title=f"{TARGET} ({GH_REPO})",
        data={"url": GH_URL, "provider": "github", "base_url": "https://github.com",
              "repo_path": GH_REPO, "target_domain": TARGET},
        options={"include_prereleases": False},
    )
    entry.add_to_hass(hass)
    await setup(hass, entry)
    assert hass.config_entries.flow.async_progress() == []
    assert "Rate-Limit" in str(entry.runtime_data.last_exception)


@pytest.mark.parametrize(
    ("zip_bytes", "sha256", "message"),
    [
        (make_zip("1.0.1"), "f" * 64, "SHA-256 mismatch"),
        (make_zip("1.0.1", manifest_domain="other"), None, "domain is 'other'"),
        (make_zip("1.0.1", domain="other"), None, "Unexpected path"),
    ],
    ids=["wrong-sha", "wrong-manifest-domain", "wrong-folder"],
)
async def test_first_install_failure_leaves_nothing(
    hass, empty_components_dir, aioclient_mock, zip_bytes, sha256, message
):
    mock_release(aioclient_mock, "1.0.1", zip_bytes, sha256=sha256)
    await setup(hass, make_entry(hass))
    with pytest.raises(HomeAssistantError, match=message):
        await install(hass)
    assert list(empty_components_dir.iterdir()) == []
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"restart_required_{TARGET}") is None


async def test_unreadable_manifest_offers_reinstall(hass, components_dir, aioclient_mock):
    (components_dir / TARGET / "manifest.json").write_text("{broken")
    mock_release(aioclient_mock, "1.0.1", make_zip("1.0.1"))
    await setup(hass, make_entry(hass))
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "unknown"
    await install(hass)
    assert backups(components_dir) == [f"{TARGET}-unknown"]


async def test_github_rate_limit_keeps_last_release(hass, components_dir, aioclient_mock):
    """Rate limit is not fatal: the entity keeps the last known release."""
    from conftest import GH_API, GH_REPO, GH_URL, github_release_json

    aioclient_mock.get(f"{GH_API}/releases/latest", json=github_release_json("1.2.0", "a" * 64))
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=TARGET, title=f"{TARGET} ({GH_REPO})",
        data={"url": GH_URL, "provider": "github", "base_url": "https://github.com",
              "repo_path": GH_REPO, "target_domain": TARGET},
        options={"include_prereleases": False},
    )
    entry.add_to_hass(hass)
    await setup(hass, entry)
    entity = "update.demo_target_owner_demo"
    assert hass.states.get(entity).attributes["latest_version"] == "1.2.0"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{GH_API}/releases/latest", status=403, headers={"x-ratelimit-remaining": "0"})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity)
    assert state.state == STATE_ON
    assert state.attributes["latest_version"] == "1.2.0"

"""Repo Installer: install and update custom integrations from Git release ZIPs."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from .const import CONF_BASE_URL, CONF_PROVIDER, CONF_REPO_PATH, CONF_TOKEN
from .coordinator import RepoInstallerConfigEntry, RepoUpdateCoordinator
from .providers import RepoLocation, build_provider

PLATFORMS = [Platform.UPDATE]


async def async_setup_entry(hass: HomeAssistant, entry: RepoInstallerConfigEntry) -> bool:
    # Provider was detected once in the config flow; never re-detected here.
    provider = build_provider(
        async_get_clientsession(hass),
        entry.data[CONF_PROVIDER],
        RepoLocation(URL(entry.data[CONF_BASE_URL]), entry.data[CONF_REPO_PATH]),
        entry.data.get(CONF_TOKEN),
    )
    coordinator = RepoUpdateCoordinator(hass, entry, provider)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # First check runs in the background: HA startup never waits for the network.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"repo_installer first refresh {entry.title}"
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RepoInstallerConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: RepoInstallerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

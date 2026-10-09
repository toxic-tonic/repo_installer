"""Forgejo Updater: update entities for custom integrations released on Forgejo."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ForgejoClient
from .const import CONF_REPOSITORY, CONF_TOKEN, CONF_URL
from .coordinator import ForgejoUpdateCoordinator, ForgejoUpdaterConfigEntry

PLATFORMS = [Platform.UPDATE]


async def async_setup_entry(hass: HomeAssistant, entry: ForgejoUpdaterConfigEntry) -> bool:
    client = ForgejoClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_REPOSITORY],
        entry.data.get(CONF_TOKEN),
    )
    coordinator = ForgejoUpdateCoordinator(hass, entry, client)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # First check runs in the background: HA startup never waits for Forgejo.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"forgejo_updater first refresh {entry.title}"
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ForgejoUpdaterConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ForgejoUpdaterConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

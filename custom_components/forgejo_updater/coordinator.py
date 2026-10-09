"""Polls the latest release and the installed version."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ForgejoClient, ForgejoError, Release
from .const import CONF_INCLUDE_PRERELEASES, CONF_TARGET_DOMAIN, UPDATE_INTERVAL
from .installer import read_installed_version

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateData:
    """Snapshot of installed and available version."""

    installed_version: str | None
    release: Release


type ForgejoUpdaterConfigEntry = ConfigEntry[ForgejoUpdateCoordinator]


class ForgejoUpdateCoordinator(DataUpdateCoordinator[UpdateData]):
    """One coordinator per config entry (= one repository/target domain)."""

    config_entry: ForgejoUpdaterConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ForgejoUpdaterConfigEntry, client: ForgejoClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"forgejo_updater {client.owner}/{client.repo}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.target_domain: str = entry.data[CONF_TARGET_DOMAIN]
        self.components_dir = Path(hass.config.path("custom_components"))

    async def async_read_installed_version(self) -> str | None:
        return await self.hass.async_add_executor_job(
            read_installed_version, self.components_dir, self.target_domain
        )

    async def _async_update_data(self) -> UpdateData:
        include_pre = self.config_entry.options.get(CONF_INCLUDE_PRERELEASES, False)
        try:
            release = await self.client.async_get_latest_release(include_pre)
        except ForgejoError as err:
            raise UpdateFailed(f"Forgejo: {err}") from err
        return UpdateData(await self.async_read_installed_version(), release)

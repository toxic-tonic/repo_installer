"""Polls the latest release and the installed version."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_INCLUDE_PRERELEASES, CONF_TARGET_DOMAIN, UPDATE_INTERVAL
from .installer import read_installed_version
from .providers import Provider, RateLimitError, Release, RepoError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateData:
    """Snapshot of installed and available version."""

    installed_version: str | None  # None: custom_components/<domain> does not exist
    release: Release


type RepoInstallerConfigEntry = ConfigEntry[RepoUpdateCoordinator]


class RepoUpdateCoordinator(DataUpdateCoordinator[UpdateData]):
    """One coordinator per config entry (= one repository/target domain)."""

    config_entry: RepoInstallerConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: RepoInstallerConfigEntry, provider: Provider
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"repo_installer {provider.location.path}",
            update_interval=UPDATE_INTERVAL,
        )
        self.provider = provider
        self.target_domain: str = entry.data[CONF_TARGET_DOMAIN]
        self.components_dir = Path(hass.config.path("custom_components"))

    async def async_read_installed_version(self) -> str | None:
        return await self.hass.async_add_executor_job(
            read_installed_version, self.components_dir, self.target_domain
        )

    async def _async_update_data(self) -> UpdateData:
        include_pre = self.config_entry.options.get(CONF_INCLUDE_PRERELEASES, False)
        try:
            release = await self.provider.async_get_latest_release(include_pre)
        except RateLimitError as err:
            if self.data is not None:
                # Not fatal: keep the last known release until the limit resets
                _LOGGER.warning("%s: %s, keeping last known release", self.name, err)
                return UpdateData(await self.async_read_installed_version(), self.data.release)
            raise UpdateFailed(f"{self.provider.name}: {err}") from err
        except RepoError as err:
            raise UpdateFailed(f"{self.provider.name}: {err}") from err
        return UpdateData(await self.async_read_installed_version(), release)

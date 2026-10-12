"""Update entity per configured repository."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .actions import async_install_release
from .const import DOMAIN, NOT_INSTALLED
from .coordinator import RepoInstallerConfigEntry, RepoUpdateCoordinator
from .installer import UNKNOWN_VERSION, InstallError
from .providers import RepoError
from .version import is_newer


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RepoInstallerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RepoUpdateEntity(entry.runtime_data)])


class RepoUpdateEntity(CoordinatorEntity[RepoUpdateCoordinator], UpdateEntity):
    """Offers the latest release of one custom integration from one repository."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, coordinator: RepoUpdateCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        provider = coordinator.provider
        self._attr_unique_id = entry.entry_id
        self._attr_title = coordinator.target_domain
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=provider.name,
            model=provider.location.path,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=str(provider.location.web_url),
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def installed_version(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.installed_version or NOT_INSTALLED

    @property
    def latest_version(self) -> str | None:
        return self.coordinator.data.release.version if self.coordinator.data else None

    @property
    def release_url(self) -> str | None:
        return self.coordinator.data.release.html_url if self.coordinator.data else None

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        if installed_version in (NOT_INSTALLED, UNKNOWN_VERSION):
            return True  # offer the (first) install
        return is_newer(latest_version, installed_version)

    async def async_release_notes(self) -> str | None:
        return self.coordinator.data.release.body if self.coordinator.data else None

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        data = self.coordinator.data
        if data is None:
            raise HomeAssistantError("No release information available")
        release = data.release
        if version is not None and version != release.version:
            raise HomeAssistantError(f"Only the latest release {release.version} can be installed")
        domain = self.coordinator.target_domain
        try:
            await async_install_release(
                self.hass, self.coordinator.provider, self.coordinator.components_dir,
                domain, release,
            )
        except (RepoError, InstallError, OSError) as err:
            raise HomeAssistantError(f"Installing {domain} {release.version} failed: {err}") from err
        self.coordinator.async_set_updated_data(replace(data, installed_version=release.version))

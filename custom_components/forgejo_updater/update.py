"""Update entity per configured repository."""

from __future__ import annotations

from dataclasses import replace
import logging
import re
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ForgejoError
from .const import DOMAIN
from .coordinator import ForgejoUpdateCoordinator, ForgejoUpdaterConfigEntry
from .installer import InstallError, install_zip

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ForgejoUpdaterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ForgejoUpdateEntity(entry.runtime_data)])


def version_key(version: str) -> tuple:
    """Natural sort key: 2024.5.9+ultra10 > 2024.5.9+ultra9 > 2024.5.9."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.findall(r"\d+|[A-Za-z]+", version)
    )


class ForgejoUpdateEntity(CoordinatorEntity[ForgejoUpdateCoordinator], UpdateEntity):
    """Offers the latest Forgejo release of one custom integration."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, coordinator: ForgejoUpdateCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = entry.entry_id
        self._attr_title = coordinator.target_domain
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Forgejo",
            model=f"{coordinator.client.owner}/{coordinator.client.repo}",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=str(
                coordinator.client.base_url / coordinator.client.owner / coordinator.client.repo
            ),
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def installed_version(self) -> str | None:
        return self.coordinator.data.installed_version if self.coordinator.data else None

    @property
    def latest_version(self) -> str | None:
        return self.coordinator.data.release.version if self.coordinator.data else None

    @property
    def release_url(self) -> str | None:
        return self.coordinator.data.release.html_url if self.coordinator.data else None

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        return latest_version != installed_version and version_key(latest_version) > version_key(
            installed_version
        )

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
            blob = await self.coordinator.client.async_download_asset(release)
            backup_path = await self.hass.async_add_executor_job(
                install_zip, self.coordinator.components_dir, domain, release.version, blob
            )
        except (ForgejoError, InstallError, OSError) as err:
            raise HomeAssistantError(f"Installing {domain} {release.version} failed: {err}") from err

        _LOGGER.info(
            "Installed %s %s from %s (backup: %s); restart required",
            domain, release.version, release.asset_name, backup_path,
        )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"restart_required_{domain}",
            is_fixable=False,
            is_persistent=False,  # gone after the next restart
            severity=ir.IssueSeverity.WARNING,
            translation_key="restart_required",
            translation_placeholders={"domain": domain, "version": release.version},
        )
        self.coordinator.async_set_updated_data(replace(data, installed_version=release.version))

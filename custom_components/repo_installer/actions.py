"""Install a release: shared by the update entity and the config flow."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .installer import install_zip
from .providers import Provider, Release

_LOGGER = logging.getLogger(__name__)


async def async_install_release(
    hass: HomeAssistant,
    provider: Provider,
    components_dir: Path,
    domain: str,
    release: Release,
) -> Path | None:
    """Download, verify and install; raises RepoError/InstallError/OSError.

    Missing target folder: created, no backup. Existing folder: replaced,
    old one kept as backup. Returns the backup path.
    """
    blob = await provider.async_download_asset(release)  # verifies SHA-256
    backup_path = await hass.async_add_executor_job(
        install_zip, components_dir, domain, release.version, blob
    )
    _LOGGER.info(
        "Installed %s %s from %s (backup: %s); restart required",
        domain, release.version, release.asset_name, backup_path,
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"restart_required_{domain}",
        is_fixable=False,
        is_persistent=False,  # gone after the next restart
        severity=ir.IssueSeverity.WARNING,
        translation_key="restart_required",
        translation_placeholders={"domain": domain, "version": release.version},
    )
    return backup_path

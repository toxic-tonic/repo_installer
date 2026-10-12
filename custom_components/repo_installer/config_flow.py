"""Config flow: repository URL → auto-detected provider → confirm (and install)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .actions import async_install_release
from .const import (
    CONF_BASE_URL,
    CONF_INCLUDE_PRERELEASES,
    CONF_INSTALL_NOW,
    CONF_PROVIDER,
    CONF_REPO_PATH,
    CONF_TARGET_DOMAIN,
    CONF_TOKEN,
    CONF_URL,
    DETECT_TOTAL_TIMEOUT,
    DOMAIN,
    DOMAIN_RE,
    PROVIDER_AUTO,
    PROVIDER_GITEA,
    PROVIDER_GITHUB,
    PROVIDER_GITLAB,
)
from .installer import InstallError, read_installed_version
from .providers import (
    DetectionError,
    Provider,
    RateLimitError,
    Release,
    RepoAuthError,
    RepoConnectionError,
    RepoError,
    RepoLocation,
    RepoNotFoundError,
    async_detect,
    build_provider,
    parse_repo_url,
)

_LOGGER = logging.getLogger(__name__)

CONF_REMOVE_TOKEN = "remove_token"

# hassfest forbids URLs inside translations
URL_EXAMPLES = {
    "example_self_hosted": "http://192.168.1.10:3000/owner/repo",
    "example_github": "https://github.com/owner/repo",
}

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
PROVIDER_SELECTOR_OPTIONS = [PROVIDER_AUTO, PROVIDER_GITHUB, PROVIDER_GITLAB, PROVIDER_GITEA]


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Required(CONF_TARGET_DOMAIN): str,
        vol.Optional(CONF_TOKEN): TOKEN_SELECTOR,
        vol.Optional(CONF_INCLUDE_PRERELEASES, default=False): bool,
        vol.Optional(CONF_PROVIDER, default=PROVIDER_AUTO): SelectSelector(
            SelectSelectorConfig(
                options=PROVIDER_SELECTOR_OPTIONS,
                translation_key="provider",
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)


async def _async_validate(provider: Provider) -> str | None:
    """Check provider + token against the API; return a flow error key or None."""
    try:
        await provider.async_probe()
    except RateLimitError:
        return "rate_limited"
    except RepoAuthError:
        return "invalid_auth"
    except RepoNotFoundError:
        return "repository_not_found"  # private repos answer 404 without valid token
    except RepoConnectionError:
        return "cannot_connect"
    except RepoError:
        return "provider_mismatch"
    return None


class RepoInstallerConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per target integration."""

    VERSION = 1

    def __init__(self) -> None:
        self._input: dict[str, Any] = {}
        self._provider: Provider | None = None
        self._release: Release | None = None
        self._release_error: str | None = None
        self._installed_version: str | None = None  # None: not installed

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            domain = user_input[CONF_TARGET_DOMAIN].strip()
            token = (user_input.get(CONF_TOKEN) or "").strip() or None
            try:
                repo_url = parse_repo_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            if not DOMAIN_RE.match(domain):
                errors[CONF_TARGET_DOMAIN] = "invalid_domain"
            if not errors:
                await self.async_set_unique_id(domain)
                self._abort_if_unique_id_configured()
                try:
                    self._provider = await async_detect(
                        async_get_clientsession(self.hass),
                        repo_url,
                        token,
                        user_input.get(CONF_PROVIDER, PROVIDER_AUTO),
                    )
                except DetectionError as err:
                    _LOGGER.debug("Detection for %s failed: %s", repo_url.url, err)
                    errors["base"] = err.reason
                else:
                    self._input = {
                        **user_input,
                        CONF_URL: str(repo_url.url),
                        CONF_TARGET_DOMAIN: domain,
                        CONF_TOKEN: token,
                    }
                    await self._async_fetch_release()
                    return await self.async_step_confirm()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or {}),
            errors=errors,
            description_placeholders=URL_EXAMPLES,
        )

    async def _async_fetch_release(self) -> None:
        assert self._provider is not None
        self._release, self._release_error = None, None
        try:
            async with asyncio.timeout(DETECT_TOTAL_TIMEOUT):
                self._release = await self._provider.async_get_latest_release(
                    self._input.get(CONF_INCLUDE_PRERELEASES, False)
                )
        except (RepoError, TimeoutError) as err:
            self._release_error = str(err) or type(err).__name__
        self._installed_version = await self.hass.async_add_executor_job(
            read_installed_version, self._components_dir, self._input[CONF_TARGET_DOMAIN]
        )

    @property
    def _components_dir(self) -> Path:
        return Path(self.hass.config.path("custom_components"))

    @property
    def _can_install(self) -> bool:
        return (
            self._installed_version is None
            and self._release is not None
            and not self._release.problem
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what was detected; offer the first install if nothing is installed."""
        assert self._provider is not None
        errors: dict[str, str] = {}
        error_detail = ""
        domain = self._input[CONF_TARGET_DOMAIN]
        if user_input is not None:
            if self._can_install and user_input.get(CONF_INSTALL_NOW):
                assert self._release is not None
                try:
                    await async_install_release(
                        self.hass, self._provider, self._components_dir, domain, self._release
                    )
                except (RepoError, InstallError, OSError) as err:
                    errors["base"] = "install_failed"
                    error_detail = str(err)
            if not errors:
                return self._create_entry()

        release = self._release
        if release is None:
            latest = f"– ({self._release_error})"
        elif release.problem:
            latest = f"{release.version} ⚠ {release.problem}"
        else:
            latest = release.version
        schema = (
            vol.Schema({vol.Optional(CONF_INSTALL_NOW, default=True): bool})
            if self._can_install
            else vol.Schema({})
        )
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "provider": self._provider.name,
                "repository": self._provider.location.path,
                "latest": latest,
                "domain": domain,
                "installed": self._installed_version or "–",
                "error": error_detail,
            },
        )

    def _create_entry(self) -> ConfigFlowResult:
        assert self._provider is not None
        location = self._provider.location
        domain = self._input[CONF_TARGET_DOMAIN]
        data = {
            CONF_URL: self._input[CONF_URL],
            CONF_PROVIDER: self._provider.key,
            CONF_BASE_URL: str(location.base_url),
            CONF_REPO_PATH: location.path,
            CONF_TARGET_DOMAIN: domain,
        }
        if self._input.get(CONF_TOKEN):
            data[CONF_TOKEN] = self._input[CONF_TOKEN]
        return self.async_create_entry(
            title=f"{domain} ({location.path})",
            data=data,
            options={
                CONF_INCLUDE_PRERELEASES: self._input.get(CONF_INCLUDE_PRERELEASES, False)
            },
        )

    # --- reauth: HA starts this on ConfigEntryAuthFailed (HTTP 401/403) -------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = (user_input.get(CONF_TOKEN) or "").strip() or None
            provider = self._entry_provider(entry, token)
            if (error := await _async_validate(provider)) is not None:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data=self._with_token(entry.data, token)
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
            description_placeholders={"repository": entry.data[CONF_URL]},
        )

    # --- reconfigure: change token and/or provider ------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_REMOVE_TOKEN):
                token = None
            else:
                # empty field = keep the stored token
                token = (user_input.get(CONF_TOKEN) or "").strip() or entry.data.get(CONF_TOKEN)
            wanted = user_input.get(CONF_PROVIDER, entry.data[CONF_PROVIDER])
            provider: Provider | None = None
            if wanted == entry.data[CONF_PROVIDER]:
                provider = self._entry_provider(entry, token)
                if (error := await _async_validate(provider)) is not None:
                    errors["base"] = error
            else:
                try:
                    provider = await async_detect(
                        async_get_clientsession(self.hass),
                        parse_repo_url(entry.data[CONF_URL]),
                        token,
                        wanted,
                    )
                except DetectionError as err:
                    errors["base"] = err.reason
            if not errors and provider is not None:
                data = {
                    **entry.data,
                    CONF_PROVIDER: provider.key,
                    CONF_BASE_URL: str(provider.location.base_url),
                    CONF_REPO_PATH: provider.location.path,
                }
                return self.async_update_reload_and_abort(
                    entry, data=self._with_token(data, token)
                )
        schema = vol.Schema(
            {
                vol.Optional(CONF_TOKEN): TOKEN_SELECTOR,
                vol.Optional(CONF_REMOVE_TOKEN, default=False): bool,
                vol.Optional(CONF_PROVIDER, default=entry.data[CONF_PROVIDER]): SelectSelector(
                    SelectSelectorConfig(
                        options=PROVIDER_SELECTOR_OPTIONS,
                        translation_key="provider",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "repository": entry.data[CONF_URL],
                "token_state": "✓" if entry.data.get(CONF_TOKEN) else "–",
            },
        )

    def _entry_provider(self, entry, token: str | None) -> Provider:
        return build_provider(
            async_get_clientsession(self.hass),
            entry.data[CONF_PROVIDER],
            RepoLocation(URL(entry.data[CONF_BASE_URL]), entry.data[CONF_REPO_PATH]),
            token,
        )

    @staticmethod
    def _with_token(data: Mapping[str, Any], token: str | None) -> dict[str, Any]:
        new = {k: v for k, v in data.items() if k != CONF_TOKEN}
        if token:
            new[CONF_TOKEN] = token
        return new

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return RepoInstallerOptionsFlow()


class RepoInstallerOptionsFlow(OptionsFlow):
    """Toggle pre-releases."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INCLUDE_PRERELEASES,
                        default=self.config_entry.options.get(CONF_INCLUDE_PRERELEASES, False),
                    ): bool
                }
            ),
        )

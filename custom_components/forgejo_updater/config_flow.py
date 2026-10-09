"""Config flow for Forgejo Updater."""

from __future__ import annotations

from typing import Any

from yarl import URL
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ForgejoAuthError, ForgejoClient, ForgejoError, ForgejoNotFoundError
from .const import (
    CONF_INCLUDE_PRERELEASES,
    CONF_REPOSITORY,
    CONF_TARGET_DOMAIN,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    DOMAIN_RE,
    REPOSITORY_RE,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Required(CONF_REPOSITORY): str,
        vol.Required(CONF_TARGET_DOMAIN): str,
        vol.Optional(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_INCLUDE_PRERELEASES, default=False): bool,
    }
)


class ForgejoUpdaterConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per target integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            repository = user_input[CONF_REPOSITORY].strip().strip("/")
            domain = user_input[CONF_TARGET_DOMAIN].strip()
            token = (user_input.get(CONF_TOKEN) or "").strip() or None
            parsed = URL(url)
            if parsed.scheme not in ("http", "https") or not parsed.host:
                errors[CONF_URL] = "invalid_url"
            if not REPOSITORY_RE.match(repository):
                errors[CONF_REPOSITORY] = "invalid_repository"
            if not DOMAIN_RE.match(domain):
                errors[CONF_TARGET_DOMAIN] = "invalid_domain"
            if not errors:
                await self.async_set_unique_id(domain)
                self._abort_if_unique_id_configured()
                client = ForgejoClient(async_get_clientsession(self.hass), url, repository, token)
                try:
                    await client.async_get_repo()
                except ForgejoAuthError:
                    errors["base"] = "invalid_auth"
                except ForgejoNotFoundError:
                    errors[CONF_REPOSITORY] = "repository_not_found"
                except ForgejoError:
                    errors["base"] = "cannot_connect"
                else:
                    data = {CONF_URL: url, CONF_REPOSITORY: repository, CONF_TARGET_DOMAIN: domain}
                    if token:
                        data[CONF_TOKEN] = token
                    return self.async_create_entry(
                        title=f"{domain} ({repository})",
                        data=data,
                        options={
                            CONF_INCLUDE_PRERELEASES: user_input.get(
                                CONF_INCLUDE_PRERELEASES, False
                            )
                        },
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ForgejoUpdaterOptionsFlow()


class ForgejoUpdaterOptionsFlow(OptionsFlow):
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

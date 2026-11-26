"""Config flow for Hemma."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    DEFAULT_IMMICH_ALBUM_ID,
    DEFAULT_IMMICH_URL,
    DEFAULT_PHOTO_INTERVAL_SECONDS,
    DEFAULT_PHOTO_SYNC_MINUTES,
    DOMAIN,
    PANEL_TITLE,
)

PHOTO_SCHEMA = vol.Schema(
    {
        vol.Optional("immich_url", default=DEFAULT_IMMICH_URL): str,
        vol.Optional("immich_api_key", default=""): str,
        vol.Optional("immich_album_id", default=DEFAULT_IMMICH_ALBUM_ID): str,
        vol.Optional("photo_sync_minutes", default=DEFAULT_PHOTO_SYNC_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
        vol.Optional("photo_interval_seconds", default=DEFAULT_PHOTO_INTERVAL_SECONDS): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        ),
    }
)


class HemmaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance flow that just adds the panel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=PHOTO_SCHEMA)

        return self.async_create_entry(title=PANEL_TITLE, data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HemmaOptionsFlow(config_entry)


class HemmaOptionsFlow(OptionsFlow):
    """Edit the optional Yumi Fotos/Immich photo source."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Fotos", data=user_input)

        values = {
            **PHOTO_SCHEMA({}),
            **self._config_entry.data,
            **self._config_entry.options,
        }
        schema = vol.Schema(
            {
                vol.Optional("immich_url", default=values["immich_url"]): str,
                vol.Optional("immich_api_key", default=values.get("immich_api_key", "")): str,
                vol.Optional("immich_album_id", default=values["immich_album_id"]): str,
                vol.Optional("photo_sync_minutes", default=values["photo_sync_minutes"]): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=1440)
                ),
                vol.Optional("photo_interval_seconds", default=values["photo_interval_seconds"]): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

"""Hemma photo sensor platform."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PHOTO_DATA_KEY
from .photos import HemmaPhotosSensor, HemmaPhotoSync


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: HemmaPhotoSync = hass.data[PHOTO_DATA_KEY]
    async_add_entities([HemmaPhotosSensor(manager)])

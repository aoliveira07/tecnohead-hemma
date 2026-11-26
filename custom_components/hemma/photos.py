"""Yumi Fotos/Immich synchronisation for Hemma's Today screensaver.

The Display add-on has the same small, read-only photo pipeline.  Hemma keeps
the cache in Home Assistant's ``www`` directory so the dashboard can use the
normal ``/local`` URL, while the manifest and credentials stay private to the
integration.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from PIL import Image, ImageEnhance, ImageOps

from .const import (
    DEFAULT_IMMICH_ALBUM_ID,
    DEFAULT_IMMICH_URL,
    DEFAULT_PHOTO_INTERVAL_SECONDS,
    DEFAULT_PHOTO_SYNC_MINUTES,
    DOMAIN,
    PHOTO_FORMAT_VERSION,
    PHOTO_MAX_ITEMS,
    PHOTO_SENSOR_MARKER,
)

_LOGGER = logging.getLogger(__name__)
NORMALIZED_WIDTH = 1920
NORMALIZED_HEIGHT = 1080
PORTRAIT_LONG_EDGE = 1920
PHOTO_ROOT = ("www", "hemma", "photos")
MANIFEST_STORE_KEY = f"{DOMAIN}.photos"


class HemmaPhotosError(RuntimeError):
    """Raised when the photo source cannot be read or normalized."""


class HemmaPhotoSync:
    """Read-only album sync with an HA-persistent, normalized cache."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        self.hass = hass
        self.base_url = str(options.get("immich_url") or DEFAULT_IMMICH_URL).rstrip("/")
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[:-4].rstrip("/")
        self.api_key = str(options.get("immich_api_key") or "").strip()
        self.album_id = str(options.get("immich_album_id") or DEFAULT_IMMICH_ALBUM_ID).strip()
        self.sync_interval_seconds = max(
            60, _as_int(options.get("photo_sync_minutes"), DEFAULT_PHOTO_SYNC_MINUTES) * 60
        )
        self.interval_seconds = max(
            5,
            _as_int(options.get("photo_interval_seconds"), DEFAULT_PHOTO_INTERVAL_SECONDS),
        )
        self.max_photos = PHOTO_MAX_ITEMS
        self.cache_dir = Path(hass.config.path(*PHOTO_ROOT))
        self._store: Store[dict[str, Any]] = Store(hass, PHOTO_FORMAT_VERSION, MANIFEST_STORE_KEY)
        self._manifest: dict[str, Any] = {"photos": []}
        self._loaded = False
        self._lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()
        self._timer_unsub: Callable[[], None] | None = None
        self._initial_task: asyncio.Task | None = None
        self._session = async_get_clientsession(hass)

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.album_id)

    @property
    def manifest(self) -> dict[str, Any]:
        return self._manifest

    async def async_initialize(self) -> None:
        if self._loaded:
            return
        data = await self._store.async_load()
        self._manifest = data if isinstance(data, dict) else {}
        photos = self._manifest.get("photos")
        self._manifest["photos"] = photos if isinstance(photos, list) else []
        self._loaded = True

    def reset_after_setup_error(self, detail: str) -> None:
        """Leave the dashboard usable when an old cache cannot be read."""
        self._manifest = {
            "photos": [],
            "format_version": PHOTO_FORMAT_VERSION,
            "synced_at": None,
            "error": f"Cache de fotos indisponível: {detail[:240]}",
        }
        self._loaded = True

    def record_setup_error(self, detail: str) -> None:
        """Keep a startup failure visible without taking down Hemma."""
        self._manifest["error"] = f"Sincronização de fotos indisponível: {detail[:240]}"

    async def async_start(self) -> None:
        await self.async_initialize()
        self._timer_unsub = async_track_time_interval(
            self.hass, self._scheduled_sync, timedelta(seconds=self.sync_interval_seconds)
        )
        self._initial_task = self.hass.async_create_background_task(
            self.async_sync(), "hemma_photo_initial_sync"
        )

    async def async_unload(self) -> None:
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        if self._initial_task and not self._initial_task.done():
            self._initial_task.cancel()
            try:
                await self._initial_task
            except asyncio.CancelledError:
                pass
        self._initial_task = None

    @callback
    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)

        @callback
        def _unsubscribe() -> None:
            self._listeners.discard(listener)

        return _unsubscribe

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("Hemma: photo state listener failed")

    async def _scheduled_sync(self, _now) -> None:
        await self.async_sync()

    def state(self) -> dict[str, Any]:
        photos = self._manifest.get("photos")
        photos = photos if isinstance(photos, list) else []
        return {
            "configured": self.configured,
            "photos": photos,
            "count": len(photos),
            "synced_at": self._manifest.get("synced_at"),
            "error": self._manifest.get("error"),
            "sync_interval_seconds": self.sync_interval_seconds,
            "interval_seconds": self.interval_seconds,
        }

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        return {"Accept": accept, "x-api-key": self.api_key}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def _request_json(self, method: str, path: str, **kwargs: object) -> object:
        try:
            async with self._session.request(
                method, self._url(path), headers=self._headers(), **kwargs
            ) as response:
                if response.status >= 400:
                    detail = (await response.text())[:180].replace("\n", " ")
                    raise HemmaPhotosError(
                        f"Yumi Fotos respondeu HTTP {response.status}: {detail}"
                    )
                return await response.json(content_type=None)
        except HemmaPhotosError:
            raise
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise HemmaPhotosError(f"Falha de rede ao acessar Yumi Fotos: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise HemmaPhotosError("Yumi Fotos devolveu uma resposta inválida") from exc

    async def _search_assets(self) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        page = 1
        visited: set[int] = set()
        while len(assets) < self.max_photos and page not in visited:
            visited.add(page)
            result = await self._request_json(
                "POST",
                "/api/search/metadata",
                json={
                    "albumIds": [self.album_id],
                    "page": page,
                    "size": self.max_photos,
                    "withExif": False,
                    "withPeople": False,
                    "withStacked": False,
                },
            )
            if not isinstance(result, dict):
                break
            container = result.get("assets", result)
            if isinstance(container, dict):
                items = container.get("items", [])
                next_page = container.get("nextPage")
            else:
                items = container if isinstance(container, list) else []
                next_page = None
            if not isinstance(items, list):
                break
            assets.extend(item for item in items if isinstance(item, dict))
            if not next_page:
                break
            try:
                page = int(next_page)
            except (TypeError, ValueError):
                break
        return assets[: self.max_photos]

    @staticmethod
    def _is_image(asset: dict[str, Any]) -> bool:
        asset_type = str(asset.get("type") or "").upper()
        mime = str(asset.get("originalMimeType") or asset.get("mimeType") or "").lower()
        if asset_type and asset_type not in {"IMAGE", "PHOTO"}:
            return False
        return not mime or mime.startswith("image/")

    @staticmethod
    def _filename(asset_id: str) -> str:
        # A digest avoids putting an external identifier directly into a path.
        digest = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:20]
        return f"{digest}-v{PHOTO_FORMAT_VERSION}.jpg"

    async def _download_preview(
        self, asset_id: str, destination: Path
    ) -> tuple[int, int, bool]:
        try:
            async with self._session.get(
                self._url(f"/api/assets/{quote(asset_id, safe='')}/thumbnail"),
                headers=self._headers("image/*"),
                params={"size": "preview"},
            ) as response:
                if response.status >= 400:
                    raise HemmaPhotosError(
                        f"Yumi Fotos não entregou a miniatura (HTTP {response.status})"
                    )
                data = await response.read()
        except HemmaPhotosError:
            raise
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise HemmaPhotosError(f"Falha ao baixar uma foto do Yumi Fotos: {exc}") from exc
        if not data:
            raise HemmaPhotosError("Yumi Fotos devolveu uma miniatura vazia")
        try:
            return await self.hass.async_add_executor_job(
                self._normalize_image, data, destination
            )
        except Exception as exc:
            raise HemmaPhotosError(f"Não foi possível normalizar a foto: {exc}") from exc

    @staticmethod
    def _normalize_image(source: bytes, destination: Path) -> tuple[int, int, bool]:
        """Normalize a photo while retaining its orientation and full frame.

        Landscape assets keep the legacy 1920x1080 canvas for other Hemma
        surfaces. Portrait assets keep their aspect ratio and are capped at a
        1920px long edge so Today can show the complete vertical photo in its
        full-height centre lane. The small color/contrast lift keeps the
        result from looking washed out on the kiosk display.
        """

        with Image.open(BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")

        portrait = image.height > image.width
        if portrait:
            canvas = image.copy()
            canvas.thumbnail((PORTRAIT_LONG_EDGE, PORTRAIT_LONG_EDGE), Image.Resampling.LANCZOS)
        else:
            canvas = image.resize((NORMALIZED_WIDTH, NORMALIZED_HEIGHT), Image.Resampling.LANCZOS)
        canvas = ImageEnhance.Color(canvas).enhance(1.08)
        canvas = ImageEnhance.Contrast(canvas).enhance(1.04)
        canvas = ImageEnhance.Brightness(canvas).enhance(1.03)

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            canvas.save(temporary, format="JPEG", quality=92, optimize=True, progressive=True)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return canvas.width, canvas.height, portrait

    async def async_sync(self, force: bool = False) -> dict[str, Any]:
        await self.async_initialize()
        async with self._lock:
            if not self.configured:
                self._notify()
                return self.state()
            if not force and not self._sync_due():
                return self.state()
            try:
                assets = [asset for asset in await self._search_assets() if self._is_image(asset)]
                previous = {
                    str(photo.get("id")): photo
                    for photo in self._manifest.get("photos", [])
                    if isinstance(photo, dict) and photo.get("id")
                }
                photos: list[dict[str, Any]] = []
                for asset in assets:
                    asset_id = str(asset.get("id") or "").strip()
                    if not asset_id:
                        continue
                    filename = self._filename(asset_id)
                    destination = self.cache_dir / filename
                    prior = previous.get(asset_id, {})
                    changed = (
                        not destination.is_file()
                        or prior.get("updated_at") != asset.get("updatedAt")
                        or prior.get("checksum") != asset.get("checksum")
                        or prior.get("format_version") != PHOTO_FORMAT_VERSION
                    )
                    if changed:
                        width, height, portrait = await self._download_preview(
                            asset_id, destination
                        )
                    else:
                        width = _as_int(prior.get("width"), NORMALIZED_WIDTH)
                        height = _as_int(prior.get("height"), NORMALIZED_HEIGHT)
                        portrait = bool(prior.get("portrait")) or height > width
                    photos.append(
                        {
                            "id": asset_id,
                            "filename": filename,
                            "url": f"/local/hemma/photos/{quote(filename, safe='')}",
                            "name": str(asset.get("originalFileName") or filename),
                            "created_at": asset.get("fileCreatedAt") or asset.get("localDateTime"),
                            "updated_at": asset.get("updatedAt"),
                            "checksum": asset.get("checksum"),
                            "format_version": PHOTO_FORMAT_VERSION,
                            "width": width,
                            "height": height,
                            "portrait": portrait,
                            "orientation": "portrait" if portrait else "landscape",
                        }
                    )
                self._manifest = {
                    "photos": photos,
                    "format_version": PHOTO_FORMAT_VERSION,
                    "synced_at": datetime.now(UTC).isoformat(),
                    "error": None,
                }
                await self._store.async_save(self._manifest)
            except HemmaPhotosError as exc:
                self._manifest["error"] = str(exc)
                await self._store.async_save(self._manifest)
                _LOGGER.warning("Hemma: photo sync failed: %s", exc)
            self._notify()
            return self.state()

    def _sync_due(self) -> bool:
        if self._manifest.get("format_version") != PHOTO_FORMAT_VERSION:
            return True
        value = self._manifest.get("synced_at")
        if not isinstance(value, str) or not value:
            return True
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError:
            return True
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return datetime.now(UTC) - timestamp >= timedelta(seconds=self.sync_interval_seconds)


class HemmaPhotosSensor(SensorEntity):
    """Expose the private manifest to Lovelace without exposing the API key."""

    _attr_has_entity_name = False
    _attr_name = "Fotos da família"
    _attr_unique_id = "hemma_family_photos"
    _attr_icon = "mdi:image-multiple-outline"
    _attr_should_poll = False

    def __init__(self, manager: HemmaPhotoSync) -> None:
        self._manager = manager
        self._unsubscribe: Callable[[], None] | None = None
        self._attr_native_value = 0
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        self._unsubscribe = self._manager.subscribe(self._state_changed)
        self._state_changed()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _state_changed(self) -> None:
        data = self._manager.state()
        self._attr_native_value = data["count"]
        self._attr_extra_state_attributes = {
            PHOTO_SENSOR_MARKER: True,
            "photos": data["photos"],
            "count": data["count"],
            "configured": data["configured"],
            "synced_at": data["synced_at"],
            "error": data["error"],
            "interval_seconds": data["interval_seconds"],
        }
        if self.hass is not None:
            self.async_write_ha_state()


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def manager_from_entry(hass: HomeAssistant, entry: ConfigEntry) -> HemmaPhotoSync:
    options = {**entry.data, **entry.options}
    return HemmaPhotoSync(hass, options)

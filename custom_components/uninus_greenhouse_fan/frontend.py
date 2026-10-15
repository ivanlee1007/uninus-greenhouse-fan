"""Serve the bundled Lovelace card and keep its dashboard resource current."""
from pathlib import Path
import logging

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_YAML

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
CARD_VERSION = "0.5.4"
CARD_PATH = f"/{DOMAIN}/card.js"
CARD_URL = f"{CARD_PATH}?v={CARD_VERSION}"


async def async_ensure_card_resource(hass) -> None:
    """Register the JS path once, upserting only our own storage resource."""
    import asyncio
    from functools import partial
    data = hass.data[DOMAIN]
    async with data.setdefault('_card_path_lock', asyncio.Lock()):
        if not data.get("_path_registered"):
            path = str(Path(__file__).with_name("card.js"))
            app = getattr(hass.http, 'app', None)
            existing = next((route for route in app.router.routes()
                if route.method == 'GET' and route.resource.canonical == CARD_PATH), None) if app is not None else None
            if existing is not None:
                # HA adds the route before CORS setup. A later failure can
                # leave that route installed with our success flag unset.
                try:
                    from homeassistant.components.http.server import KEY_ALLOW_CONFIGURED_CORS, _serve_file
                except ImportError:
                    from homeassistant.components.http import KEY_ALLOW_CONFIGURED_CORS, _serve_file
                handler = existing.handler
                if (not isinstance(handler, partial) or handler.func is not _serve_file
                        or handler.args != (path,) or handler.keywords):
                    raise ValueError('Card route belongs to another resource')
                app[KEY_ALLOW_CONFIGURED_CORS](existing)
            else:
                await hass.http.async_register_static_paths([
                    StaticPathConfig(CARD_PATH, path, cache_headers=False)
                ])
            data["_path_registered"] = True

    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None:
        _LOGGER.warning("Lovelace unavailable; add %s as a module resource when enabled", CARD_URL)
        return
    if lovelace.resource_mode == MODE_YAML:
        _LOGGER.warning("Lovelace YAML mode: add %s as a module in YAML resources", CARD_URL)
        return
    resources = lovelace.resources
    await resources.async_get_info()  # Ensure the collection has loaded from disk.
    owned = [item for item in resources.async_items() if item.get("url", "").split("?")[0] == CARD_PATH]
    if len(owned) > 1:
        raise ValueError("Duplicate UNiNUS greenhouse fan resources; resolve before updating")
    if owned:
        item = owned[0]
        if item.get("url") != CARD_URL or item.get("type") != "module":
            await resources.async_update_item(item["id"], {"url": CARD_URL, "res_type": "module"})
    else:
        await resources.async_create_item({"url": CARD_URL, "res_type": "module"})

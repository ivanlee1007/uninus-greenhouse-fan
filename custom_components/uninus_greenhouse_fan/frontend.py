"""Serve the bundled Lovelace card and keep its dashboard resource current."""
from pathlib import Path
import logging

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_YAML

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
CARD_VERSION = "0.4.0"
CARD_PATH = f"/{DOMAIN}/card.js"
CARD_URL = f"{CARD_PATH}?v={CARD_VERSION}"


async def async_ensure_card_resource(hass) -> None:
    """Register the JS path once, upserting only our own storage resource."""
    data = hass.data[DOMAIN]
    if not data.get("_path_registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig(CARD_PATH, str(Path(__file__).with_name("card.js")), cache_headers=False)
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

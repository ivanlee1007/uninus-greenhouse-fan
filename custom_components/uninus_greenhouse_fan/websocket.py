"""Authenticated WebSocket contract shared by the Lovelace editor and runtime."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .registry import Conflict


@websocket_api.websocket_command({"type": f"{DOMAIN}/groups"})
def ws_groups(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """List actual config entries for authenticated clients, without writes."""
    runtime = hass.data.get(DOMAIN, {})
    connection.send_result(msg["id"], [
        {"entry_id": entry.entry_id, "name": entry.title,
         "loaded": runtime.get(entry.entry_id) is not None and runtime[entry.entry_id].active}
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.domain == DOMAIN
    ])


def _group(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    entry = next((entry for entry in hass.config_entries.async_entries(DOMAIN)
                  if entry.domain == DOMAIN and entry.entry_id == msg["entry_id"]), None)
    group = hass.data.get(DOMAIN, {}).get(msg["entry_id"]) if entry else None
    if group is None or not group.active:
        connection.send_error(msg["id"], "not_found", "Fan control group is missing or unloaded")
        return None
    return group


@websocket_api.websocket_command({"type": f"{DOMAIN}/get", vol.Required("entry_id"): str})
def ws_get(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Authenticated clients read the canonical group view."""
    group = _group(hass, connection, msg)
    if group:
        connection.send_result(msg["id"], group.snapshot())


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/bind",
    vol.Required("entry_id"): str,
    vol.Required("expected_revision"): vol.All(int, vol.Range(min=0)),
    vol.Required("fan_entity"): str,
    vol.Required("temperature_entity"): str,
    vol.Required("humidity_entity"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_bind(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Admin-only, optimistic-concurrency binding mutation."""
    group = _group(hass, connection, msg)
    if group is None:
        return
    try:
        result = await group.bind(
            msg["expected_revision"], msg["fan_entity"],
            msg["temperature_entity"], msg["humidity_entity"],
        )
    except Conflict:
        connection.send_error(msg["id"], "conflict", "Binding changed; refresh and reconcile your draft")
    except ValueError as error:
        connection.send_error(msg["id"], "invalid_binding", str(error))
    except Exception:
        connection.send_error(msg["id"], "save_failed", "Could not persist sensor binding")
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/manual",
    vol.Required("entry_id"): str,
    vol.Required("fan_entity"): str,
    vol.Required("mode"): vol.In(("on", "off", "auto")),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_manual(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Admin-only manual hold or explicit return to auto."""
    group = _group(hass, connection, msg)
    if group is None:
        return
    try:
        result = await group.manual(msg["fan_entity"], msg["mode"])
    except ValueError as error:
        connection.send_error(msg["id"], "invalid_manual_action", str(error))
    except Exception:
        connection.send_error(msg["id"], "action_failed", "Fan command failed")
    else:
        connection.send_result(msg["id"], result)


def register_commands(hass: HomeAssistant) -> None:
    """Register one command set even when several group entries exist."""
    for command in (ws_groups, ws_get, ws_bind, ws_manual):
        websocket_api.async_register_command(hass, command)

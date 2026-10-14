"""Authenticated WebSocket contract shared by the Lovelace editor and runtime."""
from __future__ import annotations

import logging
from math import isfinite

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .registry import Conflict

_LOGGER = logging.getLogger(__name__)


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
        _LOGGER.exception("Could not apply sensor binding for group %s", msg["entry_id"])
        connection.send_error(
            msg["id"], "binding_failed",
            "無法完成感測來源綁定；請檢查 Home Assistant 日誌詳細錯誤，重新讀取綁定並核對草稿後重試",
        )
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


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/set_control_mode",
    vol.Required("entry_id"): str,
    vol.Required("control_mode"): vol.In(("auto", "manual")),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set_control_mode(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Admin-only passive control-mode transaction for one actual loaded group."""
    group = _group(hass, connection, msg)
    if group is None:
        return
    try:
        result = await group.set_control_mode(msg["control_mode"])
    except ValueError as error:
        connection.send_error(msg["id"], "invalid_control_mode", str(error))
    except Exception:
        _LOGGER.exception("Could not persist control mode for group %s", msg["entry_id"])
        connection.send_error(msg["id"], "mode_failed", "控制模式儲存失敗；請重新讀取群組並檢查日誌")
    else:
        connection.send_result(msg["id"], result)


def _finite_number(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise vol.Invalid('Thresholds must be finite numbers, not booleans or strings')
    return value


def _policy_revision(value):
    if type(value) is not int or value < 0:
        raise vol.Invalid('Invalid policy revision')
    return value


@websocket_api.websocket_command({
    'type': f'{DOMAIN}/save_thresholds',
    vol.Required('entry_id'): str,
    vol.Required('expected_policy_revision'): _policy_revision,
    vol.Required('thresholds'): vol.Schema({vol.Required(key): _finite_number for key in ('temperature_on', 'temperature_off', 'humidity_on', 'humidity_off')}),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save_thresholds(hass, connection, msg):
    """Admin-only, verified passive policy save for an actual loaded entry."""
    group = _group(hass, connection, msg)
    if group is None:
        return
    try:
        result = await group.save_thresholds(msg['thresholds'], msg['expected_policy_revision'])
    except Conflict:
        connection.send_error(msg['id'], 'conflict', '門檻已由其他介面修改；請取消草稿並重新讀取後調整')
    except (ValueError, TypeError) as error:
        connection.send_error(msg['id'], 'invalid_policy', str(error))
    except Exception:
        _LOGGER.exception('Could not save thresholds for group %s', msg['entry_id'])
        connection.send_error(msg['id'], 'save_failed', '門檻儲存失敗；草稿保留，控制仍使用原門檻。請檢查日誌或取消並重新讀取。')
    else:
        connection.send_result(msg['id'], result)


def register_commands(hass: HomeAssistant) -> None:
    """Register one command set even when several group entries exist."""
    for command in (ws_groups, ws_get, ws_bind, ws_manual, ws_set_control_mode, ws_save_thresholds):
        websocket_api.async_register_command(hass, command)

"""UNiNUS greenhouse fan integration: per-group policy and safe control."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DEFAULT_POLICY, DOMAIN, POLICY_KEYS, SCAN_SECONDS
from .controller import Controller, Policy
from .registry import Registry
from .sensors import safe_reading


def _entry_policy(entry: ConfigEntry) -> Policy:
    values = {key: entry.options.get(key, entry.data.get(key, DEFAULT_POLICY[key])) for key in POLICY_KEYS}
    return Policy(**values)


class FanGroup:
    """One HA config entry; no automatic action unless explicitly bound."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, registry: Registry):
        self.hass = hass
        self.entry = entry
        self.registry = registry
        self.controller = Controller(_entry_policy(entry))
        for fan, mode in registry.manual_modes.items():
            self.controller.set_mode(fan, mode)
        self._lock = asyncio.Lock()
        self._unsubs = []

    def snapshot(self) -> dict:
        return {
            **self.registry.snapshot(),
            "policy": self.controller.policy.as_dict(),
            "runtime": {
                fan: {**self.controller.status(fan), "on": self._fan_state(fan) == "on"}
                for fan in self.registry.bindings
            },
        }

    def _fan_state(self, entity_id: str) -> str | None:
        state = self.hass.states.get(entity_id)
        return state.state if state else None

    async def bind(self, revision: int, fan: str, temperature: str, humidity: str) -> dict:
        """An authoritative revisioned write; never guess a sensor source."""
        from .sensors import compatible_sensor

        if not compatible_sensor(self.hass.states.get(temperature), "temperature") or not compatible_sensor(self.hass.states.get(humidity), "humidity"):
            raise ValueError("Temperature requires °C and humidity requires %")
        async with self._lock:
            result = await self.registry.bind(revision, fan, temperature, humidity, self.hass.states)
            self.controller.reset(fan)
            return {**result, "policy": self.controller.policy.as_dict(), "runtime": self.snapshot()["runtime"]}

    async def manual(self, fan: str, mode: str) -> dict:
        """A manual command holds automation until explicit resume."""
        if fan not in self.registry.bindings or mode not in ("on", "off", "auto"):
            raise ValueError("Fan is not bound or mode is invalid")
        async with self._lock:
            if mode != "auto" and self._fan_state(fan) not in ("on", "off"):
                raise ValueError("Fan state unavailable")
            # Save the hold first: if device service fails, automation remains held.
            await self.registry.set_mode(fan, mode)
            self.controller.set_mode(fan, mode)
            if mode != "auto":
                await self.hass.services.async_call(
                    fan.split(".", 1)[0], "turn_on" if mode == "on" else "turn_off",
                    {"entity_id": fan}, blocking=True,
                )
            return self.snapshot()

    async def evaluate_all(self) -> None:
        """The same persistent-duration gate runs on every periodic evaluation."""
        async with self._lock:
            now = monotonic()
            for fan, binding in tuple(self.registry.bindings.items()):
                temperature = safe_reading(self.hass.states.get(binding["temperature_entity"]), "temperature")
                humidity = safe_reading(self.hass.states.get(binding["humidity_entity"]), "humidity")
                action = self.controller.evaluate(fan, True, self._fan_state(fan), temperature, humidity, now)
                if action is None:
                    continue
                # Do not act on a fan whose state/source changed during evaluation.
                if self._fan_state(fan) not in ("on", "off") or self.registry.bindings.get(fan) != binding:
                    self.controller.reset(fan)
                    continue
                try:
                    await self.hass.services.async_call(
                        fan.split(".", 1)[0], "turn_on" if action == "on" else "turn_off",
                        {"entity_id": fan}, blocking=True,
                    )
                except Exception:  # HA service failures must not disable evaluation of other fans.
                    self.controller.reset(fan)
                    self.controller._state(fan)["reason"] = "action_failed"

    def start(self) -> None:
        @callback
        def _tick(_now) -> None:
            self.hass.async_create_task(self.evaluate_all())

        self._unsubs.append(async_track_time_interval(self.hass, _tick, timedelta(seconds=SCAN_SECONDS)))
        self._unsubs.append(self.entry.add_update_listener(self._options_updated))

    async def _options_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        async with self._lock:
            self.controller.set_policy(_entry_policy(entry))

    def stop(self) -> None:
        for unsubscribe in self._unsubs:
            unsubscribe()
        self._unsubs.clear()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load authoritative bindings; register commands once for all entries."""
    from .websocket import register_commands
    from .frontend import async_ensure_card_resource

    data = hass.data.setdefault(DOMAIN, {})
    await async_ensure_card_resource(hass)
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    registry = Registry(entry.entry_id, await store.async_load(), store.async_save)
    group = FanGroup(hass, entry, registry)
    data[entry.entry_id] = group
    if not data.get("_commands_registered"):
        register_commands(hass)
        data["_commands_registered"] = True
    group.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop periodic control without deleting stored bindings."""
    group = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if group:
        group.stop()
    return True

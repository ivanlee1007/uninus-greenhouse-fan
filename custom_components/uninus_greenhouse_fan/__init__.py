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
        self._manual_targets = set(registry.manual_modes)
        self.active = True
        self._lock = asyncio.Lock()
        self._unsubs = []

    def snapshot(self) -> dict:
        runtime = {}
        # Retain resumed manual-only targets in this runtime; only holds persist.
        for fan in sorted(row["fan_entity"] for row in self.registry.devices.values()):
            status = self.controller.status(fan)
            if fan not in self.registry.bindings and status["mode"] == "auto":
                status["reason"] = "unbound"
            runtime[fan] = {**status, "on": self._fan_state(fan) == "on"}
        return {
            **self.registry.snapshot(),
            "policy": self.controller.policy.as_dict(),
            "runtime": runtime,
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
            self._require_active()
            result = await self.registry.bind(revision, fan, temperature, humidity, self.hass.states)
            self.controller.reset(fan)
            return {**result, "policy": self.controller.policy.as_dict(), "runtime": self.snapshot()["runtime"]}

    async def manual(self, fan: str, mode: str) -> dict:
        """A manual command holds automation until explicit resume."""
        if not self.registry.valid_device(fan) or not self.registry.owned(fan) or mode not in ("on", "off", "auto"):
            raise ValueError("Invalid fan or mode")
        async with self._lock:
            self._require_active()
            self._require_exclusive(fan)
            if mode != "auto" and self._fan_state(fan) not in ("on", "off"):
                raise ValueError("Fan state unavailable")
            # Save the hold first: if device service fails, automation remains held.
            await self.registry.set_mode(fan, mode)
            self._require_active()
            self._require_exclusive(fan)
            self.controller.set_mode(fan, mode)
            self._manual_targets.add(fan)
            if mode != "auto":
                if self._fan_state(fan) not in ("on", "off"):
                    raise ValueError("Fan state unavailable")
                await self.hass.services.async_call(
                    fan.split(".", 1)[0], "turn_on" if mode == "on" else "turn_off",
                    {"entity_id": fan}, blocking=True,
                )
            return self.snapshot()

    async def evaluate_all(self) -> None:
        """The same persistent-duration gate runs on every periodic evaluation."""
        async with self._lock:
            if not self.active:
                return
            now = monotonic()
            for fan, binding in tuple(self.registry.bindings.items()):
                if not self.active:
                    return
                try:
                    self._require_exclusive(fan)
                except ValueError:
                    self.controller.reset(fan)
                    continue
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

    def _require_exclusive(self, fan):
        runtime = self.hass.data.get(DOMAIN, {})
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == self.entry.entry_id:
                continue
            group = runtime.get(entry.entry_id)
            if group is None or not group.active:
                raise ValueError('Another group is unloaded; reload all groups before assigning or controlling outputs')
            if group.registry.owned(fan):
                raise ValueError('duplicate_output')

    async def save_device(self, identity, record, expected_revision=None):
        lock = self.hass.data.setdefault(DOMAIN, {}).setdefault('_devices_lock', asyncio.Lock())
        async with lock, self._lock:
            self._require_active()
            self._require_exclusive(record.get('fan_entity'))
            from .sensors import compatible_sensor
            old = self.registry.devices.get(identity)
            for field, kind in (('temperature_entity', 'temperature'), ('humidity_entity', 'humidity')):
                entity = record.get(field)
                if entity and not compatible_sensor(self.hass.states.get(entity), kind):
                    # Keep a configured offline source when editing its display name.
                    if not old or old.get(field) != entity:
                        raise ValueError(field)
            output = record.get('fan_entity')
            if self.hass.states.get(output) is None and (not old or old['fan_entity'] != output):
                raise ValueError('fan_entity')
            result = await self.registry.save_device(identity, record, expected_revision)
            if old and old['fan_entity'] != result['fan_entity']:
                self.controller._states.pop(old['fan_entity'], None)
                self._manual_targets.discard(old['fan_entity'])
                self.controller._states.pop(result['fan_entity'], None)
            if old is None or any(old.get(key) != result.get(key) for key in ('fan_entity', 'temperature_entity', 'humidity_entity')):
                self.controller.reset(result['fan_entity'])
            return result

    async def remove_device(self, identity, expected_revision=None):
        async with self._lock:
            self._require_active()
            old = self.registry.devices.get(identity)
            await self.registry.remove_device(identity, expected_revision)
            self.controller._states.pop(old['fan_entity'], None)
            self._manual_targets.discard(old['fan_entity'])

    def _require_active(self) -> None:
        if not self.active:
            raise ValueError("Fan control group is unloaded")
        if getattr(getattr(self.hass, 'state', None), 'value', None) == 'STOPPING':
            raise OSError('Home Assistant is stopping; fan control is disabled')

    def stop(self) -> None:
        self.active = False
        self.registry.close()
        for unsubscribe in self._unsubs:
            unsubscribe()
        self._unsubs.clear()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Keep discovery available even when all entries are unloaded."""
    from .websocket import register_commands

    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("_commands_registered"):
        register_commands(hass)
        data["_commands_registered"] = True
    return True


def _lifecycle_lock(hass: HomeAssistant, entry: ConfigEntry) -> asyncio.Lock:
    # Retain this lock after runtime removal so a reload cannot outrun drain.
    locks = hass.data.setdefault(DOMAIN, {}).setdefault('_lifecycle_locks', {})
    return locks.setdefault(entry.entry_id, asyncio.Lock())


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Serialize loading with completion of the prior runtime's mutations."""
    async with _lifecycle_lock(hass, entry):
        await _async_drain_entry(hass, entry)
        return await _async_setup_entry(hass, entry)


async def _async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load authoritative bindings; register commands once for all entries."""
    from .frontend import async_ensure_card_resource

    data = hass.data.setdefault(DOMAIN, {})
    await async_ensure_card_resource(hass)
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}", atomic_writes=True)
    from .persistence import VerifiedStore
    group = None
    def fail_closed():
        if group is not None:
            group.stop()
    persistence = VerifiedStore(hass, store, None, fail_closed)
    if persistence.path:
        await hass.async_add_executor_job(persistence.check_quarantine)
    loaded = await store.async_load()
    persistence.previous = loaded
    registry = Registry(entry.entry_id, loaded, persistence.save)
    if registry.migrated:
        await persistence.save(registry.payload())
        registry.migrated = False
    group = FanGroup(hass, entry, registry)
    data[entry.entry_id] = group
    await async_setup(hass, {})
    group.start()
    return True


async def _async_drain_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = hass.data[DOMAIN]
    group = data.get(entry.entry_id)
    if group is None:
        return
    group.stop()

    async def drain():
        # Group -> registry matches mutation lock order. The registry lock covers
        # save() from before scheduling _prepare through durable publication.
        async with group._lock, group.registry._lock:
            pass

    task = asyncio.create_task(drain())
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()
    data.pop(entry.entry_id)
    if cancelled:
        raise asyncio.CancelledError


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Gate control immediately, then drain before permitting another setup."""
    async with _lifecycle_lock(hass, entry):
        await _async_drain_entry(hass, entry)
    return True

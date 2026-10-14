"""Per-entry, revisioned authoritative sensor binding registry."""
import asyncio
import re
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid4, uuid5


class Conflict(Exception):
    """Optimistic concurrency revision mismatch."""


class Registry:
    def __init__(self, entry_id, data, save):
        data = data or {}
        revision = data.get('revision', 0)
        bindings = data.get('bindings', {})
        modes = data.get('manual_modes', {})
        control_mode = data.get('control_mode', 'auto')
        if control_mode not in ('auto', 'manual'):
            raise ValueError('Invalid stored control mode')
        if type(revision) is not int or revision < 0 or not isinstance(bindings, dict) or not isinstance(modes, dict):
            raise ValueError('Invalid stored registry')
        for fan, pair in bindings.items():
            if not self._valid_pair(fan, pair.get('temperature_entity') if isinstance(pair, dict) else None, pair.get('humidity_entity') if isinstance(pair, dict) else None):
                raise ValueError('Invalid stored binding')
        if any(not self.valid_device(fan) or mode not in ('on', 'off') for fan, mode in modes.items()):
            raise ValueError('Invalid stored manual hold')
        self.entry_id = entry_id
        self.revision = revision
        self.bindings = deepcopy(bindings)
        self.manual_modes = deepcopy(modes)
        self.control_mode = control_mode
        self._save = save
        self._lock = asyncio.Lock()
        self._closed = False
        legacy_inventory = 'devices' not in data
        self.migrated = legacy_inventory or 'control_mode' not in data
        self.devices = deepcopy(data.get('devices', {}))
        if legacy_inventory:
            for fan in sorted(set(bindings) | set(modes)):
                identity = uuid5(NAMESPACE_URL, f'{entry_id}/{fan}').hex
                self.devices[identity] = {'device_id': identity, 'name': fan, 'fan_entity': fan,
                    'temperature_entity': bindings.get(fan, {}).get('temperature_entity', ''),
                    'humidity_entity': bindings.get(fan, {}).get('humidity_entity', '')}
        if not isinstance(self.devices, dict):
            raise ValueError('Invalid device inventory')
        outputs = set()
        for identity, row in self.devices.items():
            if not isinstance(identity, str) or not identity or not isinstance(row, dict) or row.get('device_id') != identity:
                raise ValueError('Invalid device identity')
            record = self.validate_record(row)
            if record['fan_entity'] in outputs:
                raise ValueError('Duplicate stored output')
            outputs.add(record['fan_entity'])
            self.devices[identity] = {'device_id': identity, **record}
        if self._bindings(self.devices) != self.bindings or any(fan not in outputs for fan in modes):
            raise ValueError('Inconsistent stored inventory')

    def close(self):
        """Reject queued/new mutations while allowing the lock holder to settle."""
        self._closed = True

    def _require_open(self):
        if self._closed:
            raise ValueError('Fan control group is unloaded')

    @classmethod
    def validate_record(cls, record):
        name, fan = record.get('name', ''), record.get('fan_entity', '')
        temperature, humidity = record.get('temperature_entity', '') or '', record.get('humidity_entity', '') or ''
        if not isinstance(name, str) or not name.strip():
            raise ValueError('name')
        if not cls.valid_device(fan):
            raise ValueError('fan_entity')
        if bool(temperature) != bool(humidity) or (temperature and not cls._valid_pair(fan, temperature, humidity)):
            raise ValueError('sensor_pair')
        return {'name': name.strip(), 'fan_entity': fan, 'temperature_entity': temperature, 'humidity_entity': humidity}

    @staticmethod
    def _bindings(devices):
        return {row['fan_entity']: {key: row[key] for key in ('temperature_entity', 'humidity_entity')}
                for row in devices.values() if row['temperature_entity'] and row['humidity_entity']}

    def owned(self, fan):
        return any(row['fan_entity'] == fan for row in self.devices.values())

    def device_for_output(self, fan):
        return next((deepcopy(row) for row in self.devices.values() if row['fan_entity'] == fan), None)

    def payload(self):
        return {'revision': self.revision, 'devices': deepcopy(self.devices), 'bindings': deepcopy(self.bindings), 'manual_modes': deepcopy(self.manual_modes), 'control_mode': self.control_mode}

    async def _commit(self, devices, modes, control_mode=None):
        control_mode = self.control_mode if control_mode is None else control_mode
        bindings, revision = self._bindings(devices), self.revision + 1
        await self._save({'revision': revision, 'devices': deepcopy(devices), 'bindings': bindings, 'manual_modes': deepcopy(modes), 'control_mode': control_mode})
        self.devices, self.bindings, self.manual_modes, self.revision = devices, bindings, modes, revision
        self.control_mode = control_mode
        self.migrated = False

    async def set_control_mode(self, mode):
        """One durable transaction; global auto explicitly clears every hold."""
        if mode not in ('auto', 'manual'):
            raise ValueError('Invalid control mode')
        async with self._lock:
            self._require_open()
            await self._commit(deepcopy(self.devices), {} if mode == 'auto' else deepcopy(self.manual_modes), mode)

    async def save_device(self, identity, record, expected_revision=None):
        clean = self.validate_record(record)
        async with self._lock:
            self._require_open()
            if expected_revision is not None and expected_revision != self.revision:
                raise Conflict('Device settings changed; reopen the form')
            if identity is not None and identity not in self.devices:
                raise ValueError('device_id')
            if any(row['fan_entity'] == clean['fan_entity'] and key != identity for key, row in self.devices.items()):
                raise ValueError('duplicate_output')
            devices, modes = deepcopy(self.devices), deepcopy(self.manual_modes)
            old = devices.get(identity)
            identity = identity or uuid4().hex
            if old and old['fan_entity'] != clean['fan_entity']:
                modes.pop(old['fan_entity'], None)
            devices[identity] = {'device_id': identity, **clean}
            await self._commit(devices, modes)
            return deepcopy(devices[identity])

    async def remove_device(self, identity, expected_revision=None):
        async with self._lock:
            self._require_open()
            if expected_revision is not None and expected_revision != self.revision:
                raise Conflict('Device settings changed; reopen the form')
            if identity not in self.devices:
                raise ValueError('device_id')
            devices, modes = deepcopy(self.devices), deepcopy(self.manual_modes)
            modes.pop(devices.pop(identity)['fan_entity'], None)
            await self._commit(devices, modes)

    @staticmethod
    def valid_device(fan):
        return isinstance(fan, str) and re.fullmatch(r'(?:fan|switch)\.[a-z0-9_]+', fan) is not None

    @staticmethod
    def _valid_pair(fan, temperature, humidity):
        return (Registry.valid_device(fan) and
                all(isinstance(x, str) and re.fullmatch(r'sensor\.[a-z0-9_]+', x) is not None
                    for x in (temperature, humidity)))

    def snapshot(self):
        return {'entry_id': self.entry_id, 'revision': self.revision, 'bindings': deepcopy(self.bindings), 'control_mode': self.control_mode,
                'devices': [{key: row[key] for key in ('device_id', 'name', 'fan_entity', 'temperature_entity', 'humidity_entity')} for row in self.devices.values()]}

    async def bind(self, expected_revision, fan, temperature, humidity, existing):
        row = self.device_for_output(fan)
        if row is None or not self._valid_pair(fan, temperature, humidity) or any(existing.get(entity) is None for entity in (fan, temperature, humidity)):
            raise ValueError('Invalid, unconfigured or missing entity')
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Invalid revision')
        await self.save_device(row['device_id'], {**row, 'temperature_entity': temperature, 'humidity_entity': humidity}, expected_revision)
        return self.snapshot()

    async def set_mode(self, fan, mode):
        """Persist manual hold before any actuation; auto removes the hold."""
        if not self.valid_device(fan) or mode not in ('auto', 'on', 'off'):
            raise ValueError('Invalid fan or mode')
        async with self._lock:
            self._require_open()
            if not self.owned(fan):
                raise ValueError('Output is not configured in this group')
            if mode == 'auto' and self.control_mode == 'manual':
                raise ValueError('全域手動模式：請先將全域控制切換為自動 (global manual)')
            modes = deepcopy(self.manual_modes)
            if mode == 'auto':
                modes.pop(fan, None)
            else:
                modes[fan] = mode
            await self._commit(deepcopy(self.devices), modes)

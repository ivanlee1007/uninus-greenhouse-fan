"""Per-entry, revisioned authoritative sensor binding registry."""
import asyncio
from copy import deepcopy


class Conflict(Exception):
    """Optimistic concurrency revision mismatch."""


class Registry:
    def __init__(self, entry_id, data, save):
        data = data or {}
        revision = data.get('revision', 0)
        bindings = data.get('bindings', {})
        modes = data.get('manual_modes', {})
        if type(revision) is not int or revision < 0 or not isinstance(bindings, dict) or not isinstance(modes, dict):
            raise ValueError('Invalid stored registry')
        for fan, pair in bindings.items():
            if not self._valid_pair(fan, pair.get('temperature_entity') if isinstance(pair, dict) else None, pair.get('humidity_entity') if isinstance(pair, dict) else None):
                raise ValueError('Invalid stored binding')
        if any(fan not in bindings or mode not in ('on', 'off') for fan, mode in modes.items()):
            raise ValueError('Invalid stored manual hold')
        self.entry_id = entry_id
        self.revision = revision
        self.bindings = deepcopy(bindings)
        self.manual_modes = deepcopy(modes)
        self._save = save
        self._lock = asyncio.Lock()

    @staticmethod
    def _valid_pair(fan, temperature, humidity):
        return (isinstance(fan, str) and fan.split('.', 1)[0] in ('fan', 'switch') and
                '.' in fan and bool(fan.split('.', 1)[1]) and
                all(isinstance(x, str) and x.startswith('sensor.') and len(x) > len('sensor.')
                    for x in (temperature, humidity)))

    def snapshot(self):
        return {'entry_id': self.entry_id, 'revision': self.revision, 'bindings': deepcopy(self.bindings)}

    async def bind(self, expected_revision, fan, temperature, humidity, existing):
        if not self._valid_pair(fan, temperature, humidity) or any(entity not in existing for entity in (fan, temperature, humidity)):
            raise ValueError('Invalid or missing entity')
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Invalid revision')
        async with self._lock:
            if expected_revision != self.revision:
                raise Conflict('Stale revision')
            bindings = deepcopy(self.bindings)
            bindings[fan] = {'temperature_entity': temperature, 'humidity_entity': humidity}
            revision = self.revision + 1
            await self._save({'revision': revision, 'bindings': bindings, 'manual_modes': deepcopy(self.manual_modes)})
            self.bindings = bindings
            self.revision = revision
            return self.snapshot()

    async def set_mode(self, fan, mode):
        """Persist manual hold before any actuation; auto removes the hold."""
        if fan not in self.bindings or mode not in ('auto', 'on', 'off'):
            raise ValueError('Invalid fan or mode')
        async with self._lock:
            modes = deepcopy(self.manual_modes)
            if mode == 'auto':
                modes.pop(fan, None)
            else:
                modes[fan] = mode
            revision = self.revision + 1
            await self._save({'revision': revision, 'bindings': deepcopy(self.bindings), 'manual_modes': modes})
            self.manual_modes = modes
            self.revision = revision

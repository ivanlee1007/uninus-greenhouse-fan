"""Pure binding registry tests with an in-memory persistence adapter."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/uninus_greenhouse_fan'
spec = importlib.util.spec_from_file_location('fan_registry', ROOT / 'registry.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Registry = module.Registry
Conflict = module.Conflict


class RegistryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = []
        async def save(data):
            self.saved.append(data)
        self.save = save
        self.entities = dict.fromkeys(('fan.a', 'switch.a', 'sensor.t', 'sensor.h', 'sensor.t2'), object())
        self.registry = Registry('entry-1', {'revision':0, 'bindings':{}, 'manual_modes':{}, 'devices':{fan:{'device_id':fan,'name':fan,'fan_entity':fan,'temperature_entity':'','humidity_entity':''} for fan in ('fan.a','switch.a')}}, self.save)

    async def test_unbound_manual_hold_roundtrip_and_invalid_ids_fail_closed(self):
        for fan in ('fan.a', 'switch.a'):
            await self.registry.set_mode(fan, 'on')
        restored = Registry('entry-1', self.saved[-1], self.save)
        self.assertEqual(restored.manual_modes, {'fan.a':'on', 'switch.a':'on'})
        await restored.set_mode('switch.a', 'auto')
        self.assertEqual(self.saved[-1]['manual_modes'], {'fan.a':'on'})
        for fan in ('sensor.a', 'light.a', 'fan.', 'fan.a.b', 'fan.a b', 'fan.A', 'switch.a\n', 12, None):
            with self.subTest(fan=fan):
                with self.assertRaises(ValueError):
                    Registry('entry-1', {'manual_modes':{fan:'on'}}, self.save)
                with self.assertRaises(ValueError):
                    await restored.set_mode(fan, 'on')
        for mode in ('auto', 'bad', None, True):
            with self.assertRaises(ValueError):
                Registry('entry-1', {'manual_modes':{'fan.a':mode}}, self.save)

    async def test_unbound_failed_save_does_not_commit_hold(self):
        async def fail(data):
            raise OSError('storage offline')
        registry = Registry('entry-1', {'revision':0, 'bindings':{}, 'manual_modes':{}, 'devices':{fan:{'device_id':fan,'name':fan,'fan_entity':fan,'temperature_entity':'','humidity_entity':''} for fan in ('fan.a','switch.a')}}, fail)
        with self.assertRaises(OSError):
            await registry.set_mode('switch.a', 'off')
        self.assertEqual(registry.manual_modes, {})
        self.assertEqual(registry.revision, 0)

    async def test_bind_supports_real_state_machine_get_only_contract(self):
        class GetOnlyStates:
            def get(inner, entity):
                return object() if entity in self.entities else None
        result = await self.registry.bind(0, 'fan.a', 'sensor.t', 'sensor.h', GetOnlyStates())
        self.assertEqual(result['revision'], 1)
        with self.assertRaises(ValueError):
            await self.registry.bind(1, 'fan.a', 'sensor.missing', 'sensor.h', GetOnlyStates())
        self.assertEqual(self.registry.revision, 1)

    async def test_bind_persists_and_revision_increments(self):
        result = await self.registry.bind(0, 'fan.a', 'sensor.t', 'sensor.h', self.entities)
        self.assertEqual(result['revision'], 1)
        self.assertEqual(self.saved[0]['bindings']['fan.a']['temperature_entity'], 'sensor.t')
        self.assertEqual(self.registry.snapshot()['bindings']['fan.a']['humidity_entity'], 'sensor.h')

    async def test_switch_relay_is_a_supported_fan_output(self):
        result = await self.registry.bind(0, 'switch.a', 'sensor.t', 'sensor.h', self.entities)
        self.assertIn('switch.a', result['bindings'])

    async def test_stale_revision_rejects_without_mutation(self):
        await self.registry.bind(0, 'fan.a', 'sensor.t', 'sensor.h', self.entities)
        with self.assertRaises(Conflict):
            await self.registry.bind(0, 'fan.a', 'sensor.t2', 'sensor.h', self.entities)
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.registry.snapshot()['revision'], 1)

    async def test_missing_and_wrong_domain_rejected(self):
        for fan, temp, humidity in [('fan.missing', 'sensor.t', 'sensor.h'), ('sensor.t', 'sensor.t2', 'sensor.h'), ('fan.a', 'fan.a', 'sensor.h'), ('fan.a', 'sensor.t', 'sensor.no')]:
            with self.assertRaises(ValueError):
                await self.registry.bind(0, fan, temp, humidity, self.entities)
        self.assertEqual(self.saved, [])

    async def test_failed_persistence_does_not_commit(self):
        async def fail(data):
            raise OSError('storage offline')
        registry = Registry('entry-1', {'revision':0, 'bindings':{}, 'manual_modes':{}, 'devices':{fan:{'device_id':fan,'name':fan,'fan_entity':fan,'temperature_entity':'','humidity_entity':''} for fan in ('fan.a','switch.a')}}, fail)
        with self.assertRaises(OSError):
            await registry.bind(0, 'fan.a', 'sensor.t', 'sensor.h', self.entities)
        self.assertEqual(registry.snapshot()['revision'], 0)
        self.assertEqual(registry.snapshot()['bindings'], {})

    async def test_reload_invalid_data_fails_closed(self):
        registry = Registry('entry-1', {'revision': 3, 'bindings': {'fan.a': {'temperature_entity': 'sensor.t', 'humidity_entity': 'sensor.h'}}}, self.save)
        self.assertEqual(registry.snapshot()['revision'], 3)
        with self.assertRaises(ValueError):
            Registry('entry-1', {'revision': 'bad', 'bindings': {}}, self.save)

    async def test_concurrent_writers_only_one_wins(self):
        import asyncio
        outcomes = await asyncio.gather(
            self.registry.bind(0, 'fan.a', 'sensor.t', 'sensor.h', self.entities),
            self.registry.bind(0, 'fan.a', 'sensor.t2', 'sensor.h', self.entities),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(v, Conflict) for v in outcomes), 1)
        self.assertEqual(len(self.saved), 1)

    async def test_manual_hold_is_durable_and_failed_save_does_not_resume_auto(self):
        await self.registry.bind(0, 'fan.a', 'sensor.t', 'sensor.h', self.entities)
        await self.registry.set_mode('fan.a', 'on')
        self.assertEqual(self.saved[-1]['manual_modes'], {'fan.a': 'on'})
        reloaded = Registry('entry-1', self.saved[-1], self.save)
        self.assertEqual(reloaded.manual_modes['fan.a'], 'on')
        async def fail(_data):
            raise OSError('disk failure')
        reloaded._save = fail
        with self.assertRaises(OSError):
            await reloaded.set_mode('fan.a', 'auto')
        self.assertEqual(reloaded.manual_modes['fan.a'], 'on')
        reloaded._save = self.save
        await reloaded.set_mode('fan.a', 'auto')
        self.assertEqual(self.saved[-1]['manual_modes'], {})


if __name__ == '__main__':
    unittest.main()

"""Configured inventory, legacy migration and transactional persistence."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('inventory_registry', Path(__file__).resolve().parents[1] / 'custom_components/uninus_greenhouse_fan/registry.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Registry = module.Registry

class DevicesTest(unittest.IsolatedAsyncioTestCase):
    async def test_atomic_device_record_and_stable_identity(self):
        saved = []
        async def save(data): saved.append(data)
        registry = Registry('group', {}, save)
        device = await registry.save_device(None, {'name':'North', 'fan_entity':'switch.north', 'temperature_entity':'', 'humidity_entity':''})
        self.assertTrue(device['device_id'])
        self.assertEqual(registry.bindings, {})
        await registry.set_mode('switch.north', 'on')
        changed = await registry.save_device(device['device_id'], {**device, 'name':'Renamed', 'fan_entity':'fan.north'})
        self.assertEqual(changed['device_id'], device['device_id'])
        self.assertEqual(registry.manual_modes, {})
        self.assertEqual(saved[-1]['devices'], registry.devices)
        restored = Registry('group', saved[-1], save)
        self.assertEqual(restored.devices, registry.devices)
        await restored.remove_device(device['device_id'])
        self.assertEqual(restored.devices, {})
        self.assertEqual(restored.manual_modes, {})

    async def test_migration_is_idempotent_preserves_pair_and_manual_only_hold(self):
        async def save(data): pass
        old = {'bindings':{'fan.a':{'temperature_entity':'sensor.t','humidity_entity':'sensor.h'}}, 'manual_modes':{'fan.a':'off','switch.b':'on'}}
        registry = Registry('group', old, save)
        self.assertEqual(len(registry.devices), 2)
        self.assertEqual(registry.bindings, old['bindings'])
        self.assertEqual(registry.manual_modes, old['manual_modes'])
        again = Registry('group', registry.payload(), save)
        self.assertEqual(again.devices, registry.devices)
        self.assertEqual(again.manual_modes, registry.manual_modes)
        self.assertEqual(Registry('group', old, save).devices, registry.devices)

    async def test_validation_and_storage_failure_never_commit(self):
        async def save(data): pass
        registry = Registry('group', {}, save)
        device = await registry.save_device(None, {'name':'A','fan_entity':'fan.a'})
        for record in ({'name':'','fan_entity':'fan.b'}, {'name':'B','fan_entity':'fan.a'}, {'name':'B','fan_entity':'fan.b','temperature_entity':'sensor.t'}):
            with self.assertRaises(ValueError): await registry.save_device(None, record)
        before = registry.payload()
        async def fail(data): raise OSError('disk')
        registry._save = fail
        with self.assertRaises(OSError): await registry.save_device(device['device_id'], {**device,'name':'Changed'})
        with self.assertRaises(OSError): await registry.remove_device(device['device_id'])
        self.assertEqual(registry.payload(), before)
        with self.assertRaises(ValueError): await registry.set_mode('switch.unowned','on')
        with self.assertRaises(ValueError): await registry.bind(registry.revision,'fan.unowned','sensor.t','sensor.h',{})

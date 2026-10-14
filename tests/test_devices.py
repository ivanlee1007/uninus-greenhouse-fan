"""Configured inventory, legacy migration and transactional persistence."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('inventory_registry', Path(__file__).resolve().parents[1] / 'custom_components/uninus_greenhouse_fan/registry.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Registry = module.Registry

class DevicesTest(unittest.IsolatedAsyncioTestCase):
    async def test_existing_inventory_without_control_flag_is_migrated_without_identity_changes(self):
        async def save(data): pass
        registry=Registry('group',{},save)
        row=await registry.save_device(None,{'name':'A','fan_entity':'fan.a'})
        old=registry.payload();old.pop('control_mode')
        migrated=Registry('group',old,save)
        self.assertTrue(migrated.migrated)
        self.assertEqual(migrated.devices,registry.devices)
        self.assertEqual(migrated.control_mode,'auto')
        for flag in (None,True,False,0,1,'AUTO','on',[],{}):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                Registry('group',{**old,'control_mode':flag},save)


    async def test_global_control_mode_atomic_roundtrip_and_gate(self):
        saved=[]
        async def save(data): saved.append(data)
        registry=Registry('group', {}, save)
        for fan in ('fan.a','switch.hidden'):
            await registry.save_device(None, {'name':fan,'fan_entity':fan})
        await registry.set_mode('fan.a','on')
        before=len(saved)
        await registry.set_control_mode('manual')
        self.assertEqual(len(saved),before+1)
        self.assertEqual(registry.snapshot()['control_mode'],'manual')
        restored=Registry('group',saved[-1],save)
        self.assertEqual(restored.control_mode,'manual')
        await restored.save_device(None,{'name':'new','fan_entity':'fan.new'})
        self.assertEqual(saved[-1]['control_mode'],'manual')
        with self.assertRaisesRegex(ValueError,'global|全域'):
            await restored.set_mode('fan.a','auto')
        await restored.set_mode('fan.a','off')
        await restored.set_control_mode('auto')
        self.assertEqual(restored.manual_modes,{})
        self.assertEqual(saved[-1]['control_mode'],'auto')

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

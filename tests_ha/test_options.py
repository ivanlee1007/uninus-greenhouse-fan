"""Native HA forms/selectors, isolated from tests' fake sys.modules."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.selector import EntitySelector
from custom_components.uninus_greenhouse_fan import FanGroup
from custom_components.uninus_greenhouse_fan.registry import Registry
from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanOptionsFlow
from custom_components.uninus_greenhouse_fan.const import DOMAIN

class OptionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.hass = HomeAssistant(self.directory.name)
        self.entry = ConfigEntry(domain=DOMAIN, title='North', data={}, options={}, source='user', version=1, minor_version=1, unique_id=None, discovery_keys={}, subentries_data=[])
        self.hass.config_entries = types.SimpleNamespace(async_entries=lambda domain: [self.entry])
        self.saved = []
        async def save(data): self.saved.append(data)
        self.group = FanGroup(self.hass, self.entry, Registry(self.entry.entry_id, {}, save))
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.group}
        self.hass.states.async_set('fan.a', 'off')
        self.hass.states.async_set('switch.b', 'off')
        self.hass.states.async_set('sensor.t', '30', {'device_class':'temperature','unit_of_measurement':'°C'})
        self.hass.states.async_set('sensor.h', '60', {'device_class':'humidity','unit_of_measurement':'%'})
        self.record = {'name':'North fan','fan_entity':'fan.a','temperature_entity':'sensor.t','humidity_entity':'sensor.h'}

    async def asyncTearDown(self):
        await self.hass.async_stop()
        self.directory.cleanup()

    def flow(self):
        flow = GreenhouseFanOptionsFlow(self.entry)
        flow.hass = self.hass
        return flow

    async def test_exact_p130_manual_ignores_sensor_health_but_rejects_invalid_outputs(self):
        target = 'switch.uss_p130_f5_relay0'
        self.hass.states.async_set(target, 'off')
        device = await self.group.save_device(None, {**self.record, 'fan_entity':target})
        calls = []
        async def service(call):
            calls.append((call.domain, call.service, dict(call.data)))
        self.hass.services.async_register('switch', 'turn_on', service)
        self.hass.services.async_register('switch', 'turn_off', service)
        for output in ('on', 'off'):
            for health in ('absent', 'healthy', 'unavailable', 'missing'):
                self.hass.states.async_set('sensor.t', '30', {'device_class':'temperature','unit_of_measurement':'°C'})
                record = {**self.record, 'fan_entity':target}
                if health == 'absent':
                    record.update(temperature_entity='', humidity_entity='')
                await self.group.save_device(device['device_id'], record)
                if health == 'unavailable':
                    self.hass.states.async_set('sensor.t', 'unavailable')
                elif health == 'missing':
                    self.hass.states.async_remove('sensor.t')
                self.hass.states.async_set(target, output)
                for mode in ('on', 'off'):
                    result = await self.group.manual(target, mode)
                    self.assertEqual(result['runtime'][target]['mode'], mode)
                    self.assertEqual(calls[-1], ('switch', 'turn_'+mode, {'entity_id':target}))
                before = len(calls)
                await self.group.manual(target, 'auto')
                self.assertEqual(len(calls), before)
        before = len(calls)
        for value in ('unknown', 'unavailable', None):
            if value is None:
                self.hass.states.async_remove(target)
            else:
                self.hass.states.async_set(target, value)
            for mode in ('on', 'off'):
                with self.assertRaises(ValueError):
                    await self.group.manual(target, mode)
        self.hass.states.async_set('switch.unowned', 'on')
        with self.assertRaises(ValueError):
            await self.group.manual('switch.unowned', 'off')
        self.group.active = False
        with self.assertRaises(ValueError):
            await self.group.manual(target, 'on')
        self.assertEqual(len(calls), before)

    async def test_menu_device_save_reopen_cancel_and_native_selectors(self):
        flow = self.flow()
        menu = await flow.async_step_init()
        self.assertEqual(menu['type'], 'menu')
        self.assertIn('policy', menu['menu_options'])
        form = await flow.async_step_add_device()
        self.assertEqual(form['step_id'], 'device')
        selectors = {key.schema: value for key, value in form['data_schema'].schema.items()}
        self.assertIsInstance(selectors['fan_entity'], EntitySelector)
        self.assertIsInstance(selectors['temperature_entity'], EntitySelector)
        self.assertEqual(self.saved, [])  # Cancel/closing form does not write.
        result = await flow.async_step_device(self.record)
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(len(self.saved), 1)
        device = next(iter(self.group.registry.devices.values()))
        reopened = self.flow()
        await reopened.async_step_edit_device({'device':device['device_id']})
        form = await reopened.async_step_device()
        self.assertEqual(form['data_schema']({})['name'], 'North fan')
        self.assertEqual(len(self.saved), 1)

    async def test_field_errors_preserve_input_and_pair_clear_manual_only(self):
        flow = self.flow()
        await flow.async_step_add_device()
        record = {**self.record, 'humidity_entity':''}
        result = await flow.async_step_device(record)
        self.assertIn('humidity_entity', result['errors'])
        self.assertEqual(result['data_schema']({})['name'], record['name'])
        self.assertEqual(self.saved, [])
        result = await flow.async_step_device({**record,'temperature_entity':''})
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(self.group.registry.bindings, {})
        self.assertEqual(len(self.group.registry.devices), 1)

    async def test_update_duplicate_output_delete_confirm_and_no_actuation(self):
        flow = self.flow(); await flow.async_step_add_device(); await flow.async_step_device(self.record)
        device = next(iter(self.group.registry.devices.values()))
        duplicate = self.flow(); await duplicate.async_step_add_device()
        self.assertIn('fan_entity', (await duplicate.async_step_device(self.record))['errors'])
        edit = self.flow(); await edit.async_step_edit_device({'device':device['device_id']})
        await edit.async_step_device({**self.record,'fan_entity':'switch.b','name':'Updated'})
        self.assertEqual(next(iter(self.group.registry.devices)), device['device_id'])
        remove = self.flow(); await remove.async_step_remove_device({'device':device['device_id']})
        await remove.async_step_confirm_remove({'confirm':False})
        self.assertEqual(len(self.group.registry.devices), 1)
        remove = self.flow(); await remove.async_step_remove_device({'device':device['device_id']})
        await remove.async_step_confirm_remove({'confirm':True})
        self.assertEqual(self.group.registry.devices, {})

    async def test_user_policy_validation_and_shared_policy_reopen(self):
        from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanConfigFlow
        from custom_components.uninus_greenhouse_fan.const import DEFAULT_POLICY
        setup = GreenhouseFanConfigFlow(); setup.hass = self.hass
        self.assertEqual((await setup.async_step_user())['step_id'], 'user')
        invalid = await setup.async_step_user({'name':'North', **DEFAULT_POLICY, 'duration_seconds':-1})
        self.assertEqual(invalid['errors']['base'], 'invalid_policy')
        created = await setup.async_step_user({'name':'North', **DEFAULT_POLICY})
        self.assertEqual(created['title'], 'North')
        policy = await self.flow().async_step_policy({**DEFAULT_POLICY,'temperature_on':35})
        self.assertEqual(policy['data']['temperature_on'],35)
        self.assertEqual(self.saved, [])

    async def test_pair_cleared_through_native_schema_and_bad_entity_field_errors(self):
        flow = self.flow(); await flow.async_step_add_device(); await flow.async_step_device(self.record)
        device = next(iter(self.group.registry.devices.values()))
        edit = self.flow(); await edit.async_step_edit_device({'device':device['device_id']})
        form = await edit.async_step_device()
        submission = form['data_schema']({'name':'Manual only','fan_entity':'fan.a'})
        self.assertNotIn('temperature_entity', submission)
        await edit.async_step_device(submission)
        self.assertEqual(self.group.registry.bindings,{})
        for field, value in [('name',''),('fan_entity','light.invalid'),('temperature_entity','sensor.missing')]:
            flow = self.flow(); await flow.async_step_add_device()
            result = await flow.async_step_device({**self.record,field:value})
            self.assertIn(field,result['errors'])

    async def test_source_reset_preserves_hold_replacement_drops_hold_and_removal_is_passive(self):
        await self.group.save_device(None,self.record)
        old = next(iter(self.group.registry.devices.values()))
        await self.group.registry.set_mode('fan.a','off')
        self.group.controller.set_mode('fan.a','off')
        await self.group.save_device(old['device_id'],{**self.record,'temperature_entity':'','humidity_entity':''})
        self.assertEqual(self.group.registry.manual_modes,{'fan.a':'off'})
        self.assertEqual(self.group.controller.status('fan.a')['mode'],'off')
        await self.group.save_device(old['device_id'],{**self.record,'fan_entity':'switch.b'})
        self.assertEqual(self.group.registry.manual_modes,{})
        self.assertNotIn('fan.a',self.group.controller._states)
        self.assertEqual(self.group.controller.status('switch.b')['mode'],'auto')
        self.assertIsNone(self.group.controller.status('switch.b')['pending'])
        await self.group.remove_device(old['device_id'])
        self.assertEqual(self.group.registry.bindings,{})
        self.assertNotIn('switch.b',self.group.controller._states)
        self.assertEqual(self.hass.states.get('fan.a').state,'off')
        self.assertEqual(self.hass.states.get('switch.b').state,'off')

    async def test_conflict_does_not_advance_original_form_revision(self):
        flow = self.flow(); await flow.async_step_add_device()
        await self.group.save_device(None,{'name':'Other','fan_entity':'switch.b'})
        before = self.group.registry.payload()
        result = await flow.async_step_device(self.record)
        self.assertEqual(result['errors']['base'],'conflict')
        self.assertEqual(self.group.registry.payload(),before)
        self.assertEqual(flow._revision,0)

    async def test_cross_group_duplicate_and_unloaded_conservative_rejection(self):
        other = ConfigEntry(domain=DOMAIN,title='South',data={},options={},source='user',version=1,minor_version=1,unique_id=None,discovery_keys={},subentries_data=[])
        async def save(data): pass
        second = FanGroup(self.hass,other,Registry(other.entry_id,{},save))
        self.hass.config_entries.async_entries = lambda domain: [self.entry,other]
        self.hass.data[DOMAIN][other.entry_id] = second
        await second.save_device(None,self.record)
        flow=self.flow();await flow.async_step_add_device()
        self.assertEqual((await flow.async_step_device(self.record))['errors']['fan_entity'],'duplicate_output')
        self.hass.data[DOMAIN].pop(other.entry_id)
        result = await flow.async_step_device({**self.record,'fan_entity':'switch.b'})
        self.assertIn('base',result['errors'])
        with self.assertRaises(ValueError): await self.group.manual('fan.a','on')

    async def test_reload_waits_for_replacement_before_journal_exists(self):
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
        from homeassistant.helpers.storage import Store
        from unittest.mock import AsyncMock
        import json
        import threading
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            old = self.hass.data[DOMAIN][self.entry.entry_id]
            device = await old.save_device(None, self.record)
            entered, release = asyncio.Event(), threading.Event()
            prepare = VerifiedStore._prepare
            def paused(storage):
                self.hass.loop.call_soon_threadsafe(entered.set)
                if not release.wait(10): raise OSError('test release timeout')
                return prepare(storage)
            calls = []
            async def service(call): calls.append(dict(call.data))
            for domain in ('fan', 'switch'):
                self.hass.services.async_register(domain, 'turn_on', service)
            with patch.object(VerifiedStore, '_prepare', paused):
                mutation = asyncio.create_task(old.save_device(device['device_id'], {**self.record, 'fan_entity':'switch.b'}))
                unload = setup = None
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
                    self.assertFalse(Path(str(path) + '.pending').exists())
                    unload = asyncio.create_task(async_unload_entry(self.hass, self.entry))
                    for _ in range(5): await asyncio.sleep(0)
                    setup = asyncio.create_task(async_setup_entry(self.hass, self.entry))
                    for _ in range(10): await asyncio.sleep(0)
                    self.assertFalse(old.active)
                    self.assertFalse(unload.done(), 'Unload must drain the pre-journal transaction')
                    self.assertFalse(setup.done(), 'Setup must wait for the old mutation')
                finally:
                    release.set()
                    await mutation
                    if unload: await unload
                    if setup: await setup
            active = self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertIsNot(active, old)
            self.assertEqual(json.loads(path.read_bytes())['data'], active.registry.payload())
            self.assertEqual(active.registry.devices[device['device_id']]['fan_entity'], 'switch.b')
            self.hass.states.async_set('sensor.t', '40', {'device_class':'temperature','unit_of_measurement':'°C'})
            with patch('custom_components.uninus_greenhouse_fan.monotonic', return_value=100): await active.evaluate_all()
            with patch('custom_components.uninus_greenhouse_fan.monotonic', return_value=1000): await active.evaluate_all()
            self.assertEqual(calls, [{'entity_id':'switch.b'}])
            await async_unload_entry(self.hass, self.entry)

    async def test_cancelled_unload_drains_direct_registry_write_and_rejects_queued_mutations(self):
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
        from homeassistant.helpers.storage import Store
        from unittest.mock import AsyncMock
        import threading
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            old = self.hass.data[DOMAIN][self.entry.entry_id]
            device = await old.save_device(None, self.record)
            entered, release = asyncio.Event(), threading.Event()
            prepare = VerifiedStore._prepare
            def paused(storage):
                self.hass.loop.call_soon_threadsafe(entered.set)
                if not release.wait(10): raise OSError('test release timeout')
                return prepare(storage)
            with patch.object(VerifiedStore, '_prepare', paused):
                mutation = asyncio.create_task(old.registry.set_mode('fan.a', 'off'))
                queued = [asyncio.create_task(old.registry.set_mode('fan.a', 'on')),
                          asyncio.create_task(old.registry.save_device(device['device_id'], {**self.record, 'fan_entity':'switch.b'})),
                          asyncio.create_task(old.registry.remove_device(device['device_id']))]
                unload = setup = None
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    unload = asyncio.create_task(async_unload_entry(self.hass, self.entry))
                    for _ in range(5): await asyncio.sleep(0)
                    self.assertFalse(old.active)
                    queued.extend(asyncio.create_task(operation) for operation in (
                        old.manual('fan.a', 'on'), old.remove_device(device['device_id']),
                        old.save_device(device['device_id'], self.record),
                        old.bind(old.registry.revision, 'fan.a', 'sensor.t', 'sensor.h')))
                    unload.cancel()
                    for _ in range(5): await asyncio.sleep(0)
                    unload.cancel()
                    setup = asyncio.create_task(async_setup_entry(self.hass, self.entry))
                    for _ in range(10): await asyncio.sleep(0)
                    self.assertFalse(unload.done())
                    self.assertFalse(setup.done())
                    self.assertIs(self.hass.data[DOMAIN][self.entry.entry_id], old)
                finally:
                    release.set()
                    await mutation
                    results = await asyncio.gather(*queued, return_exceptions=True)
                    if unload:
                        with self.assertRaises(asyncio.CancelledError): await unload
                    if setup: await setup
            self.assertTrue(all(isinstance(result, ValueError) for result in results), results)
            active = self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(active.registry.manual_modes, {'fan.a':'off'})
            self.assertEqual(active.registry.revision, 2)
            self.assertEqual(await Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').async_load(), active.registry.payload())
            await async_unload_entry(self.hass, self.entry)

    async def test_real_store_migration_read_back_reload(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        store = Store(self.hass,1,f'{DOMAIN}.{self.entry.entry_id}')
        legacy={'revision':3,'bindings':{'fan.a':{'temperature_entity':'sensor.t','humidity_entity':'sensor.h'}},'manual_modes':{'switch.b':'off'}}
        await store.async_save(legacy)
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            await async_setup_entry(self.hass,self.entry)
            group=self.hass.data[DOMAIN][self.entry.entry_id]
            first=group.registry.payload()
            self.assertEqual(len(first['devices']),2)
            self.assertEqual(first['bindings'],legacy['bindings'])
            self.assertEqual(first['manual_modes'],legacy['manual_modes'])
            self.assertEqual((await Store(self.hass,1,f'{DOMAIN}.{self.entry.entry_id}').async_load()),first)
            await async_unload_entry(self.hass,self.entry)
            await async_setup_entry(self.hass,self.entry)
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.payload(),first)
            await async_unload_entry(self.hass,self.entry)

    async def test_real_atomic_writer_interrupted_before_replace_preserves_held_inventory(self):
        from atomicwrites import AtomicWriter
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            device = await group.save_device(None, self.record)
            await group.registry.set_mode('fan.a', 'off')
            before = group.registry.payload()
            path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
            durable = path.read_bytes()
            commit = AtomicWriter.commit
            reached = []
            def interrupted(writer, temporary):
                if Path(writer._path) == path:
                    reached.append(Path(temporary.name).read_bytes())
                    raise OSError('interrupted before atomic replacement')
                return commit(writer, temporary)
            with patch.object(AtomicWriter, 'commit', interrupted):
                with self.assertRaises(OSError):
                    await group.save_device(device['device_id'], {**self.record, 'fan_entity':'switch.b'})
            self.assertTrue(reached, 'Real HA atomic writer boundary was not exercised')
            self.assertEqual(path.read_bytes(), durable)
            self.assertEqual(group.registry.payload(), before)
            await async_unload_entry(self.hass, self.entry)
            await async_setup_entry(self.hass, self.entry)
            restored = self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(restored.registry.payload(), before)
            self.assertEqual(restored.controller.status('fan.a')['mode'], 'off')
            await async_unload_entry(self.hass, self.entry)

    async def test_real_store_transient_readback_error_reconciles_success(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
            read = Path.read_text
            failures = []
            def transient(target, *args, **kwargs):
                if target == path and not failures:
                    failures.append(True)
                    raise OSError('transient readback failure after successful write')
                return read(target, *args, **kwargs)
            with patch.object(Path, 'read_text', transient):
                device = await group.save_device(None, self.record)
            self.assertEqual(len(failures), 1)
            self.assertEqual(group.registry.devices[device['device_id']], device)
            before = group.registry.payload()
            await async_unload_entry(self.hass, self.entry)
            await async_setup_entry(self.hass, self.entry)
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.payload(), before)
            await async_unload_entry(self.hass, self.entry)

    async def test_persistent_readback_failure_quarantines_group_across_restart(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            device = await group.save_device(None, self.record)
            await group.registry.set_mode('fan.a', 'off')
            before = group.registry.payload()
            path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
            read = Path.read_text
            def unreadable(target, *args, **kwargs):
                if target == path:
                    raise OSError('persistent readback unavailable')
                return read(target, *args, **kwargs)
            flow = self.flow(); await flow.async_step_edit_device({'device':device['device_id']})
            with patch.object(Path, 'read_text', unreadable):
                result = await flow.async_step_device({**self.record, 'fan_entity':'switch.b'})
            self.assertEqual(result['errors']['base'], 'storage_quarantined')
            self.assertFalse(group.active)
            self.assertEqual(group.registry.payload(), before)
            self.assertTrue(Path(str(path) + '.pending').exists())
            with patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as call:
                await group.evaluate_all()
                with self.assertRaises(ValueError): await group.manual('fan.a', 'on')
                call.assert_not_awaited()
            await async_unload_entry(self.hass, self.entry)
            with self.assertRaisesRegex(OSError, 'quarantin'):
                await async_setup_entry(self.hass, self.entry)
            self.assertNotIn(self.entry.entry_id, self.hass.data[DOMAIN])

    async def test_failed_readback_verified_rollback_preserves_replacement_hold(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            device = await group.save_device(None, self.record)
            await group.registry.set_mode('fan.a', 'off')
            group.controller.set_mode('fan.a', 'off')
            before = group.registry.payload()
            path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
            read = Path.read_text
            failed = []
            def fail_three(target, *args, **kwargs):
                if target == path and len(failed) < 3:
                    failed.append(True)
                    raise OSError('readback temporarily unavailable')
                return read(target, *args, **kwargs)
            with patch.object(Path, 'read_text', fail_three):
                with self.assertRaisesRegex(OSError, 'restored and verified'):
                    await group.save_device(device['device_id'], {**self.record, 'fan_entity':'switch.b'})
            self.assertEqual(group.registry.payload(), before)
            self.assertEqual(group.controller.status('fan.a')['mode'], 'off')
            self.assertTrue(group.active)
            self.assertEqual(await Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').async_load(), before)
            self.assertFalse(Path(str(path) + '.pending').exists())
            await async_unload_entry(self.hass, self.entry)
            await async_setup_entry(self.hass, self.entry)
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.payload(), before)
            await async_unload_entry(self.hass, self.entry)

    async def test_cancel_during_underlying_store_write_drains_then_restores_no_actuation(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        import threading
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            await group.save_device(None, self.record)
            await group.registry.set_mode('fan.a', 'off')
            group.controller.set_mode('fan.a', 'off')
            before = group.registry.payload()
            entered, release = asyncio.Event(), threading.Event()
            writer = Store._write_prepared_data
            def paused(store, *args):
                self.hass.loop.call_soon_threadsafe(entered.set)
                if not release.wait(5): raise OSError('test release timeout')
                return writer(store, *args)
            with patch.object(Store, '_write_prepared_data', paused), patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as call:
                operation = asyncio.create_task(group.manual('fan.a', 'on'))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    operation.cancel()
                    await asyncio.sleep(0)
                    operation.cancel()  # Repeated cancellation cannot release the locks early.
                finally:
                    release.set()
                with self.assertRaises(asyncio.CancelledError): await operation
                call.assert_not_awaited()
            self.assertEqual(group.registry.payload(), before)
            self.assertEqual(group.controller.status('fan.a')['mode'], 'off')
            self.assertEqual(await Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').async_load(), before)
            await async_unload_entry(self.hass, self.entry)
            await async_setup_entry(self.hass, self.entry)
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.payload(), before)
            await async_unload_entry(self.hass, self.entry)

    async def test_unload_during_real_store_write_preserves_hold_without_dispatch(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            await group.save_device(None, self.record)
            entered, release = asyncio.Event(), asyncio.Event()
            save = Store.async_save
            async def paused(store, payload):
                entered.set(); await release.wait()
                await save(store, payload)
            with patch.object(Store, 'async_save', paused), patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as call:
                operation = asyncio.create_task(group.manual('fan.a', 'off'))
                await asyncio.wait_for(entered.wait(), 5)
                unload = asyncio.create_task(async_unload_entry(self.hass, self.entry))
                await asyncio.sleep(0)
                self.assertFalse(group.active)
                self.assertFalse(unload.done())
                release.set()
                await unload
                with self.assertRaisesRegex(ValueError, 'unloaded'): await operation
                call.assert_not_awaited()
            await async_setup_entry(self.hass, self.entry)
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.manual_modes, {'fan.a':'off'})
            await async_unload_entry(self.hass, self.entry)

    async def test_real_store_rejected_and_aborted_native_forms_have_no_writes_or_actuation(self):
        from homeassistant.config_entries import ConfigEntries
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanConfigFlow
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        manager = ConfigEntries(self.hass, {})
        manager._entries[self.entry.entry_id] = self.entry
        self.hass.config_entries = manager
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            before = self.hass.data[DOMAIN][self.entry.entry_id].registry.payload()
            with patch('homeassistant.config_entries._async_get_flow_handler', new=AsyncMock(return_value=GreenhouseFanConfigFlow)), patch.object(Store, 'async_save', new=AsyncMock()) as save, patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as call:
                result = await manager.options.async_init(self.entry.entry_id)
                result = await manager.options.async_configure(result['flow_id'], {'next_step_id':'add_device'})
                result = await manager.options.async_configure(result['flow_id'], {key:value for key,value in self.record.items() if key != 'humidity_entity'})
                self.assertIn('humidity_entity', result['errors'])
                manager.options.async_abort(result['flow_id'])
                save.assert_not_awaited(); call.assert_not_awaited()
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.payload(), before)
            await async_unload_entry(self.hass, self.entry)

    async def test_failed_rollback_leaves_new_disk_record_quarantined_on_fresh_ha_restart(self):
        import json
        from homeassistant.helpers.storage import Store
        from homeassistant.util.file import write_utf8_file_atomic
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            device = await group.save_device(None, self.record)
            await group.registry.set_mode('fan.a', 'off')
            before = group.registry.payload()
            path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
            read, attempts = Path.read_text, []
            def fail_three(target, *args, **kwargs):
                if target == path and len(attempts) < 3:
                    attempts.append(True); raise OSError('readback failed')
                return read(target, *args, **kwargs)
            def fail_restore(filename, *args, **kwargs):
                if Path(filename) == path: raise OSError('rollback writer unavailable')
                return write_utf8_file_atomic(filename, *args, **kwargs)
            with patch.object(Path, 'read_text', fail_three), patch('homeassistant.util.file.write_utf8_file_atomic', fail_restore):
                with self.assertRaisesRegex(OSError, 'quarantined'):
                    await group.save_device(device['device_id'], {**self.record, 'fan_entity':'switch.b'})
            self.assertFalse(group.active)
            self.assertEqual(group.registry.payload(), before)
            indeterminate = json.loads(path.read_bytes())['data']
            self.assertEqual(indeterminate['devices'][device['device_id']]['fan_entity'], 'switch.b')
            self.assertEqual(indeterminate['manual_modes'], {})
            await async_unload_entry(self.hass, self.entry)
            fresh = HomeAssistant(self.directory.name)
            fresh.config_entries = types.SimpleNamespace(async_entries=lambda domain: [self.entry])
            try:
                with self.assertRaisesRegex(OSError, 'quarantined'):
                    await async_setup_entry(fresh, self.entry)
                self.assertNotIn(self.entry.entry_id, fresh.data[DOMAIN])
                pending = Path(str(path) + '.pending')
                previous = json.loads(pending.read_text())['previous']
                self.assertEqual(previous['data'], before)
                # Exercise documented explicit recovery; never adopt the new target.
                await fresh.async_add_executor_job(write_utf8_file_atomic, str(path), json.dumps(previous))
                self.assertEqual(json.loads(path.read_bytes()), previous)
                pending.unlink()
                await async_setup_entry(fresh, self.entry)
                restored = fresh.data[DOMAIN][self.entry.entry_id]
                self.assertEqual(restored.registry.payload(), before)
                self.assertEqual(restored.controller.status('fan.a')['mode'], 'off')
                await async_unload_entry(fresh, self.entry)
            finally:
                await fresh.async_stop()

    async def test_shutdown_during_underlying_write_never_dispatches_or_defers_late_write(self):
        from homeassistant.core import CoreState
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        import threading
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            await group.save_device(None, self.record)
            entered, release = asyncio.Event(), threading.Event()
            writer, stores = Store._write_prepared_data, []
            def paused(store, *args):
                stores.append(store)
                self.hass.loop.call_soon_threadsafe(entered.set)
                if not release.wait(5): raise OSError('test release timeout')
                return writer(store, *args)
            with patch.object(Store, '_write_prepared_data', paused), patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as call:
                operation = asyncio.create_task(group.manual('fan.a', 'off'))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    self.hass.state = CoreState.stopping
                finally:
                    release.set()
                with self.assertRaisesRegex(OSError, 'stopping'): await operation
                call.assert_not_awaited()
                self.assertTrue(all(store._data is None and store._unsub_final_write_listener is None for store in stores))
            self.hass.state = CoreState.not_running
            await async_unload_entry(self.hass, self.entry)
            await async_setup_entry(self.hass, self.entry)
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.manual_modes, {'fan.a':'off'})
            await async_unload_entry(self.hass, self.entry)

    async def test_journal_release_failure_keeps_new_record_quarantined(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            before = group.registry.payload()
            path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
            pending = Path(str(path) + '.pending')
            unlink = Path.unlink
            def fail_release(target, *args, **kwargs):
                if target == pending: raise OSError('journal release failed')
                return unlink(target, *args, **kwargs)
            with patch.object(Path, 'unlink', fail_release):
                with self.assertRaisesRegex(OSError, 'quarantined'): await group.save_device(None, self.record)
            self.assertFalse(group.active)
            self.assertEqual(group.registry.payload(), before)
            self.assertTrue(pending.exists())
            await async_unload_entry(self.hass, self.entry)
            with self.assertRaisesRegex(OSError, 'quarantined'): await async_setup_entry(self.hass, self.entry)

    async def test_journal_prepare_failure_does_not_call_store_or_actuate(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            before = group.registry.payload()
            with patch('homeassistant.util.file.write_utf8_file_atomic', side_effect=OSError('journal disk unavailable')), patch.object(Store, 'async_save', new=AsyncMock()) as save, patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as call:
                with self.assertRaisesRegex(OSError, 'quarantined'): await group.save_device(None, self.record)
                save.assert_not_awaited(); call.assert_not_awaited()
            self.assertEqual(group.registry.payload(), before)
            self.assertFalse(group.active)
            await async_unload_entry(self.hass, self.entry)
            # No candidate was attempted; with no journal and unchanged bytes,
            # a later reload is safe once storage is usable again.
            await async_setup_entry(self.hass, self.entry)
            self.assertEqual(self.hass.data[DOMAIN][self.entry.entry_id].registry.payload(), before)
            await async_unload_entry(self.hass, self.entry)

    async def test_cancel_with_failed_rollback_leaves_durable_fault_and_no_actuation(self):
        from homeassistant.helpers.storage import Store
        from homeassistant.util.file import write_utf8_file_atomic
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            group = self.hass.data[DOMAIN][self.entry.entry_id]
            await group.save_device(None, self.record)
            before = group.registry.payload()
            entered, release = asyncio.Event(), asyncio.Event()
            path = Path(Store(self.hass, 1, f'{DOMAIN}.{self.entry.entry_id}').path)
            save = Store.async_save
            async def paused(store, payload):
                await save(store, payload)
                entered.set(); await release.wait()
            def fail_restore(filename, *args, **kwargs):
                if Path(filename) == path: raise OSError('cancellation rollback failed')
                return write_utf8_file_atomic(filename, *args, **kwargs)
            with patch.object(Store, 'async_save', paused), patch('homeassistant.util.file.write_utf8_file_atomic', fail_restore), patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as call:
                operation = asyncio.create_task(group.manual('fan.a', 'on'))
                await asyncio.wait_for(entered.wait(), 5)
                operation.cancel(); release.set()
                with self.assertRaises(asyncio.CancelledError): await operation
                call.assert_not_awaited()
            self.assertFalse(group.active)
            self.assertEqual(group.registry.payload(), before)
            self.assertTrue(Path(str(path) + '.pending').exists())
            await async_unload_entry(self.hass, self.entry)
            with self.assertRaisesRegex(OSError, 'quarantined'): await async_setup_entry(self.hass, self.entry)

    async def test_real_store_swallowed_write_is_detected_before_commit(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            await async_setup_entry(self.hass,self.entry)
            group=self.hass.data[DOMAIN][self.entry.entry_id]
            before=group.registry.payload()
            flow=self.flow();await flow.async_step_add_device()
            with patch.object(Store,'async_save',new=AsyncMock()):
                result=await flow.async_step_device(self.record)
            self.assertEqual(result['errors']['base'],'save_failed')
            self.assertEqual(group.registry.payload(),before)
            self.assertEqual(await Store(self.hass,1,f'{DOMAIN}.{self.entry.entry_id}').async_load(),before)
            await async_unload_entry(self.hass,self.entry)

    async def test_offline_existing_devices_remain_editable_and_snapshot_allowlisted(self):
        await self.group.save_device(None,self.record)
        device=next(iter(self.group.registry.devices.values()))
        self.hass.states.async_remove('fan.a');self.hass.states.async_remove('sensor.t')
        result=await self.group.save_device(device['device_id'],{**self.record,'name':'Offline renamed','unexpected':{'nested':True}})
        self.assertEqual(result['name'],'Offline renamed')
        self.assertNotIn('unexpected',self.group.snapshot()['devices'][0])
        flow=self.flow();await flow.async_step_edit_device({'device':device['device_id']})
        self.assertEqual((await flow.async_step_device())['data_schema']({})['fan_entity'],'fan.a')

    async def test_name_preserves_pending_source_change_resets_fresh_duration(self):
        await self.group.save_device(None,self.record)
        device=next(iter(self.group.registry.devices.values()))
        self.group.controller.evaluate('fan.a',True,'off',35,60,100)
        self.assertIsNotNone(self.group.controller.status('fan.a')['pending'])
        await self.group.save_device(device['device_id'],{**self.record,'name':'Rename'})
        self.assertIsNotNone(self.group.controller.status('fan.a')['pending'])
        self.hass.states.async_set('sensor.t2','35',{'device_class':'temperature','unit_of_measurement':'°C'})
        await self.group.save_device(device['device_id'],{**self.record,'temperature_entity':'sensor.t2'})
        self.assertIsNone(self.group.controller.status('fan.a')['pending'])
        self.assertIsNone(self.group.controller.evaluate('fan.a',True,'off',35,60,1000))

    async def test_owned_manual_only_uses_real_state_machine_and_service_registry(self):
        await self.group.save_device(None,{'name':'Manual','fan_entity':'fan.a'})
        calls=[]
        async def service(call):
            calls.append(dict(call.data));self.hass.states.async_set('fan.a','on')
        self.hass.services.async_register('fan','turn_on',service)
        await self.group.manual('fan.a','on')
        self.assertEqual(calls,[{'entity_id':'fan.a'}])
        self.assertEqual(self.group.registry.manual_modes,{'fan.a':'on'})
        await self.group.manual('fan.a','auto')
        self.assertEqual(len(calls),1)
        await self.group.evaluate_all();self.assertEqual(len(calls),1)
        with self.assertRaises(ValueError):await self.group.manual('switch.b','on')
        with self.assertRaises(ValueError):await self.group.bind(self.group.registry.revision,'switch.b','sensor.t','sensor.h')

    async def test_delete_failure_keeps_device_binding_and_hold(self):
        await self.group.save_device(None,self.record)
        device=next(iter(self.group.registry.devices.values()))
        await self.group.registry.set_mode('fan.a','off')
        before=self.group.registry.payload()
        remove=self.flow();await remove.async_step_remove_device({'device':device['device_id']})
        async def fail(data):raise OSError('disk offline')
        self.group.registry._save=fail
        result=await remove.async_step_confirm_remove({'confirm':True})
        self.assertEqual(result['errors']['base'],'save_failed')
        self.assertEqual(self.group.registry.payload(),before)

    async def test_shutdown_rejects_before_store_can_schedule_late_write(self):
        from homeassistant.core import CoreState
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry
        from unittest.mock import AsyncMock
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            await async_setup_entry(self.hass,self.entry)
            group=self.hass.data[DOMAIN][self.entry.entry_id]
            self.hass.state=CoreState.stopping
            with patch.object(Store,'async_save',new=AsyncMock()) as save:
                with self.assertRaises(OSError):await group.save_device(None,self.record)
                self.assertEqual(save.await_count,0)
            self.hass.state=CoreState.not_running
            await async_unload_entry(self.hass,self.entry)

    async def test_native_options_manager_save_reopen_and_abort_cancel(self):
        from homeassistant.config_entries import ConfigEntries
        from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanConfigFlow
        from unittest.mock import AsyncMock
        manager=ConfigEntries(self.hass,{})
        manager._entries[self.entry.entry_id]=self.entry
        self.hass.config_entries=manager
        # Only bypass integration discovery/bootstrap, not HA flow machinery.
        with patch('homeassistant.config_entries._async_get_flow_handler',new=AsyncMock(return_value=GreenhouseFanConfigFlow)):
            result=await manager.options.async_init(self.entry.entry_id)
            result=await manager.options.async_configure(result['flow_id'],{'next_step_id':'add_device'})
            self.assertTrue(result['last_step'])
            cancelled=result['flow_id'];manager.options.async_abort(cancelled)
            self.assertEqual(self.saved,[])
            result=await manager.options.async_init(self.entry.entry_id)
            result=await manager.options.async_configure(result['flow_id'],{'next_step_id':'add_device'})
            result=await manager.options.async_configure(result['flow_id'],self.record)
            self.assertEqual(result['type'],'create_entry')
            self.assertEqual(len(self.saved),1)
            device=next(iter(self.group.registry.devices.values()))
            result=await manager.options.async_init(self.entry.entry_id)
            result=await manager.options.async_configure(result['flow_id'],{'next_step_id':'edit_device'})
            result=await manager.options.async_configure(result['flow_id'],{'device':device['device_id']})
            self.assertEqual(result['step_id'],'device')
            self.assertEqual(result['data_schema']({})['name'],'North fan')
            manager.options.async_abort(result['flow_id'])
            self.assertEqual(len(self.saved),1)

    async def test_failed_save_preserves_form_and_committed_state(self):
        async def fail(data): raise OSError('disk offline')
        self.group.registry._save = fail
        flow = self.flow(); await flow.async_step_add_device()
        result = await flow.async_step_device(self.record)
        self.assertEqual(result['errors']['base'], 'save_failed')
        self.assertEqual(result['data_schema']({})['name'], self.record['name'])
        self.assertEqual(self.group.registry.devices, {})

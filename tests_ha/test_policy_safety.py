"""Real HA policy persistence, Options conflicts and lifecycle safety."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch, AsyncMock
import test_options
import test_control_mode
from custom_components.uninus_greenhouse_fan import FanGroup
from custom_components.uninus_greenhouse_fan.const import DOMAIN
from custom_components.uninus_greenhouse_fan.registry import Registry, Conflict
from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanOptionsFlow, policy_schema


class PolicySafetyTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_options.OptionsTest.asyncSetUp
    asyncTearDown = test_options.OptionsTest.asyncTearDown
    durable = test_control_mode.ControlModeTest.durable

    def flow(self):
        flow = GreenhouseFanOptionsFlow(self.entry)
        flow.hass = self.hass
        return flow

    def changed(self):
        return {**self.group.snapshot()['policy'], 'temperature_on':35}

    async def fixture(self):
        await self.group.save_device(None, self.record)
        await self.group.save_device(None, {'name':'Hidden', 'fan_entity':'switch.b'})
        await self.group.registry.set_mode('switch.b', 'off')
        self.group.controller.set_mode('switch.b', 'off')
        self.hass.states.async_set('sensor.t', '40', {'unit_of_measurement':'°C'})
        await self.group.evaluate_all()
        self.assertEqual(self.group.snapshot()['runtime']['fan.a']['pending'], 'on')
        calls=[]
        async def service(call): calls.append((call.domain, call.service, dict(call.data)))
        for domain in ('fan','switch'):
            for action in ('turn_on','turn_off'): self.hass.services.async_register(domain, action, service)
        return calls

    async def test_native_schema_is_serializable_as_numeric_fields(self):
        import voluptuous_serialize
        from homeassistant.helpers.config_validation import custom_serializer
        fields=voluptuous_serialize.convert(policy_schema(self.changed()), custom_serializer=custom_serializer)
        self.assertEqual(len(fields),5)
        self.assertEqual([x['type'] for x in fields], ['float','float','float','float','integer'])

    async def test_native_conflict_failure_retains_draft_revision_and_timers(self):
        calls=await self.fixture()
        flow=self.flow(); await flow.async_step_policy()
        newer={**self.changed(), 'humidity_on':90}
        await self.group.save_policy(newer, 0)
        before=deepcopy(self.group.controller._states)
        result=await flow.async_step_policy({**self.changed(), 'temperature_on':37})
        self.assertEqual(result['errors'], {'base':'conflict'})
        self.assertEqual(flow._policy_revision,0)
        self.assertEqual(result['data_schema']({})['temperature_on'],37)
        self.assertEqual(self.group.snapshot()['policy'],newer)
        self.assertEqual(self.group.controller._states,before)
        flow=self.flow(); await flow.async_step_policy()
        async def failed(data): raise OSError('disk offline')
        with patch.object(self.group.registry, '_save', failed):
            result=await flow.async_step_policy({**newer,'temperature_on':38})
        self.assertEqual(result['errors'],{'base':'save_failed'})
        self.assertEqual(result['data_schema']({})['temperature_on'],38)
        self.assertEqual(flow._policy_revision,1)
        self.assertEqual(self.group.controller._states,before)
        self.assertEqual(calls,[])

    async def test_verified_failure_keeps_policy_pending_holds_and_reload_crud(self):
        calls=await self.fixture()
        before=self.group.registry.payload(); runtime=deepcopy(self.group.controller._states)
        store,adapter=await self.durable()
        read=Path.read_text; failures=[]; path=Path(store.path)
        def fail_three(target,*args,**kwargs):
            if target==path and len(failures)<3:
                failures.append(True);raise OSError('readback failed')
            return read(target,*args,**kwargs)
        with patch.object(Path,'read_text',fail_three):
            with self.assertRaisesRegex(OSError,'restored and verified'):
                await self.group.save_policy(self.changed(),0)
        self.assertEqual(self.group.registry.payload(),before)
        self.assertEqual(self.group.controller._states,runtime)
        self.assertEqual(await store.async_load(),before)
        self.assertFalse(adapter.pending.exists())
        saved=self.changed(); await self.group.save_policy(saved,0)
        self.assertIsNone(self.group.snapshot()['runtime']['fan.a']['pending'])
        self.assertEqual(self.group.snapshot()['runtime']['switch.b']['mode'],'off')
        self.group=FanGroup(self.hass,self.entry,Registry(self.entry.entry_id,await store.async_load(),adapter.save))
        self.hass.data[DOMAIN][self.entry.entry_id]=self.group
        row=self.group.registry.device_for_output('fan.a')
        await self.group.save_device(row['device_id'],{**row,'name':'Renamed'})
        await self.group.bind(self.group.registry.revision,'fan.a','sensor.t','sensor.h')
        await self.group.manual('switch.b','auto')
        await self.group.set_control_mode('manual')
        await self.group.remove_device(row['device_id'])
        self.assertEqual((await store.async_load())['policy'],saved)
        self.assertEqual((await store.async_load())['policy_revision'],1)
        self.assertEqual(calls,[])

    async def test_quarantine_keeps_old_effective_policy_disables_and_blocks_reload(self):
        calls=await self.fixture(); store,adapter=await self.durable()
        before=self.group.snapshot()['policy']; read=Path.read_text; path=Path(store.path)
        def fail(target,*args,**kwargs):
            if target==path: raise OSError('persistent readback fault')
            return read(target,*args,**kwargs)
        with patch.object(Path,'read_text',fail):
            with self.assertRaises(OSError): await self.group.save_policy(self.changed(),0)
        self.assertEqual(self.group.snapshot()['policy'],before)
        self.assertFalse(self.group.active); self.assertTrue(adapter.pending.exists())
        with self.assertRaises(OSError): adapter.check_quarantine()
        with self.assertRaises(ValueError): await self.group.save_policy(self.changed(),0)
        self.assertEqual(calls,[])

    async def test_repeated_cancel_drains_real_store_and_rolls_back_policy(self):
        from homeassistant.helpers.storage import Store
        calls=await self.fixture(); store,adapter=await self.durable()
        before=self.group.registry.payload(); runtime=deepcopy(self.group.controller._states)
        entered,release=asyncio.Event(),threading.Event(); writer=Store._write_prepared_data
        def paused(target,*args):
            self.hass.loop.call_soon_threadsafe(entered.set)
            if not release.wait(5): raise OSError('test timeout')
            return writer(target,*args)
        with patch.object(Store,'_write_prepared_data',paused):
            operation=asyncio.create_task(self.group.save_policy(self.changed(),0))
            try:
                await asyncio.wait_for(entered.wait(),5)
                operation.cancel(); await asyncio.sleep(0); operation.cancel()
            finally: release.set()
            with self.assertRaises(asyncio.CancelledError): await operation
        self.assertEqual(await store.async_load(),before)
        self.assertEqual(self.group.registry.payload(),before)
        self.assertEqual(self.group.controller._states,runtime)
        self.assertEqual(calls,[])

    async def test_shutdown_during_write_no_runtime_publication_or_service(self):
        from homeassistant.helpers.storage import Store
        from homeassistant.core import CoreState
        calls=await self.fixture(); store,adapter=await self.durable()
        before=self.group.snapshot()['policy']; entered,release=asyncio.Event(),threading.Event()
        writer=Store._write_prepared_data
        def paused(target,*args):
            self.hass.loop.call_soon_threadsafe(entered.set)
            if not release.wait(5): raise OSError('test timeout')
            return writer(target,*args)
        with patch.object(Store,'_write_prepared_data',paused):
            operation=asyncio.create_task(self.group.save_policy(self.changed(),0))
            try:
                await asyncio.wait_for(entered.wait(),5); self.hass.set_state(CoreState.stopping)
            finally: release.set()
            with self.assertRaises(OSError): await operation
        self.assertEqual(self.group.snapshot()['policy'],before)
        self.assertEqual(calls,[])
        self.hass.set_state(CoreState.not_running)

    async def test_unload_reload_drains_policy_and_rehydrates_verified_record(self):
        from custom_components.uninus_greenhouse_fan import async_setup_entry,async_unload_entry
        from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            await async_setup_entry(self.hass,self.entry)
            self.group=self.hass.data[DOMAIN][self.entry.entry_id]
            calls=await self.fixture(); expected=self.changed()
            entered,release=asyncio.Event(),threading.Event(); prepare=VerifiedStore._prepare
            def paused(adapter):
                self.hass.loop.call_soon_threadsafe(entered.set)
                if not release.wait(5): raise OSError('test timeout')
                return prepare(adapter)
            with patch.object(VerifiedStore,'_prepare',paused):
                operation=asyncio.create_task(self.group.save_policy(expected,0))
                try:
                    await asyncio.wait_for(entered.wait(),5)
                    unload=asyncio.create_task(async_unload_entry(self.hass,self.entry)); await asyncio.sleep(0)
                    setup=asyncio.create_task(async_setup_entry(self.hass,self.entry)); await asyncio.sleep(0)
                    self.assertFalse(unload.done()); self.assertFalse(setup.done())
                finally: release.set()
                with self.assertRaises(ValueError): await operation
                await unload; await setup
            self.group=self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(self.group.snapshot()['policy'],expected)
            self.assertEqual(self.group.registry.manual_modes,{'switch.b':'off'})
            self.assertEqual(calls,[])
            await async_unload_entry(self.hass,self.entry)

    async def test_policy_serializes_crud_global_and_evaluation_no_actuation(self):
        calls=await self.fixture()
        started,release=asyncio.Event(),asyncio.Event(); original=self.group.registry._save
        async def slow(data):
            started.set(); await release.wait(); await original(data)
        self.group.registry._save=slow
        operation=asyncio.create_task(self.group.save_policy(self.changed(),0)); await started.wait()
        row=self.group.registry.device_for_output('fan.a')
        edit=asyncio.create_task(self.group.save_device(row['device_id'],{**row,'name':'New name'}))
        mode=asyncio.create_task(self.group.set_control_mode('manual'))
        evaluate=asyncio.create_task(self.group.evaluate_all()); await asyncio.sleep(0)
        self.assertFalse(edit.done()); self.assertFalse(mode.done()); self.assertFalse(evaluate.done())
        release.set(); await operation; await edit; await mode; await evaluate
        self.assertEqual(self.group.registry.policy_revision,1)
        self.assertEqual(self.saved[-1]['policy']['temperature_on'],35)
        self.assertEqual(self.group.registry.manual_modes,{'switch.b':'off'})
        self.assertEqual(calls,[])

    async def test_legacy_options_only_migrate_once_preserve_ids_global_and_holds(self):
        await self.fixture(); before=self.group.registry.payload()
        legacy={k:v for k,v in before.items() if k not in ('policy','policy_revision')}
        object.__setattr__(self.entry,'options',{'temperature_on':36,'duration_seconds':18})
        registry=Registry(self.entry.entry_id,legacy,self.group.registry._save)
        migrated=FanGroup(self.hass,self.entry,registry)
        self.assertEqual(migrated.snapshot()['policy']['temperature_on'],36)
        self.assertEqual(migrated.snapshot()['policy']['duration_seconds'],18)
        self.assertEqual(registry.devices,before['devices']); self.assertEqual(registry.manual_modes,before['manual_modes'])
        saved={**migrated.snapshot()['policy'],'temperature_on':40}
        await migrated.save_policy(saved,0)
        object.__setattr__(self.entry,'options',{'temperature_on':31})
        restored=FanGroup(self.hass,self.entry,Registry(self.entry.entry_id,self.saved[-1],registry._save))
        await restored._options_updated(self.hass,self.entry)
        self.assertEqual(restored.snapshot()['policy'],saved)

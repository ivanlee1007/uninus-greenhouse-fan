"""Global control through native HA decorators, storage and lifecycle locks."""
import asyncio
from copy import deepcopy
import types
import unittest
import test_options
from homeassistant.exceptions import Unauthorized
from custom_components.uninus_greenhouse_fan import FanGroup
from custom_components.uninus_greenhouse_fan.registry import Registry
from custom_components.uninus_greenhouse_fan import websocket as ws


class ControlModeTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_options.OptionsTest.asyncSetUp
    asyncTearDown = test_options.OptionsTest.asyncTearDown

    async def durable(self):
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
        store=Store(self.hass,1,f'{self.entry.domain}.{self.entry.entry_id}',atomic_writes=True)
        await store.async_save(self.group.registry.payload())
        adapter=VerifiedStore(self.hass,store,self.group.registry.payload(),self.group.stop)
        self.group.registry._save=adapter.save
        return store,adapter

    async def test_global_real_verified_store_failure_retains_pending_and_holds(self):
        from pathlib import Path
        from unittest.mock import patch
        await self.group.save_device(None,self.record)
        await self.group.save_device(None,{'name':'Hidden','fan_entity':'switch.b'})
        await self.group.registry.set_mode('switch.b','off')
        self.group.controller.set_mode('switch.b','off')
        await self.group.evaluate_all()
        before=self.group.registry.payload();runtime=deepcopy(self.group.controller._states)
        store,adapter=await self.durable()
        path=Path(store.path);read=Path.read_text;failures=[]
        def fail_three(target,*args,**kwargs):
            if target==path and len(failures)<3:
                failures.append(True);raise OSError('readback failed')
            return read(target,*args,**kwargs)
        with patch.object(Path,'read_text',fail_three):
            with self.assertRaisesRegex(OSError,'restored and verified'): await self.group.set_control_mode('manual')
        self.assertEqual(self.group.registry.payload(),before)
        self.assertEqual(self.group.controller._states,runtime)
        self.assertEqual(await store.async_load(),before)
        self.assertTrue(self.group.active)
        self.assertFalse(Path(str(path)+'.pending').exists())

    async def test_global_real_store_repeated_cancellation_drains_and_rolls_back(self):
        import threading
        from unittest.mock import patch
        from homeassistant.helpers.storage import Store
        await self.group.save_device(None,self.record)
        await self.group.evaluate_all()
        store,adapter=await self.durable()
        before=self.group.registry.payload();runtime=deepcopy(self.group.controller._states)
        entered,release=asyncio.Event(),threading.Event();writer=Store._write_prepared_data
        def paused(target,*args):
            self.hass.loop.call_soon_threadsafe(entered.set)
            if not release.wait(5): raise OSError('test timeout')
            return writer(target,*args)
        with patch.object(Store,'_write_prepared_data',paused):
            operation=asyncio.create_task(self.group.set_control_mode('manual'))
            try:
                await asyncio.wait_for(entered.wait(),5)
                operation.cancel();await asyncio.sleep(0);operation.cancel()
            finally: release.set()
            with self.assertRaises(asyncio.CancelledError): await operation
        self.assertEqual(self.group.registry.payload(),before)
        self.assertEqual(self.group.controller._states,runtime)
        self.assertEqual(await store.async_load(),before)

    async def test_global_real_store_quarantine_retains_previous_mode_and_closes_control(self):
        from pathlib import Path
        from unittest.mock import patch
        await self.group.save_device(None,self.record)
        store,adapter=await self.durable()
        before=self.group.registry.payload();read=Path.read_text;path=Path(store.path)
        def fail(target,*args,**kwargs):
            if target==path: raise OSError('persistent readback fault')
            return read(target,*args,**kwargs)
        with patch.object(Path,'read_text',fail):
            with self.assertRaises(OSError): await self.group.set_control_mode('manual')
        self.assertFalse(self.group.active)
        self.assertEqual(self.group.registry.payload(),before)
        self.assertTrue(Path(str(path)+'.pending').exists())
        with self.assertRaisesRegex(OSError,'quarantin'): adapter.check_quarantine()
        with self.assertRaisesRegex(ValueError,'unloaded'): await self.group.set_control_mode('auto')

    async def test_global_cross_group_ownership_and_unloaded_scope_reject_before_save(self):
        from homeassistant.config_entries import ConfigEntry
        from custom_components.uninus_greenhouse_fan.const import DOMAIN
        await self.group.save_device(None,self.record)
        other=ConfigEntry(domain=DOMAIN,title='Other',data={},options={},source='user',version=1,minor_version=1,unique_id=None,discovery_keys={},subentries_data=[])
        self.hass.config_entries.async_entries=lambda domain:[self.entry,other]
        before=self.group.registry.payload()
        with self.assertRaisesRegex(ValueError,'unloaded'): await self.group.set_control_mode('manual')
        registry=Registry(other.entry_id,{},self.group.registry._save)
        await registry.save_device(None,{'name':'Duplicate','fan_entity':'fan.a'})
        self.hass.data[DOMAIN][other.entry_id]=FanGroup(self.hass,other,registry)
        with self.assertRaisesRegex(ValueError,'duplicate_output'): await self.group.set_control_mode('manual')
        self.assertEqual(self.group.registry.payload(),before)

    async def test_global_reload_waits_for_real_journal_prepare_and_rehydrates_gate(self):
        import threading
        from unittest.mock import patch,AsyncMock
        from custom_components.uninus_greenhouse_fan import async_setup_entry,async_unload_entry
        from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
        from homeassistant.helpers.storage import Store
        from custom_components.uninus_greenhouse_fan.const import DOMAIN
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            await async_setup_entry(self.hass,self.entry)
            self.group=self.hass.data[DOMAIN][self.entry.entry_id]
            await self.group.save_device(None,self.record)
            entered,release=asyncio.Event(),threading.Event();prepare=VerifiedStore._prepare
            def paused(adapter):
                self.hass.loop.call_soon_threadsafe(entered.set)
                if not release.wait(5): raise OSError('test timeout')
                return prepare(adapter)
            with patch.object(VerifiedStore,'_prepare',paused):
                operation=asyncio.create_task(self.group.set_control_mode('manual'))
                await asyncio.wait_for(entered.wait(),5)
                unload=asyncio.create_task(async_unload_entry(self.hass,self.entry))
                await asyncio.sleep(0)
                setup=asyncio.create_task(async_setup_entry(self.hass,self.entry))
                await asyncio.sleep(0)
                self.assertFalse(self.group.active)
                self.assertFalse(unload.done());self.assertFalse(setup.done())
                release.set()
                with self.assertRaisesRegex(ValueError,'unloaded'): await operation
                await unload;await setup
            self.group=self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(self.group.snapshot()['control_mode'],'manual')
            self.assertEqual(self.group.snapshot()['runtime']['fan.a']['mode'],'manual')
            self.assertEqual(await Store(self.hass,1,f'{DOMAIN}.{self.entry.entry_id}').async_load(),self.group.registry.payload())
            await async_unload_entry(self.hass,self.entry)

    async def test_native_ws_admin_schema_loaded_scope_no_service(self):
        self.assertTrue(hasattr(ws, 'ws_set_control_mode'))
        await self.group.save_device(None,self.record)
        replies=[]
        connection=types.SimpleNamespace(user=types.SimpleNamespace(is_admin=False),send_result=lambda *args:replies.append(('result',args)),send_error=lambda *args:replies.append(('error',args)))
        msg={'id':1,'type':'uninus_greenhouse_fan/set_control_mode','entry_id':self.entry.entry_id,'control_mode':'manual'}
        with self.assertRaises(Unauthorized): ws.ws_set_control_mode(self.hass,connection,msg)
        connection.user.is_admin=True
        ws.ws_set_control_mode(self.hass,connection,msg)
        await self.hass.async_block_till_done()
        self.assertEqual(replies[-1][0],'result')
        self.assertEqual(replies[-1][1][1]['runtime']['fan.a']['mode'],'manual')
        self.assertEqual(self.hass.states.get('fan.a').state,'off')
        msg['entry_id']='missing'
        ws.ws_set_control_mode(self.hass,connection,msg)
        await self.hass.async_block_till_done()
        self.assertEqual(replies[-1][1][1],'not_found')
        import voluptuous as vol
        with self.assertRaises(vol.Invalid): ws.ws_set_control_mode._ws_schema({**msg,'control_mode':'bad'})

    async def test_global_failure_preserves_all_runtime_and_persisted_modes(self):
        await self.group.save_device(None,self.record)
        await self.group.registry.set_mode('fan.a','off')
        self.group.controller.set_mode('fan.a','off')
        before=self.group.registry.payload()
        runtime=deepcopy(self.group.controller._states)
        async def fail(data): raise OSError('disk')
        self.group.registry._save=fail
        with self.assertRaises(OSError): await self.group.set_control_mode('manual')
        self.assertEqual(self.group.registry.payload(),before)
        self.assertEqual(self.group.controller._states,runtime)

    async def test_global_unload_after_persistence_never_publishes_runtime(self):
        await self.group.save_device(None,self.record)
        old=deepcopy(self.group.controller._states)
        async def stop(data):
            self.saved.append(data)
            self.group.stop()
        self.group.registry._save=stop
        with self.assertRaisesRegex(ValueError,'unloaded'): await self.group.set_control_mode('manual')
        self.assertEqual(self.group.controller._states,old)
        self.assertEqual(self.saved[-1]['control_mode'],'manual')
        reload=FanGroup(self.hass,self.entry,Registry(self.entry.entry_id,self.saved[-1],stop))
        self.assertEqual(reload.snapshot()['runtime']['fan.a']['mode'],'manual')

    async def test_global_serializes_manual_crud_evaluation(self):
        await self.group.save_device(None,self.record)
        started,release=asyncio.Event(),asyncio.Event()
        original=self.group.registry._save
        async def slow(data):
            started.set()
            await release.wait()
            await original(data)
        self.group.registry._save=slow
        toggle=asyncio.create_task(self.group.set_control_mode('manual'))
        await started.wait()
        manual=asyncio.create_task(self.group.manual('fan.a','auto'))
        edit=asyncio.create_task(self.group.save_device(None,{'name':'B','fan_entity':'switch.b'}))
        evaluate=asyncio.create_task(self.group.evaluate_all())
        await asyncio.sleep(0)
        self.assertFalse(manual.done());self.assertFalse(edit.done());self.assertFalse(evaluate.done())
        release.set();await toggle
        with self.assertRaisesRegex(ValueError,'全域'): await manual
        await edit;await evaluate
        self.assertEqual(self.group.snapshot()['runtime']['switch.b']['mode'],'manual')

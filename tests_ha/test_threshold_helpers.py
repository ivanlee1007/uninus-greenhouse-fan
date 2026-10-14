"""Real native input_number component/entities/services, isolated disk only."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.components import input_number
from homeassistant.helpers import entity_registry as er, device_registry as dr
from custom_components.uninus_greenhouse_fan import FanGroup
from custom_components.uninus_greenhouse_fan.const import DOMAIN
from custom_components.uninus_greenhouse_fan.registry import Registry

class ThresholdHelpersTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        await er.async_load(self.hass)
        await dr.async_load(self.hass)
        await input_number.async_setup(self.hass, {})
        self.entry = self.make_entry()
        self.saved = []
        async def save(data): self.saved.append(data)
        self.group = FanGroup(self.hass, self.entry, Registry(self.entry.entry_id, {}, save))
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.group}

    def make_entry(self, title='North'):
        entry = ConfigEntry(domain=DOMAIN, title=title, data={}, options={}, source='user', version=1, minor_version=1, unique_id=None, discovery_keys={}, subentries_data=[])
        self.hass.config_entries._entries[entry.entry_id] = entry
        return entry

    async def asyncTearDown(self):
        for group in list(self.hass.data.get(DOMAIN, {}).values()):
            if isinstance(group, FanGroup):
                group.stop()
                if getattr(group, 'threshold_helpers', None):
                    await group.threshold_helpers.async_unload()
        await self.hass.async_stop()
        self.directory.cleanup()

    async def test_four_native_entities_services_and_entry_association(self):
        from custom_components.uninus_greenhouse_fan.threshold_helpers import async_setup_helpers
        await async_setup_helpers(self.group)
        mapping = self.group.snapshot()['threshold_entities']
        self.assertEqual(set(mapping), {'temperature_on','temperature_off','humidity_on','humidity_off'})
        from homeassistant.helpers.entity_component import DATA_INSTANCES
        component = self.hass.data[DATA_INSTANCES]['input_number']
        for key, identity in mapping.items():
            entity = component.get_entity(identity)
            self.assertIsInstance(entity, input_number.InputNumber)
            self.assertEqual(er.async_get(self.hass).async_get(identity).config_entry_id, self.entry.entry_id)
            state = self.hass.states.get(identity)
            self.assertEqual(float(state.state), self.group.registry.policy[key])
            self.assertEqual(state.attributes['step'], 0.1)
            self.assertEqual(state.attributes['mode'], 'slider')
            self.assertFalse(state.attributes['editable'])
            self.assertIn('North', state.attributes['friendly_name'])
        await self.hass.services.async_call('input_number','set_value', {'entity_id':mapping['temperature_on'],'value':35}, blocking=True)
        self.assertEqual(self.group.registry.policy['temperature_on'], 35)
        self.assertEqual(float(self.hass.states.get(mapping['temperature_on']).state), 35)

    async def setup_helpers(self):
        from custom_components.uninus_greenhouse_fan.threshold_helpers import async_setup_helpers
        await async_setup_helpers(self.group)
        return self.group.snapshot()['threshold_entities']

    async def call(self, mapping, key, value=None, service='set_value'):
        data = {'entity_id':mapping[key]}
        if service == 'set_value': data['value'] = value
        return await self.hass.services.async_call('input_number', service, data, blocking=True)

    def assert_values(self, mapping, policy):
        for key, identity in mapping.items():
            self.assertEqual(float(self.hass.states.get(identity).state), policy[key])

    async def test_crosspath_policy_and_threshold_writes_sync_all_four(self):
        mapping = await self.setup_helpers()
        policy = {**self.group.registry.policy, 'temperature_on':38, 'temperature_off':28, 'humidity_on':95, 'humidity_off':75}
        await self.group.save_policy(policy, 0)
        self.assert_values(mapping, policy)
        policy.update(temperature_on=39, humidity_on=96)
        await self.group.save_thresholds({k:policy[k] for k in mapping}, 1)
        self.assert_values(mapping, policy)

    async def test_real_setup_entry_reload_and_remove_own_runtime_registry(self):
        from custom_components.uninus_greenhouse_fan import async_setup_entry, async_unload_entry, async_remove_entry
        unrelated = input_number.InputNumber.from_storage({'id':'unrelated','name':'North Temperature on','initial':9,'min':0,'max':50,'step':1,'mode':'slider'})
        from homeassistant.helpers.entity_component import DATA_INSTANCES
        await self.hass.data[DATA_INSTANCES]['input_number'].async_add_entities([unrelated])
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource', new=AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
            self.group = self.hass.data[DOMAIN][self.entry.entry_id]
            mapping = self.group.snapshot()['threshold_entities']
            self.assertEqual(len(mapping),4)
            await async_unload_entry(self.hass, self.entry)
            for identity in mapping.values():
                self.assertIsNotNone(er.async_get(self.hass).async_get(identity))
                state = self.hass.states.get(identity)
                self.assertTrue(state is None or state.state == 'unavailable')
            await async_setup_entry(self.hass, self.entry)
            self.group = self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(self.group.snapshot()['threshold_entities'], mapping)
            await async_remove_entry(self.hass, self.entry)
            for identity in mapping.values():
                self.assertIsNone(self.hass.states.get(identity))
                self.assertIsNone(er.async_get(self.hass).async_get(identity))
        self.assertIsNotNone(self.hass.states.get(unrelated.entity_id))
        self.assertIsNotNone(er.async_get(self.hass).async_get(unrelated.entity_id))

    async def test_pair_nonfinite_limits_bool_direct_rejection_preserves_timers(self):
        from copy import deepcopy
        from homeassistant.exceptions import HomeAssistantError
        mapping = await self.setup_helpers()
        self.group.controller._state('fan.test').update(pending='on', since=17)
        before = deepcopy(self.group.controller._states)
        policy = dict(self.group.registry.policy)
        for key, value in [('temperature_on',20), ('temperature_off',40), ('humidity_off',99), ('humidity_on',101), ('temperature_off',-1), ('temperature_on',float('nan')), ('humidity_off',float('inf'))]:
            with self.assertRaises(HomeAssistantError): await self.call(mapping,key,value)
            self.assert_values(mapping,policy)
            self.assertEqual(self.group.registry.policy,policy)
            self.assertEqual(self.group.controller._states,before)
        with self.assertRaises(HomeAssistantError): await self.group.threshold_helpers.entities['temperature_off'].async_set_value(True)
        self.assertEqual(self.saved,[])

    async def test_native_bool_coercion_limitation_is_exposed_not_claimed_strict(self):
        # HA's unchanged native schema Coerce(float) erases the original bool.
        mapping = await self.setup_helpers()
        await self.call(mapping,'temperature_off',True)
        self.assertEqual(self.group.registry.policy['temperature_off'],1.0)

    async def test_increment_decrement_serial_merge_and_exact_state_events(self):
        mapping = await self.setup_helpers()
        changes=[]
        self.hass.bus.async_listen('state_changed',lambda event:changes.append(event.data['entity_id']))
        await asyncio.gather(self.call(mapping,'temperature_on',35), self.call(mapping,'humidity_on',97))
        self.assertEqual(self.group.registry.policy['temperature_on'],35)
        self.assertEqual(self.group.registry.policy['humidity_on'],97)
        await asyncio.gather(*(self.call(mapping,'temperature_on',service='increment') for _ in range(5)))
        self.assertEqual(self.group.registry.policy['temperature_on'],35.5)
        await self.call(mapping,'temperature_on',service='decrement')
        self.assertEqual(self.group.registry.policy['temperature_on'],35.4)
        await self.hass.async_block_till_done()
        owned=[identity for identity in changes if identity in mapping.values()]
        self.assertEqual(len(owned),8)
        self.assertEqual(len(self.saved),8)
        self.assert_values(mapping,self.group.registry.policy)

    async def test_long_save_failure_keeps_everything_old_and_valid_resets_only_timers(self):
        from copy import deepcopy
        from homeassistant.exceptions import HomeAssistantError
        mapping = await self.setup_helpers()
        self.group.controller._state('fan.held').update(mode='off',pending='on',since=3)
        self.group.controller.control_mode='manual'
        state=deepcopy(self.group.controller._states)
        policy=dict(self.group.registry.policy)
        entered,release=asyncio.Event(),asyncio.Event()
        async def failing(payload):
            entered.set(); await release.wait(); raise OSError('write failed')
        save=self.group.registry._save
        self.group.registry._save=failing
        operation=asyncio.create_task(self.call(mapping,'temperature_on',35))
        await asyncio.wait_for(entered.wait(),5)
        self.assert_values(mapping,policy)
        self.assertEqual(self.group.registry.policy,policy)
        release.set()
        with self.assertRaises(HomeAssistantError): await operation
        self.assertEqual(self.group.controller._states,state)
        self.assert_values(mapping,policy)
        self.group.registry._save=save
        await self.call(mapping,'temperature_on',35)
        self.assertEqual(self.group.controller._states['fan.held']['mode'],'off')
        self.assertIsNone(self.group.controller._states['fan.held']['since'])
        self.assertEqual(self.group.controller.control_mode,'manual')

    async def test_same_names_rename_and_registry_delete_recover_on_reload(self):
        mapping = await self.setup_helpers()
        other_entry=self.make_entry()
        other=FanGroup(self.hass,other_entry,Registry(other_entry.entry_id,{},AsyncMock()))
        self.hass.data[DOMAIN][other_entry.entry_id]=other
        from custom_components.uninus_greenhouse_fan.threshold_helpers import async_setup_helpers
        await async_setup_helpers(other)
        self.assertTrue(set(mapping.values()).isdisjoint(other.snapshot()['threshold_entities'].values()))
        registry=er.async_get(self.hass)
        registry.async_update_entity(mapping['temperature_on'], new_entity_id='input_number.user_renamed_threshold', name='My threshold')
        await self.hass.async_block_till_done()
        renamed=self.group.snapshot()['threshold_entities']
        self.assertEqual(renamed['temperature_on'],'input_number.user_renamed_threshold')
        await self.call(renamed,'temperature_on',35)
        registry.async_remove(renamed['humidity_off'])
        await self.hass.async_block_till_done()
        await self.group.threshold_helpers.async_unload()
        self.group.threshold_helpers=None
        await async_setup_helpers(self.group)
        restored=self.group.snapshot()['threshold_entities']
        self.assertEqual(restored['temperature_on'],'input_number.user_renamed_threshold')
        self.assertEqual(len(restored),4)
        self.assert_values(restored,self.group.registry.policy)

    async def test_partial_creation_cleans_only_new_own_rows_retry_safe(self):
        from custom_components.uninus_greenhouse_fan.threshold_helpers import async_setup_helpers, ThresholdInputNumber
        from homeassistant.exceptions import HomeAssistantError
        original=ThresholdInputNumber.async_added_to_hass
        async def fail(entity):
            if entity.key=='humidity_on': raise RuntimeError('partial failure')
            await original(entity)
        with patch.object(ThresholdInputNumber,'async_added_to_hass',fail), self.assertLogs('custom_components.uninus_greenhouse_fan.threshold_helpers',level='ERROR'):
            with self.assertRaises(HomeAssistantError): await async_setup_helpers(self.group)
        rows=[row for row in er.async_get(self.hass).entities.values() if row.config_entry_id==self.entry.entry_id]
        self.assertEqual(rows,[])
        self.assertIsNone(self.group.threshold_helpers)
        await async_setup_helpers(self.group)
        self.assertEqual(len(self.group.snapshot()['threshold_entities']),4)

    async def test_protects_unique_id_associated_with_another_entry(self):
        from custom_components.uninus_greenhouse_fan.threshold_helpers import async_setup_helpers,unique_id
        from homeassistant.exceptions import HomeAssistantError
        unrelated=self.make_entry('Other')
        row=er.async_get(self.hass).async_get_or_create('input_number',DOMAIN,unique_id(self.entry.entry_id,'temperature_on'),config_entry=unrelated,suggested_object_id='do_not_take_over')
        with self.assertRaises(HomeAssistantError): await async_setup_helpers(self.group)
        self.assertEqual(er.async_get(self.hass).async_get(row.entity_id).config_entry_id,unrelated.entry_id)

    async def test_entry_partial_failure_never_loads_group_or_starts_timers_and_retries(self):
        from custom_components.uninus_greenhouse_fan import async_setup_entry
        from custom_components.uninus_greenhouse_fan.threshold_helpers import ThresholdInputNumber
        from homeassistant.exceptions import HomeAssistantError
        original=ThresholdInputNumber.async_added_to_hass
        async def failing(entity):
            if entity.key=='humidity_on': raise RuntimeError('partial creation failure')
            await original(entity)
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            with patch.object(ThresholdInputNumber,'async_added_to_hass',failing), patch.object(FanGroup,'start',autospec=True) as start, self.assertLogs('custom_components.uninus_greenhouse_fan.threshold_helpers',level='ERROR'):
                with self.assertRaises(HomeAssistantError): await async_setup_entry(self.hass,self.entry)
                start.assert_not_called()
            self.assertNotIn(self.entry.entry_id,self.hass.data[DOMAIN])
            self.assertEqual([row for row in er.async_get(self.hass).entities.values() if row.config_entry_id==self.entry.entry_id],[])
            await async_setup_entry(self.hass,self.entry)
            self.group=self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(len(self.group.snapshot()['threshold_entities']),4)
            self.assertEqual(len(self.group._unsubs),2)

    async def test_existing_canonical_policy_migration_is_idempotent_and_not_restore_state(self):
        from custom_components.uninus_greenhouse_fan import async_setup_entry,async_unload_entry
        from homeassistant.helpers.storage import Store
        policy={**self.group.registry.policy,'temperature_on':38,'temperature_off':28,'humidity_on':96,'humidity_off':72}
        payload={**self.group.registry.payload(),'policy':policy,'policy_revision':9}
        store=Store(self.hass,1,DOMAIN+'.'+self.entry.entry_id,atomic_writes=True)
        await store.async_save(payload)
        with patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            await async_setup_entry(self.hass,self.entry)
            self.group=self.hass.data[DOMAIN][self.entry.entry_id]
            mapping=self.group.snapshot()['threshold_entities']
            self.assert_values(mapping,policy)
            await async_unload_entry(self.hass,self.entry)
            await async_setup_entry(self.hass,self.entry)
            self.group=self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(self.group.snapshot()['threshold_entities'],mapping)
            self.assertEqual(self.group.registry.policy_revision,9)
            self.assert_values(mapping,policy)
            rows=[row for row in er.async_get(self.hass).entities.values() if row.config_entry_id==self.entry.entry_id]
            self.assertEqual(len(rows),4)

    async def test_changes_reset_real_pending_preserve_durable_holds_and_never_call_outputs(self):
        mapping=await self.setup_helpers()
        self.hass.states.async_set('fan.virtual','off')
        self.hass.states.async_set('switch.held','off')
        self.hass.states.async_set('sensor.temperature','40',{'device_class':'temperature','unit_of_measurement':'°C'})
        self.hass.states.async_set('sensor.humidity','85',{'device_class':'humidity','unit_of_measurement':'%'})
        await self.group.save_device(None,{'name':'Virtual','fan_entity':'fan.virtual','temperature_entity':'sensor.temperature','humidity_entity':'sensor.humidity'})
        await self.group.save_device(None,{'name':'Held','fan_entity':'switch.held'})
        await self.group.registry.set_mode('switch.held','off')
        self.group.controller.set_mode('switch.held','off')
        output_calls=[]
        async def output(call): output_calls.append(call)
        for domain in ('fan','switch'):
            for action in ('turn_on','turn_off'): self.hass.services.async_register(domain,action,output)
        await self.group.evaluate_all()
        self.assertIsNotNone(self.group.controller._states['fan.virtual']['since'])
        before=self.group.registry.payload()
        await self.call(mapping,'temperature_on',35)
        self.assertIsNone(self.group.controller._states['fan.virtual']['since'])
        self.assertEqual(self.group.registry.manual_modes,before['manual_modes'])
        self.assertEqual(self.group.controller._states['switch.held']['mode'],'off')
        await self.group.set_control_mode('manual')
        await self.call(mapping,'humidity_on',95)
        self.assertEqual(self.group.registry.control_mode,'manual')
        self.assertEqual(self.group.controller.control_mode,'manual')
        self.assertEqual(self.group.registry.manual_modes,before['manual_modes'])
        self.assertEqual(output_calls,[])
        self.assert_values(mapping,self.group.registry.policy)

    async def test_service_during_partial_setup_is_rejected_without_a_write(self):
        from custom_components.uninus_greenhouse_fan.threshold_helpers import async_setup_helpers, ThresholdInputNumber
        from homeassistant.exceptions import HomeAssistantError
        entered,release=asyncio.Event(),asyncio.Event()
        original=ThresholdInputNumber.async_added_to_hass
        async def paused(entity):
            if entity.key=='humidity_off': entered.set();await release.wait()
            await original(entity)
        with patch.object(ThresholdInputNumber,'async_added_to_hass',paused):
            setup=asyncio.create_task(async_setup_helpers(self.group))
            try:
                await asyncio.wait_for(entered.wait(),5)
                entity_id=next(entity.entity_id for entity in self.hass.data['entity_components']['input_number'].entities if getattr(entity,'key',None)=='temperature_on')
                with self.assertRaises(HomeAssistantError):
                    await self.hass.services.async_call('input_number','set_value',{'entity_id':entity_id,'value':35},blocking=True)
                self.assertEqual(self.saved,[])
            finally:
                release.set();await setup

    async def test_native_increment_decrement_clamp_at_slider_bounds(self):
        mapping=await self.setup_helpers()
        await self.call(mapping,'temperature_on',50)
        await self.call(mapping,'temperature_on',service='increment')
        await self.call(mapping,'temperature_off',0)
        await self.call(mapping,'temperature_off',service='decrement')
        self.assertEqual(self.group.registry.policy['temperature_on'],50)
        self.assertEqual(self.group.registry.policy['temperature_off'],0)

    async def test_native_services_keep_entity_permissions_without_admin_bypass(self):
        import types
        from homeassistant.core import Context
        from homeassistant.auth.permissions import PolicyPermissions, PermissionLookup
        from homeassistant.exceptions import Unauthorized
        mapping=await self.setup_helpers()
        allowed=mapping['temperature_on']; forbidden=mapping['humidity_on']
        permissions=PolicyPermissions({'entities':{'entity_ids':{allowed:{'read':True,'control':True},forbidden:{'read':True,'control':False}}}},PermissionLookup(er.async_get(self.hass),dr.async_get(self.hass)))
        user=types.SimpleNamespace(is_admin=False,permissions=permissions)
        self.hass.auth=types.SimpleNamespace(async_get_user=AsyncMock(return_value=user))
        await self.hass.services.async_call('input_number','set_value',{'entity_id':allowed,'value':35},blocking=True,context=Context(user_id='non-admin'))
        self.assertEqual(self.group.registry.policy['temperature_on'],35)
        with self.assertRaises(Unauthorized):
            await self.hass.services.async_call('input_number','set_value',{'entity_id':forbidden,'value':99},blocking=True,context=Context(user_id='non-admin'))
        self.assertEqual(len(self.saved),1)

    async def test_native_options_manager_and_admin_ws_sync_all_helpers(self):
        import types
        from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanConfigFlow
        from custom_components.uninus_greenhouse_fan import websocket as ws
        mapping=await self.setup_helpers()
        manager=self.hass.config_entries
        with patch('homeassistant.config_entries._async_get_flow_handler',new=AsyncMock(return_value=GreenhouseFanConfigFlow)):
            result=await manager.options.async_init(self.entry.entry_id)
            result=await manager.options.async_configure(result['flow_id'],{'next_step_id':'policy'})
            policy={**self.group.registry.policy,'temperature_on':36,'temperature_off':28,'humidity_on':98,'humidity_off':72}
            result=await manager.options.async_configure(result['flow_id'],policy)
            self.assertEqual(result['type'],'create_entry')
            self.assert_values(mapping,policy)
        replies=[]
        connection=types.SimpleNamespace(user=types.SimpleNamespace(is_admin=True),send_result=lambda *a:replies.append(a),send_error=lambda *a:self.fail(str(a)))
        policy.update(temperature_on=37,humidity_off=71)
        ws.ws_save_thresholds(self.hass,connection,{'id':1,'type':DOMAIN+'/save_thresholds','entry_id':self.entry.entry_id,'expected_policy_revision':1,'thresholds':{key:policy[key] for key in mapping}})
        await self.hass.async_block_till_done()
        self.assert_values(mapping,policy)
        self.assertEqual(len(self.saved),2)
        self.assertEqual(replies[0][1]['threshold_entities'],mapping)

    async def test_real_verified_store_native_write_and_failure_rollback(self):
        from homeassistant.helpers.storage import Store
        from homeassistant.exceptions import HomeAssistantError
        from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
        mapping=await self.setup_helpers()
        before=self.group.registry.payload()
        store=Store(self.hass,1,DOMAIN+'.'+self.entry.entry_id,atomic_writes=True)
        await store.async_save(before)
        persistence=VerifiedStore(self.hass,store,before,self.group.stop)
        self.group.registry._save=persistence.save
        original=persistence._transaction
        entered,release=asyncio.Event(),asyncio.Event()
        async def paused(payload):
            entered.set();await release.wait();await original(payload)
        with patch.object(persistence,'_transaction',paused):
            operation=asyncio.create_task(self.call(mapping,'temperature_on',35))
            await asyncio.wait_for(entered.wait(),5)
            self.assert_values(mapping,before['policy'])
            release.set();await operation
        committed=self.group.registry.payload()
        self.assertEqual(await Store(self.hass,1,store.key).async_load(),committed)
        with patch.object(Store,'async_save',new=AsyncMock()):
            with self.assertRaises(HomeAssistantError): await self.call(mapping,'humidity_on',99)
        self.assertEqual(self.group.registry.payload(),committed)
        self.assert_values(mapping,committed['policy'])
        self.assertEqual(await Store(self.hass,1,store.key).async_load(),committed)

    async def test_real_store_quarantine_makes_helpers_unavailable_and_keeps_old_policy(self):
        from homeassistant.helpers.storage import Store
        from homeassistant.exceptions import HomeAssistantError
        from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
        mapping=await self.setup_helpers();before=self.group.registry.payload()
        store=Store(self.hass,1,DOMAIN+'.'+self.entry.entry_id,atomic_writes=True)
        await store.async_save(before)
        persistence=VerifiedStore(self.hass,store,before,self.group.stop)
        self.group.registry._save=persistence.save
        with patch.object(persistence,'_verify',new=AsyncMock(side_effect=OSError('read failure'))):
            with self.assertRaises(HomeAssistantError): await self.call(mapping,'temperature_on',35)
        self.assertFalse(self.group.active)
        self.assertEqual(self.group.registry.policy,before['policy'])
        self.assertTrue(persistence.pending.exists())
        for identity in mapping.values(): self.assertEqual(self.hass.states.get(identity).state,'unavailable')

    async def test_delete_drains_inflight_and_queued_services_cannot_republish(self):
        from custom_components.uninus_greenhouse_fan import async_remove_entry
        from homeassistant.exceptions import HomeAssistantError
        mapping=await self.setup_helpers()
        entered,release=asyncio.Event(),asyncio.Event()
        async def slow(payload): entered.set();await release.wait();self.saved.append(payload)
        self.group.registry._save=slow
        first=asyncio.create_task(self.call(mapping,'temperature_on',35))
        await asyncio.wait_for(entered.wait(),5)
        queued=asyncio.create_task(self.call(mapping,'humidity_on',99));await asyncio.sleep(0)
        removal=asyncio.create_task(async_remove_entry(self.hass,self.entry));await asyncio.sleep(0)
        self.assertFalse(self.group.active)
        self.assertFalse(removal.done())
        release.set()
        for task in (first,queued):
            with self.assertRaises(HomeAssistantError): await task
        await removal;await self.hass.async_block_till_done()
        self.assertEqual(len(self.saved),1)
        for identity in mapping.values():
            self.assertIsNone(self.hass.states.get(identity))
            self.assertIsNone(er.async_get(self.hass).async_get(identity))

    async def test_native_new_group_flow_then_manager_remove_cleans_helpers(self):
        import types
        from homeassistant.config_entries import ConfigEntryState
        from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanConfigFlow
        import custom_components.uninus_greenhouse_fan as integration
        unrelated=input_number.InputNumber.from_storage({'id':'user-helper','name':'Unrelated','initial':4,'min':0,'max':10,'step':1,'mode':'slider'})
        from homeassistant.helpers.entity_component import DATA_INSTANCES
        await self.hass.data[DATA_INSTANCES]['input_number'].async_add_entities([unrelated])
        manager=self.hass.config_entries
        async def setup(entry_id):
            entry=manager.async_get_entry(entry_id)
            await integration.async_setup_entry(self.hass,entry)
            entry._async_set_state(self.hass,ConfigEntryState.LOADED,None)
            object.__setattr__(entry,'_integration_for_domain',types.SimpleNamespace(domain=DOMAIN,async_get_component=AsyncMock(return_value=integration)))
            return True
        # Only loader/setup routing is substituted; native FlowManager, entries,
        # EntityPlatform, EntityRegistry, ServiceRegistry and deletion are real.
        with patch('homeassistant.config_entries._support_single_config_entry_only',new=AsyncMock(return_value=False)), patch('homeassistant.config_entries._async_get_flow_handler',new=AsyncMock(return_value=GreenhouseFanConfigFlow)), patch.object(ConfigEntries,'async_setup',new=lambda manager,entry_id:setup(entry_id)), patch('custom_components.uninus_greenhouse_fan.frontend.async_ensure_card_resource',new=AsyncMock()):
            result=await manager.flow.async_init(DOMAIN,context={'source':'user'})
            result=await manager.flow.async_configure(result['flow_id'],{'name':'New native group',**self.group.registry.policy})
            self.assertEqual(result['type'],'create_entry')
            entry=result['result']
            await self.hass.async_block_till_done()
            created=self.hass.data[DOMAIN][entry.entry_id]
            mapping=created.snapshot()['threshold_entities']
            self.assertEqual(len(mapping),4)
            removed=await manager.async_remove(entry.entry_id)
            self.assertFalse(removed['require_restart'])
            await self.hass.async_block_till_done()
            for identity in mapping.values():
                self.assertIsNone(er.async_get(self.hass).async_get(identity))
                self.assertIsNone(self.hass.states.get(identity))
        self.assertEqual(self.hass.states.get(unrelated.entity_id).state,'4')
        self.assertIsNotNone(er.async_get(self.hass).async_get(unrelated.entity_id))

    async def test_threshold_options_information_uses_current_renamed_ids(self):
        mapping=await self.setup_helpers()
        registry=er.async_get(self.hass)
        registry.async_update_entity(mapping['temperature_on'],new_entity_id='input_number.renamed',name='My threshold')
        await self.hass.async_block_till_done()
        from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanOptionsFlow
        flow=GreenhouseFanOptionsFlow(self.entry);flow.hass=self.hass
        menu=await flow.async_step_init()
        self.assertIn('threshold_entities',menu['menu_options'])
        result=await flow.async_step_threshold_entities()
        text=result['description_placeholders']['entities']
        self.assertIn('My threshold (input_number.renamed)',text)
        self.assertEqual(len(result['data_schema'].schema),0)
        self.assertEqual(self.saved,[])

    async def test_legacy_extended_bounds_allow_decrement_then_increment_without_shrinking(self):
        self.group.registry.policy={**self.group.registry.policy,'temperature_on':80,'temperature_off':-20}
        from custom_components.uninus_greenhouse_fan.controller import Policy
        self.group.controller.set_policy(Policy(**self.group.registry.policy))
        mapping=await self.setup_helpers()
        await self.call(mapping,'temperature_on',service='decrement')
        await self.call(mapping,'temperature_on',service='increment')
        self.assertEqual(self.group.registry.policy['temperature_on'],80)
        await self.call(mapping,'temperature_off',service='increment')
        await self.call(mapping,'temperature_off',service='decrement')
        self.assertEqual(self.group.registry.policy['temperature_off'],-20)

    async def test_legacy_policy_extended_bounds_and_initial_saved_authority(self):
        self.group.registry.policy={**self.group.registry.policy,'temperature_on':80,'temperature_off':-20}
        self.group.controller.set_policy(__import__('custom_components.uninus_greenhouse_fan.controller',fromlist=['Policy']).Policy(**self.group.registry.policy))
        mapping=await self.setup_helpers()
        self.assertEqual(self.hass.states.get(mapping['temperature_on']).attributes['max'],80)
        self.assertEqual(self.hass.states.get(mapping['temperature_off']).attributes['min'],-20)
        self.assert_values(mapping,self.group.registry.policy)

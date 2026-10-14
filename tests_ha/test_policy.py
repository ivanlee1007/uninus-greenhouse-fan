"""Authoritative shared policy: isolated real HA, never live hardware."""
import unittest
from copy import deepcopy
from unittest.mock import patch
import test_options
from custom_components.uninus_greenhouse_fan import FanGroup
from custom_components.uninus_greenhouse_fan.const import DOMAIN
from custom_components.uninus_greenhouse_fan.registry import Registry, Conflict

class PolicyTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_options.OptionsTest.asyncSetUp
    asyncTearDown = test_options.OptionsTest.asyncTearDown

    async def test_native_schema_rejects_boolean_nonfinite_and_fractional_duration(self):
        import voluptuous as vol
        from custom_components.uninus_greenhouse_fan.config_flow import policy_schema
        schema = policy_schema(self.group.snapshot()['policy'])
        for field, value in [('temperature_on', True), ('humidity_on', float('nan')), ('duration_seconds', True), ('duration_seconds', 1.5)]:
            with self.assertRaises(vol.Invalid): schema({field:value})

    async def test_malformed_canonical_policy_never_falls_back_to_stale_options(self):
        before=self.group.registry.payload()
        for invalid in (None, {}, {**before['policy'],'temperature_on':True}, {**before['policy'],'temperature_on':float('nan')}):
            with self.assertRaises((ValueError,TypeError)):
                FanGroup(self.hass,self.entry,Registry(self.entry.entry_id,{**before,'policy':invalid},self.group.registry._save))
        self.assertEqual(self.saved,[])

    async def test_registry_rejects_invalid_policy_before_any_write(self):
        before = self.group.registry.payload()
        for values in ({}, {**before['policy'], 'temperature_on': True}, {**before['policy'], 'humidity_on': 101}, {**before['policy'], 'extra': 1}):
            with self.assertRaises((TypeError, ValueError)):
                await self.group.registry.set_policy(values, 0)
        self.assertEqual(self.group.registry.payload(), before)
        self.assertEqual(self.saved, [])

    async def test_ws_native_admin_strict_schema_conflict_and_zero_services(self):
        import types
        import voluptuous as vol
        from homeassistant.exceptions import Unauthorized
        from unittest.mock import AsyncMock
        from custom_components.uninus_greenhouse_fan import websocket as ws
        self.assertTrue(hasattr(ws, 'ws_save_thresholds'))
        replies = []
        connection = types.SimpleNamespace(user=types.SimpleNamespace(is_admin=False), send_result=lambda *a: replies.append(('result', a)), send_error=lambda *a: replies.append(('error', a)))
        thresholds = {k:v for k,v in self.group.snapshot()['policy'].items() if k != 'duration_seconds'}
        thresholds['temperature_on'] = 35
        msg = {'id':1, 'type':DOMAIN+'/save_thresholds', 'entry_id':self.entry.entry_id, 'expected_policy_revision':0, 'thresholds':thresholds}
        with self.assertRaises(Unauthorized): ws.ws_save_thresholds(self.hass, connection, msg)
        connection.user.is_admin = True
        with patch.object(type(self.hass.services), 'async_call', new=AsyncMock()) as calls:
            ws.ws_save_thresholds(self.hass, connection, ws.ws_save_thresholds._ws_schema(msg))
            await self.hass.async_block_till_done()
            self.assertEqual(replies[-1][0], 'result')
            self.assertEqual(self.group.snapshot()['policy']['temperature_on'], 35)
            self.assertEqual(self.group.snapshot()['policy']['duration_seconds'], 120)
            ws.ws_save_thresholds(self.hass, connection, msg)
            await self.hass.async_block_till_done()
            self.assertEqual(replies[-1][1][1], 'conflict')
            for value in (True, None, '35', float('nan'), float('inf')):
                with self.assertRaises(vol.Invalid): ws.ws_save_thresholds._ws_schema({**msg, 'thresholds':{**thresholds, 'temperature_on':value}})
            for changes in ({'extra':1}, {'duration_seconds':10}):
                with self.assertRaises(vol.Invalid): ws.ws_save_thresholds._ws_schema({**msg, 'thresholds':{**thresholds, **changes}})
            with self.assertRaises(vol.Invalid): ws.ws_save_thresholds._ws_schema({**msg, 'expected_policy_revision':True})
            invalid = {**msg, 'expected_policy_revision':1, 'thresholds':{**thresholds, 'humidity_on':101}}
            ws.ws_save_thresholds(self.hass, connection, invalid)
            await self.hass.async_block_till_done()
            self.assertEqual(replies[-1][1][1], 'invalid_policy')
            ws.ws_save_thresholds(self.hass, connection, {**msg, 'entry_id':'missing'})
            await self.hass.async_block_till_done()
            self.assertEqual(replies[-1][1][1], 'not_found')
            calls.assert_not_awaited()

    async def test_policy_equal_thresholds_are_valid_native_range_not_demo_range(self):
        from custom_components.uninus_greenhouse_fan.controller import Policy
        self.assertEqual(Policy(80, -20, 100, 0, 120).temperature_on, 80)
        self.assertEqual(Policy(30, 30, 80, 80, 120).temperature_off, 30)

    async def test_native_options_manager_roundtrip_same_policy_and_cancel(self):
        from homeassistant.config_entries import ConfigEntries
        from custom_components.uninus_greenhouse_fan.config_flow import GreenhouseFanConfigFlow
        from unittest.mock import AsyncMock
        manager = ConfigEntries(self.hass, {})
        manager._entries[self.entry.entry_id] = self.entry
        self.hass.config_entries = manager
        await self.group.save_device(None, self.record)
        actual_calls=[]
        async def actuator(call): actual_calls.append((call.domain,call.service,dict(call.data)))
        self.hass.services.async_register('fan','turn_on',actuator)
        self.hass.services.async_register('fan','turn_off',actuator)
        current = {**self.group.snapshot()['policy'], 'temperature_on': 38}
        await self.group.save_policy(current, 0)
        saved_count=len(self.saved)
        with patch('homeassistant.config_entries._async_get_flow_handler', new=AsyncMock(return_value=GreenhouseFanConfigFlow)):
            result = await manager.options.async_init(self.entry.entry_id)
            result = await manager.options.async_configure(result['flow_id'], {'next_step_id':'policy'})
            self.assertEqual(result['data_schema']({}), current)
            manager.options.async_abort(result['flow_id'])
            self.assertEqual(len(self.saved), saved_count)
            result = await manager.options.async_init(self.entry.entry_id)
            result = await manager.options.async_configure(result['flow_id'], {'next_step_id':'policy'})
            concurrent={**current,'humidity_on':96}
            await self.group.save_policy(concurrent,1)
            conflict=await manager.options.async_configure(result['flow_id'],{**current,'temperature_on':39})
            self.assertEqual(conflict['errors'],{'base':'conflict'})
            self.assertEqual(conflict['data_schema']({})['temperature_on'],39)
            self.assertEqual(self.group.snapshot()['policy'],concurrent)
            manager.options.async_abort(conflict['flow_id'])
            result = await manager.options.async_init(self.entry.entry_id)
            result = await manager.options.async_configure(result['flow_id'], {'next_step_id':'policy'})
            edited = {**current, 'humidity_on': 95, 'duration_seconds': 17}
            result = await manager.options.async_configure(result['flow_id'], edited)
            self.assertEqual(result['type'], 'create_entry')
            self.assertEqual(self.group.snapshot()['policy'], edited)
            result = await manager.options.async_init(self.entry.entry_id)
            result = await manager.options.async_configure(result['flow_id'], {'next_step_id':'policy'})
            self.assertEqual(result['data_schema']({}), edited)
            manager.options.async_abort(result['flow_id'])
        await self.group._options_updated(self.hass, self.entry)
        self.assertEqual(self.group.snapshot()['policy'], edited)
        self.assertEqual(actual_calls,[])

    async def test_policy_transaction_full_record_independent_revision_reload(self):
        await self.group.save_device(None, self.record)
        await self.group.registry.set_mode('fan.a', 'off')
        self.group.controller.set_mode('fan.a', 'off')
        before = self.group.registry.payload()
        policy = {**self.group.snapshot()['policy'], 'temperature_on': 35}
        result = await self.group.save_policy(policy, 0)
        self.assertEqual(result['policy_revision'], 1)
        self.assertEqual(result['policy'], policy)
        self.assertEqual(self.saved[-1]['policy'], policy)
        self.assertEqual(self.saved[-1]['manual_modes'], before['manual_modes'])
        self.assertEqual(self.saved[-1]['devices'], before['devices'])
        await self.group.registry.set_control_mode('manual')
        await self.group.registry.save_device(None, {'name':'B', 'fan_entity':'switch.b'})
        self.assertEqual(self.saved[-1]['policy'], policy)
        self.assertEqual(self.saved[-1]['policy_revision'], 1)
        self.assertGreater(self.saved[-1]['revision'], before['revision'])
        restored = FanGroup(self.hass, self.entry, Registry(self.entry.entry_id, self.saved[-1], self.group.registry._save))
        self.assertEqual(restored.snapshot()['policy'], policy)
        self.assertEqual(restored.snapshot()['control_mode'], 'manual')
        with self.assertRaises(Conflict): await self.group.save_policy(policy, 0)

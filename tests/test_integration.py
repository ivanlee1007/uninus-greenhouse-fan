"""Exercise the real integration adapter with explicit HA fakes, never real devices."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components/uninus_greenhouse_fan'

def module(name, **attributes):
    target=types.ModuleType(name)
    for key,value in attributes.items():setattr(target,key,value)
    sys.modules[name]=target
    return target

module('homeassistant')
module('homeassistant.config_entries',ConfigEntry=type('ConfigEntry',(),{}))
module('homeassistant.core',HomeAssistant=type('HomeAssistant',(),{}),callback=lambda f:f)
module('homeassistant.helpers')
listeners=[]
def track(hass, callback, interval):
    listeners.append(callback)
    return lambda:listeners.remove(callback)
module('homeassistant.helpers.event',async_track_time_interval=track)
class FakeStore:
    records={}
    def __init__(self,hass,version,key, *, atomic_writes=False):
        self.key=key
        self.atomic_writes=atomic_writes
    async def async_load(self):return self.records.get(self.key)
    async def async_save(self,data):self.records[self.key]=data
module('homeassistant.helpers.storage',Store=FakeStore)
module('homeassistant.components')
class StaticPathConfig:
    def __init__(self,path,file_path,cache_headers):self.path=path;self.file_path=file_path;self.cache_headers=cache_headers
module('homeassistant.components.http',StaticPathConfig=StaticPathConfig)
module('homeassistant.components.lovelace')
module('homeassistant.components.lovelace.const',LOVELACE_DATA='lovelace',MODE_YAML='yaml')
commands=[]
class Decorator:
    @staticmethod
    def websocket_command(schema):
        def wrap(f):f._ws_command=schema['type'];return f
        return wrap
    @staticmethod
    def async_register_command(hass,f):commands.append(f)
    @staticmethod
    def require_admin(f):return f
    @staticmethod
    def async_response(f):return f
    ActiveConnection=type('ActiveConnection',(),{})
module('homeassistant.components.websocket_api',websocket_command=Decorator.websocket_command,async_register_command=Decorator.async_register_command,require_admin=Decorator.require_admin,async_response=Decorator.async_response,ActiveConnection=Decorator.ActiveConnection)
module('voluptuous',Required=lambda x:x,Schema=lambda x:x,All=lambda *args:args,Range=lambda **kwargs:kwargs,In=lambda x:x)
package='custom_components.uninus_greenhouse_fan'
# Explicit bypass: legacy fakes do not provide native helper coverage.
async def bypass_native_helpers(group):
    return None
module(package+'.threshold_helpers', async_setup_helpers=bypass_native_helpers)
module('custom_components').__path__=[str(ROOT.parent)]
spec=importlib.util.spec_from_file_location(package,ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
app=importlib.util.module_from_spec(spec);sys.modules[package]=app;spec.loader.exec_module(app)

class Entity:
    def __init__(self,id,value,unit=None,device_class=None):
        self.entity_id=id;self.state=value;self.attributes={'unit_of_measurement':unit,'device_class':device_class}

class FakeServices:
    def __init__(self,hass):self.hass=hass;self.calls=[]
    async def async_call(self,domain,service,data,blocking):
        self.calls.append((domain,service,dict(data),blocking))
        self.hass.states[data['entity_id']].state='on' if service=='turn_on' else 'off'

class FakeHass:
    def __init__(self):
        class ResourceCollection:
            def __init__(self):self.items=[]
            async def async_get_info(self):return {'resources':len(self.items)}
            def async_items(self):return self.items
            async def async_create_item(self,data):self.items.append({'id':str(len(self.items)+1),'type':data['res_type'],'url':data['url']})
            async def async_update_item(self,id,data):
                row=next(x for x in self.items if x['id']==id)
                row.update({'type':data['res_type'],'url':data['url']})
        class Http:
            def __init__(self):self.paths=[]
            async def async_register_static_paths(self,paths):self.paths.extend(paths)
        self.http=Http();self.resources=ResourceCollection()
        self.data={'lovelace':types.SimpleNamespace(resource_mode='storage',resources=self.resources)};self.states={
            'fan.a':Entity('fan.a','off'),
            'switch.a':Entity('switch.a','off'),
            'sensor.t':Entity('sensor.t','32','°C','temperature'),
            'sensor.h':Entity('sensor.h','65','%','humidity'),
        };self.services=FakeServices(self)
    def async_create_task(self,coroutine):return asyncio.create_task(coroutine)

class FakeEntry:
    def __init__(self):self.entry_id='entry-a';self.domain=app.DOMAIN;self.title='A';self.data={'name':'A'};self.options={};self.update_listeners=[]
    def add_update_listener(self,callback):
        self.update_listeners.append(callback)
        return lambda:self.update_listeners.remove(callback)

class IntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeStore.records={};commands.clear();listeners.clear()
        self.hass=FakeHass();self.entry=FakeEntry()
        self.entries=[self.entry]
        self.hass.config_entries=types.SimpleNamespace(async_entries=lambda domain:self.entries)
        FakeStore.records[f'{app.DOMAIN}.entry-a'] = {'revision':0, 'bindings':{}, 'manual_modes':{}, 'devices':{fan:{'device_id':fan,'name':fan,'fan_entity':fan,'temperature_entity':'','humidity_entity':''} for fan in ('fan.a','switch.a')}}
        self.assertTrue(await app.async_setup_entry(self.hass,self.entry))
        self.group=self.hass.data[app.DOMAIN][self.entry.entry_id]

    async def asyncTearDown(self):
        await app.async_unload_entry(self.hass,self.entry)
        self.assertEqual(listeners,[])

    async def test_global_manual_gate_hidden_devices_reload_and_fresh_auto(self):
        await self.group.bind(0,'fan.a','sensor.t','sensor.h')
        await self.group.evaluate_all()
        self.assertEqual(self.group.snapshot()['runtime']['fan.a']['pending'],'on')
        self.hass.states['switch.a'].state='unavailable'
        await self.group.set_control_mode('manual')
        self.assertEqual(self.hass.services.calls,[])
        for row in self.group.snapshot()['runtime'].values():
            self.assertEqual(row['mode'],'manual')
            self.assertIsNone(row['pending'])
        await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls,[])
        await app.async_unload_entry(self.hass,self.entry)
        await app.async_setup_entry(self.hass,self.entry)
        self.group=self.hass.data[app.DOMAIN][self.entry.entry_id]
        self.assertEqual(self.group.snapshot()['control_mode'],'manual')
        await self.group.manual('fan.a','on')
        self.assertEqual(self.group.snapshot()['runtime']['fan.a']['mode'],'manual')
        with self.assertRaisesRegex(ValueError,'全域'):
            await self.group.manual('fan.a','auto')
        self.hass.states['fan.new']=Entity('fan.new','unknown')
        await self.group.save_device(None,{'name':'New','fan_entity':'fan.new'})
        self.assertEqual(self.group.snapshot()['runtime']['fan.new']['mode'],'manual')
        self.hass.states['fan.a'].state='off'
        before=len(self.hass.services.calls)
        await self.group.set_control_mode('auto')
        self.assertEqual(len(self.hass.services.calls),before)
        self.assertEqual(self.group.registry.manual_modes,{})
        for row in self.group.snapshot()['runtime'].values():
            self.assertEqual(row['mode'],'auto')
            self.assertIsNone(row['pending'])
        await self.group.evaluate_all()
        self.assertEqual(self.group.snapshot()['runtime']['fan.a']['pending'],'on')
        self.assertEqual(len(self.hass.services.calls),before)

    async def test_unbound_manual_outputs_persist_reload_and_resume_without_actuation(self):
        for fan in ('fan.a', 'switch.a'):
            for mode in ('on', 'off'):
                result = await self.group.manual(fan, mode)
                self.assertEqual(result['bindings'], {})
                self.assertEqual(result['runtime'][fan]['mode'], mode)
                self.assertEqual(self.hass.services.calls[-1], (fan.split('.')[0], 'turn_'+mode, {'entity_id':fan}, True))
            await app.async_unload_entry(self.hass, self.entry)
            await app.async_setup_entry(self.hass, self.entry)
            self.group = self.hass.data[app.DOMAIN][self.entry.entry_id]
            self.assertEqual(self.group.snapshot()['runtime'][fan]['mode'], 'off')
            before = len(self.hass.services.calls)
            await self.group.evaluate_all()
            result = await self.group.manual(fan, 'auto')
            self.assertEqual(result['runtime'][fan]['mode'], 'auto')
            self.assertEqual(result['runtime'][fan]['reason'], 'unbound')
            await self.group.evaluate_all()
            self.assertEqual(len(self.hass.services.calls), before)
            self.assertNotIn(fan, self.group.registry.manual_modes)

    async def test_manual_rejects_invalid_missing_unavailable_outputs_without_save(self):
        for fan, mode in [('sensor.t','on'), ('light.a','off'), ('fan.missing','on'), ('fan.','on'), ('switch.a','bad'), ('fan.a','ON')]:
            with self.subTest(fan=fan, mode=mode), self.assertRaises(ValueError):
                await self.group.manual(fan, mode)
        for value in ('unavailable', 'invalid'):
            self.hass.states['fan.a'].state = value
            with self.assertRaises(ValueError):
                await self.group.manual('fan.a', 'on')
        self.assertEqual(self.group.registry.revision, 0)
        self.assertEqual(self.hass.services.calls, [])

    async def test_manual_unbound_uses_no_sensor_data_and_failed_service_keeps_hold(self):
        self.hass.states.pop('sensor.t')
        self.hass.states['sensor.h'].state = 'unavailable'
        async def fail(*args, **kwargs):
            raise RuntimeError('device offline')
        self.hass.services.async_call = fail
        with self.assertRaises(RuntimeError):
            await self.group.manual('switch.a', 'on')
        self.assertEqual(self.group.snapshot()['runtime']['switch.a']['mode'], 'on')
        self.assertEqual(FakeStore.records[f'{app.DOMAIN}.entry-a']['manual_modes'], {'switch.a':'on'})
        self.hass.states.pop('switch.a')
        with self.assertRaises(ValueError): await self.group.manual('switch.a', 'auto')
        self.hass.states['switch.a'] = Entity('switch.a','unknown')
        await self.group.manual('switch.a', 'auto')
        self.assertEqual(self.group.registry.manual_modes, {})

    async def test_unbound_manual_rechecks_availability_after_save(self):
        saved, finish = asyncio.Event(), asyncio.Event()
        original = self.group.registry._save
        async def paused_save(data):
            saved.set()
            await finish.wait()
            await original(data)
        self.group.registry._save = paused_save
        pending = asyncio.create_task(self.group.manual('switch.a', 'on'))
        await saved.wait()
        self.hass.states['switch.a'].state = 'unavailable'
        finish.set()
        with self.assertRaises(ValueError):
            await pending
        self.assertEqual(self.hass.services.calls, [])
        self.assertEqual(self.group.registry.manual_modes, {'switch.a':'on'})

    async def test_unbound_save_failure_never_dispatches_or_commits(self):
        async def fail(data):
            raise OSError('storage offline')
        self.group.registry._save = fail
        with self.assertRaises(OSError):
            await self.group.manual('switch.a', 'on')
        self.assertEqual(self.hass.services.calls, [])
        self.assertEqual(self.group.registry.manual_modes, {})
        self.assertEqual(self.group.registry.revision, 0)
        self.assertEqual(self.group.snapshot()['runtime']['switch.a']['mode'], 'auto')

    async def test_unbound_hold_blocks_later_binding_until_resume_and_healthy_duration(self):
        await self.group.manual('switch.a', 'off')
        await self.group.bind(1, 'switch.a', 'sensor.t', 'sensor.h')
        for now in (0, 2000):
            with patch.object(app, 'monotonic', return_value=now):
                await self.group.evaluate_all()
        self.assertEqual(len(self.hass.services.calls), 1)
        await self.group.manual('switch.a', 'auto')
        self.hass.states['sensor.t'].state = 'unavailable'
        for now in (2001, 4000):
            with patch.object(app, 'monotonic', return_value=now):
                await self.group.evaluate_all()
        self.assertEqual(len(self.hass.services.calls), 1)
        self.hass.states['sensor.t'].state = '32'
        for now in (4001, 4121):
            with patch.object(app, 'monotonic', return_value=now):
                await self.group.evaluate_all()
        self.assertEqual(len(self.hass.services.calls), 2)
        self.assertEqual(self.hass.services.calls[-1], ('switch', 'turn_on', {'entity_id':'switch.a'}, True))

    async def test_unbound_unload_during_save_keeps_hold_without_dispatch(self):
        saved, finish = asyncio.Event(), asyncio.Event()
        original = self.group.registry._save
        async def paused_save(data):
            saved.set()
            await finish.wait()
            await original(data)
        self.group.registry._save = paused_save
        pending = asyncio.create_task(self.group.manual('switch.a', 'on'))
        await saved.wait()
        unload = asyncio.create_task(app.async_unload_entry(self.hass, self.entry))
        await asyncio.sleep(0)
        self.assertFalse(self.group.active)
        self.assertFalse(unload.done())
        finish.set()
        await unload
        with self.assertRaises(ValueError):
            await pending
        self.assertEqual(self.hass.services.calls, [])
        self.assertEqual(FakeStore.records[f'{app.DOMAIN}.entry-a']['manual_modes'], {'switch.a':'on'})

    async def test_binding_failure_is_logged_and_not_misreported_as_filesystem_error(self):
        from custom_components.uninus_greenhouse_fan.websocket import ws_bind
        errors = []
        connection = types.SimpleNamespace(send_error=lambda *args:errors.append(args), send_result=lambda *args:self.fail('unexpected success'))
        async def fail(*args):
            raise TypeError('state adapter failure')
        self.group.bind = fail
        with self.assertLogs('custom_components.uninus_greenhouse_fan.websocket', level='ERROR') as logs:
            await ws_bind(self.hass, connection, {'id':1, 'entry_id':'entry-a', 'expected_revision':0, 'fan_entity':'fan.a', 'temperature_entity':'sensor.t', 'humidity_entity':'sensor.h'})
        self.assertIn('TypeError: state adapter failure', logs.output[0])
        self.assertEqual(errors[0][1], 'binding_failed')
        self.assertIn('Home Assistant', errors[0][2])
        self.assertIn('日誌', errors[0][2])
        self.assertNotIn('persist', errors[0][2])
        self.assertEqual(self.group.registry.revision, 0)

    async def test_binding_websocket_works_with_noniterable_state_machine(self):
        from custom_components.uninus_greenhouse_fan.websocket import ws_bind
        class StateMachine:
            def __init__(self, states):
                self._states = states
            def get(self, entity_id):
                return self._states.get(entity_id)
        self.hass.states = StateMachine(self.hass.states)
        results, errors = [], []
        connection = types.SimpleNamespace(send_error=lambda *args:errors.append(args), send_result=lambda id,result:results.append(result))
        await ws_bind(self.hass, connection, {'id':1, 'entry_id':'entry-a', 'expected_revision':0, 'fan_entity':'fan.a', 'temperature_entity':'sensor.t', 'humidity_entity':'sensor.h'})
        self.assertEqual(errors, [])
        self.assertEqual(results[0]['revision'], 1)
        self.assertEqual(results[0]['bindings']['fan.a'], {'temperature_entity':'sensor.t', 'humidity_entity':'sensor.h'})
        self.assertEqual(FakeStore.records[f'{app.DOMAIN}.entry-a']['revision'], 1)
        self.assertEqual(self.hass.services.calls, [])

    async def test_setup_without_loaded_entries_registers_groups_once(self):
        hass = FakeHass()
        self.assertTrue(await app.async_setup(hass, {}))
        self.assertTrue(await app.async_setup(hass, {}))
        self.assertEqual(sum(c._ws_command.endswith('/groups') for c in commands), 2)

    async def test_stale_runtime_and_unloaded_entries_cannot_dispatch(self):
        from custom_components.uninus_greenhouse_fan.websocket import ws_get, ws_manual
        await self.group.bind(0, 'fan.a', 'sensor.t', 'sensor.h')
        errors = []
        connection = types.SimpleNamespace(send_error=lambda *args:errors.append(args), send_result=lambda *args:self.fail('unexpected success'))
        self.entries.clear()
        ws_get(self.hass, connection, {'id':1, 'entry_id':'entry-a'})
        await ws_manual(self.hass, connection, {'id':2, 'entry_id':'entry-a', 'fan_entity':'fan.a', 'mode':'on'})
        self.assertEqual(len(errors), 2)
        self.assertEqual(self.hass.services.calls, [])

    async def test_empty_and_inactive_groups_are_read_only(self):
        from custom_components.uninus_greenhouse_fan.websocket import ws_groups, ws_bind
        results, errors = [], []
        connection = types.SimpleNamespace(send_result=lambda id, result:results.append(result), send_error=lambda *args:errors.append(args))
        self.entries.clear()
        ws_groups(self.hass, connection, {'id':1})
        self.assertEqual(results[-1], [])
        self.entries.append(self.entry)
        self.group.stop()
        ws_groups(self.hass, connection, {'id':2})
        self.assertEqual(results[-1], [{'entry_id':'entry-a', 'name':'A', 'loaded':False}])
        await ws_bind(self.hass, connection, {'id':3, 'entry_id':'entry-a', 'expected_revision':0, 'fan_entity':'fan.a', 'temperature_entity':'sensor.t', 'humidity_entity':'sensor.h'})
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.group.registry.revision, 0)
        self.assertEqual(self.hass.services.calls, [])

    async def test_unload_during_manual_save_never_dispatches_after_save(self):
        await self.group.bind(0, 'fan.a', 'sensor.t', 'sensor.h')
        saved, finish = asyncio.Event(), asyncio.Event()
        original = self.group.registry._save
        async def paused_save(data):
            saved.set()
            await finish.wait()
            await original(data)
        self.group.registry._save = paused_save
        pending = asyncio.create_task(self.group.manual('fan.a', 'on'))
        await saved.wait()
        unload = asyncio.create_task(app.async_unload_entry(self.hass, self.entry))
        await asyncio.sleep(0)
        self.assertFalse(self.group.active)
        self.assertFalse(unload.done())
        finish.set()
        await unload
        with self.assertRaises(ValueError):
            await pending
        self.assertEqual(self.hass.services.calls, [])

    async def test_unload_blocks_queued_manual_and_periodic_work(self):
        await self.group.bind(0, 'fan.a', 'sensor.t', 'sensor.h')
        await self.group._lock.acquire()
        pending = asyncio.create_task(self.group.manual('fan.a', 'on'))
        await asyncio.sleep(0)
        unload = asyncio.create_task(app.async_unload_entry(self.hass, self.entry))
        await asyncio.sleep(0)
        self.assertFalse(self.group.active)
        self.assertFalse(unload.done())
        self.group._lock.release()
        await unload
        with self.assertRaises(ValueError):
            await pending
        await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls, [])
        self.assertEqual(self.group.registry.manual_modes, {})

    async def test_groups_lists_only_actual_entries_with_runtime_loaded(self):
        from custom_components.uninus_greenhouse_fan.websocket import ws_groups
        other = types.SimpleNamespace(entry_id='other', domain='other', title='Other')
        unloaded = types.SimpleNamespace(entry_id='entry-b', domain=app.DOMAIN, title='B')
        self.hass.config_entries = types.SimpleNamespace(async_entries=lambda domain: [self.entry, unloaded, other])
        self.hass.data[app.DOMAIN]['ghost'] = self.group
        results = []
        connection = types.SimpleNamespace(send_result=lambda id, result: results.append(result))
        ws_groups(self.hass, connection, {'id': 1})
        self.assertEqual(results, [[{'entry_id': 'entry-a', 'name': 'A', 'loaded': True}, {'entry_id': 'entry-b', 'name': 'B', 'loaded': False}]])
        self.assertEqual(self.hass.services.calls, [])

    async def test_unbound_never_actuates_and_registers_contract(self):
        self.assertEqual([c._ws_command for c in commands],['uninus_greenhouse_fan/groups','uninus_greenhouse_fan/get','uninus_greenhouse_fan/bind','uninus_greenhouse_fan/manual','uninus_greenhouse_fan/set_control_mode','uninus_greenhouse_fan/save_thresholds'])
        self.assertEqual(self.hass.http.paths[0].path,'/uninus_greenhouse_fan/card.js')
        self.assertEqual(self.hass.resources.items[0]['url'],'/uninus_greenhouse_fan/card.js?v=0.5.6')
        self.assertEqual(self.hass.resources.items[0]['type'],'module')
        with patch.object(app,'monotonic',return_value=5000):await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls,[])
        self.assertEqual(self.group.snapshot()['bindings'],{})

    async def test_binding_controls_same_source_and_respects_duration_on_periodic_ticks(self):
        result=await self.group.bind(0,'fan.a','sensor.t','sensor.h')
        self.assertEqual(result['revision'],1)
        self.assertEqual(result['bindings']['fan.a']['temperature_entity'],'sensor.t')
        with patch.object(app,'monotonic',return_value=1000):await self.group.evaluate_all()
        with patch.object(app,'monotonic',return_value=1119):await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls,[])
        with patch.object(app,'monotonic',return_value=1120):await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls,[('fan','turn_on',{'entity_id':'fan.a'},True)])
        self.assertEqual(self.hass.states['fan.a'].state,'on')
        self.assertEqual(FakeStore.records[f'{app.DOMAIN}.entry-a']['revision'],1)

    async def test_switch_relay_uses_switch_service(self):
        await self.group.bind(0,'switch.a','sensor.t','sensor.h')
        with patch.object(app,'monotonic',return_value=10):await self.group.evaluate_all()
        with patch.object(app,'monotonic',return_value=130):await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls[-1],('switch','turn_on',{'entity_id':'switch.a'},True))

    async def test_unavailable_and_wrong_unit_reset_timer(self):
        await self.group.bind(0,'fan.a','sensor.t','sensor.h')
        with patch.object(app,'monotonic',return_value=0):await self.group.evaluate_all()
        self.hass.states['sensor.t'].attributes['unit_of_measurement']='°F'
        with patch.object(app,'monotonic',return_value=130):await self.group.evaluate_all()
        self.hass.states['sensor.t'].attributes['unit_of_measurement']='°C'
        with patch.object(app,'monotonic',return_value=131):await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls,[])
        with patch.object(app,'monotonic',return_value=251):await self.group.evaluate_all()
        self.assertEqual(len(self.hass.services.calls),1)

    async def test_manual_hold_until_resume_and_binding_conflict(self):
        await self.group.bind(0,'fan.a','sensor.t','sensor.h')
        from custom_components.uninus_greenhouse_fan.registry import Conflict
        with self.assertRaises(Conflict):await self.group.bind(0,'fan.a','sensor.t','sensor.h')
        await self.group.manual('fan.a','on')
        self.assertEqual(self.group.snapshot()['runtime']['fan.a']['mode'],'on')
        restored=app.FanGroup(self.hass,self.entry,app.Registry('entry-a',FakeStore.records[f'{app.DOMAIN}.entry-a'],FakeStore(self.hass,1,f'{app.DOMAIN}.entry-a').async_save))
        self.assertEqual(restored.snapshot()['runtime']['fan.a']['mode'],'on')
        self.hass.states['sensor.t'].state='10';self.hass.states['sensor.h'].state='10'
        with patch.object(app,'monotonic',return_value=1000):await self.group.evaluate_all()
        with patch.object(app,'monotonic',return_value=2000):await self.group.evaluate_all()
        self.assertEqual(len(self.hass.services.calls),1)
        await self.group.manual('fan.a','auto')
        with patch.object(app,'monotonic',return_value=2001):await self.group.evaluate_all()
        with patch.object(app,'monotonic',return_value=2121):await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls[-1][1],'turn_off')

    async def test_bind_rejects_semantically_wrong_source_and_policy_resets_timer(self):
        self.hass.states['sensor.t'].attributes['unit_of_measurement']='°F'
        with self.assertRaises(ValueError):await self.group.bind(0,'fan.a','sensor.t','sensor.h')
        self.hass.states['sensor.t'].attributes['unit_of_measurement']='°C'
        await self.group.bind(0,'fan.a','sensor.t','sensor.h')
        with patch.object(app,'monotonic',return_value=0):await self.group.evaluate_all()
        await self.group.save_policy({**self.group.snapshot()['policy'], 'duration_seconds':60}, 0)
        with patch.object(app,'monotonic',return_value=120):await self.group.evaluate_all()
        self.assertEqual(self.hass.services.calls,[])
        with patch.object(app,'monotonic',return_value=180):await self.group.evaluate_all()
        self.assertEqual(len(self.hass.services.calls),1)

if __name__=='__main__':unittest.main()

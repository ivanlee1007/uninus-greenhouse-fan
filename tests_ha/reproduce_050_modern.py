"""Intentional RED: execute the unmodified 0.5.0 adapter against real modern HA.

Isolated actual Store/journal, no live HA, no fake InputNumber. Detached entities
avoid the separate new Entity.group deprecation so the reported publication
root cause can be exercised directly. Requires baseline commit 411fce8.
"""
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.components.input_number import InputNumber
from custom_components.uninus_greenhouse_fan.const import DOMAIN
from custom_components.uninus_greenhouse_fan.registry import Registry
from custom_components.uninus_greenhouse_fan.persistence import VerifiedStore
from custom_components.uninus_greenhouse_fan.controller import Policy


def baseline_module(name, filename):
    source = subprocess.check_output(['git','show',f'411fce8:custom_components/{DOMAIN}/{filename}'])
    module = types.ModuleType(f'custom_components.{DOMAIN}.{name}')
    module.__package__ = f'custom_components.{DOMAIN}'
    exec(compile(source, f'baseline-411fce8/{filename}', 'exec'), module.__dict__)
    return module


async def reproduce():
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as directory:
        hass = HomeAssistant(directory)
        hass.config_entries = ConfigEntries(hass,{})
        dr.async_setup(hass)
        await dr.async_load(hass)
        await er.async_load(hass)
        loader.async_setup(hass)
        import shutil
        shutil.copytree(Path(__file__).resolve().parents[1]/'custom_components',Path(directory)/'custom_components')
        await loader.async_get_integration(hass,DOMAIN)
        group_module = baseline_module('baseline_group','__init__.py')
        helper_module = baseline_module('baseline_helpers','threshold_helpers.py')
        entry = ConfigEntry(domain=DOMAIN,title='Baseline',data={},options={},source='user',version=1,minor_version=1,unique_id=None,discovery_keys={},subentries_data=[])
        group = group_module.FanGroup(hass,entry,Registry(entry.entry_id,{},None))
        policy = {**group.registry.policy,'temperature_on':35.2,'temperature_off':25.1,'humidity_on':93.4,'humidity_off':72.7}
        group.registry.policy = policy
        group.controller.set_policy(Policy(**policy))
        group.threshold_helpers = helper_module.ThresholdHelpers(group)
        store = Store(hass,1,DOMAIN+'.'+entry.entry_id,atomic_writes=True)
        before = group.registry.payload()
        await store.async_save(before)
        persistence = VerifiedStore(hass,store,before,group.stop)
        group.registry._save = persistence.save
        try:
            await group.save_thresholds({key:(88.1 if key=='humidity_on' else policy[key]) for key in helper_module.KEYS},0)
        except AttributeError:
            disk = await Store(hass,1,store.key).async_load()
            print(json.dumps({'baseline':'411fce8','actual_input_number_source_sha256':hashlib.sha256(Path(inspect.getfile(InputNumber)).read_bytes()).hexdigest(),'durably_saved_humidity_on':disk['policy']['humidity_on'],'durably_saved_policy_revision':disk['policy_revision'],'runtime_helper_humidity_on':group.threshold_helpers.entities['humidity_on'].native_value}),flush=True)
            assert disk['policy']['humidity_on']==88.1 and disk['policy_revision']==1
            raise
        finally:
            await group.threshold_helpers.async_unload()
            await hass.async_stop()


if __name__=='__main__':
    asyncio.run(reproduce())

"""Native group policy and integration-owned device Options forms."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig, SelectSelector, SelectSelectorConfig

from .registry import Conflict
from .persistence import StorageQuarantined

from .controller import Policy
from .const import DOMAIN, DEFAULT_POLICY, POLICY_KEYS

_LOGGER = logging.getLogger(__name__)


def policy_schema(current):
    return vol.Schema({
        vol.Required('temperature_on', default=current['temperature_on']): vol.Coerce(float),
        vol.Required('temperature_off', default=current['temperature_off']): vol.Coerce(float),
        vol.Required('humidity_on', default=current['humidity_on']): vol.Coerce(float),
        vol.Required('humidity_off', default=current['humidity_off']): vol.Coerce(float),
        vol.Required('duration_seconds', default=current['duration_seconds']): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
    })


class GreenhouseFanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            try:
                name = user_input['name'].strip()
                if not name:
                    raise ValueError('empty name')
                Policy(**{key: user_input[key] for key in POLICY_KEYS})
            except (ValueError, KeyError, TypeError):
                errors['base'] = 'invalid_policy'
            else:
                return self.async_create_entry(title=name, data={'name': name, **{key: user_input[key] for key in POLICY_KEYS}})
        schema = policy_schema(DEFAULT_POLICY).extend({vol.Required('name', default='Greenhouse fans'): str})
        return self.async_show_form(step_id='user', data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return GreenhouseFanOptionsFlow(config_entry)


class GreenhouseFanOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._entry = config_entry
        self._device_id = None
        self._draft = {}
        self._revision = None

    def _group(self):
        group = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        return group if group and group.active else None

    async def async_step_init(self, user_input=None) -> FlowResult:
        return self.async_show_menu(step_id='init', menu_options=['devices', 'add_device', 'edit_device', 'remove_device', 'policy'])

    async def async_step_policy(self, user_input=None) -> FlowResult:
        errors = {}
        current = {key: self._entry.options.get(key, self._entry.data.get(key, DEFAULT_POLICY[key])) for key in POLICY_KEYS}
        if user_input is not None:
            current.update(user_input)
            try:
                Policy(**current)
            except (TypeError, ValueError):
                errors['base'] = 'invalid_policy'
            else:
                return self.async_create_entry(title='', data={**self._entry.options, **current})
        return self.async_show_form(step_id='policy', data_schema=policy_schema(current), errors=errors)

    async def async_step_devices(self, user_input=None):
        if user_input is not None:
            return await self.async_step_init()
        group = self._group()
        if group is None:
            return self.async_abort(reason='group_unloaded')
        names = '\n'.join(f"• {row['name']} ({row['fan_entity']})" for row in group.registry.devices.values()) or '—'
        return self.async_show_form(step_id='devices', data_schema=vol.Schema({}), description_placeholders={'devices': names})

    async def async_step_add_device(self, user_input=None):
        group = self._group()
        if group is None:
            return self.async_abort(reason='group_unloaded')
        self._device_id, self._draft, self._revision = None, {}, group.registry.revision
        return await self.async_step_device()

    async def _select_device(self, step, user_input):
        group = self._group()
        if group is None:
            return self.async_abort(reason='group_unloaded')
        if user_input is not None:
            identity = user_input.get('device')
            row = group.registry.devices.get(identity)
            if row is None:
                return self.async_abort(reason='device_missing')
            self._device_id, self._draft, self._revision = identity, dict(row), group.registry.revision
            return await (self.async_step_device() if step == 'edit_device' else self.async_step_confirm_remove())
        options = [{'value':identity, 'label':f"{row['name']} ({row['fan_entity']})"} for identity, row in group.registry.devices.items()]
        if not options:
            return self.async_abort(reason='no_devices')
        return self.async_show_form(step_id=step, data_schema=vol.Schema({vol.Required('device'): SelectSelector(SelectSelectorConfig(options=options, mode='dropdown'))}))

    async def async_step_edit_device(self, user_input=None):
        return await self._select_device('edit_device', user_input)

    async def async_step_remove_device(self, user_input=None):
        return await self._select_device('remove_device', user_input)

    def _device_schema(self):
        draft = self._draft
        return vol.Schema({
            vol.Required('name', default=draft.get('name', '')): str,
            vol.Required('fan_entity', default=draft.get('fan_entity', '')): EntitySelector(EntitySelectorConfig(domain=['fan', 'switch'])),
            vol.Optional('temperature_entity', description={'suggested_value': draft.get('temperature_entity') or None}): EntitySelector(EntitySelectorConfig(domain='sensor', device_class='temperature')),
            vol.Optional('humidity_entity', description={'suggested_value': draft.get('humidity_entity') or None}): EntitySelector(EntitySelectorConfig(domain='sensor', device_class='humidity')),
        })

    async def async_step_device(self, user_input=None):
        group = self._group()
        if group is None:
            return self.async_abort(reason='group_unloaded')
        errors = {}
        if user_input is not None:
            self._draft = dict(user_input)
            temperature, humidity = user_input.get('temperature_entity'), user_input.get('humidity_entity')
            if bool(temperature) != bool(humidity):
                errors['humidity_entity' if temperature else 'temperature_entity'] = 'sensor_pair'
            else:
                try:
                    await group.save_device(self._device_id, user_input, self._revision)
                except Conflict:
                    errors['base'] = 'conflict'
                except ValueError as error:
                    field = str(error)
                    errors[field if field in ('name', 'fan_entity', 'temperature_entity', 'humidity_entity') else 'fan_entity' if field == 'duplicate_output' else 'base'] = 'duplicate_output' if field == 'duplicate_output' else 'ownership_unavailable' if field.startswith('Another group') else 'invalid_device'
                except StorageQuarantined:
                    errors['base'] = 'storage_quarantined'
                except Exception:
                    _LOGGER.exception('Could not save device settings for group %s', self._entry.entry_id)
                    errors['base'] = 'save_failed'
                else:
                    return self.async_create_entry(title='', data=dict(self._entry.options))
        return self.async_show_form(step_id='device', data_schema=self._device_schema(), errors=errors, last_step=True)

    async def async_step_confirm_remove(self, user_input=None):
        group = self._group()
        if group is None:
            return self.async_abort(reason='group_unloaded')
        errors = {}
        if user_input is not None:
            if not user_input.get('confirm'):
                return await self.async_step_init()
            try:
                await group.remove_device(self._device_id, self._revision)
            except Conflict:
                errors['base'] = 'conflict'
            except StorageQuarantined:
                errors['base'] = 'storage_quarantined'
            except Exception:
                _LOGGER.exception('Could not remove device for group %s', self._entry.entry_id)
                errors['base'] = 'save_failed'
            else:
                return self.async_create_entry(title='', data=dict(self._entry.options))
        return self.async_show_form(step_id='confirm_remove', data_schema=vol.Schema({vol.Required('confirm', default=False): bool}), errors=errors, description_placeholders={'name':self._draft.get('name', '')})

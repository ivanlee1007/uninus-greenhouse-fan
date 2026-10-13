"""One config entry per group; options contain shared thresholds only."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .controller import Policy
from .const import DOMAIN, DEFAULT_POLICY, POLICY_KEYS


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

    async def async_step_init(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            try:
                Policy(**user_input)
            except (TypeError, ValueError):
                errors['base'] = 'invalid_policy'
            else:
                return self.async_create_entry(title='', data=user_input)
        current = {key: self._entry.options.get(key, self._entry.data.get(key, DEFAULT_POLICY[key])) for key in POLICY_KEYS}
        return self.async_show_form(step_id='init', data_schema=policy_schema(current), errors=errors)

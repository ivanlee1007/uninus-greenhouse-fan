"""Integration-owned native input_number entities (no native helper store edits).

A dedicated public EntityPlatform joins the native component's domain entity
index, retaining HA's original entity service dispatch and permissions. Its
config_entry association and integration platform namespace protect ownership.
"""
from datetime import timedelta
import logging
from uuid import NAMESPACE_URL, uuid5

from homeassistant.components.input_number import InputNumber
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.setup import async_setup_component

from .const import DOMAIN

KEYS = ('temperature_on', 'temperature_off', 'humidity_on', 'humidity_off')
LABELS = {'temperature_on':'Temperature on', 'temperature_off':'Temperature off',
          'humidity_on':'Humidity on', 'humidity_off':'Humidity off'}
_LOGGER = logging.getLogger(__name__)


def unique_id(entry_id, key):
    """Opaque, deterministic identity independent of titles and entity IDs."""
    return uuid5(NAMESPACE_URL, f'{DOMAIN}:threshold:{entry_id}:{key}').hex


class ThresholdInputNumber(InputNumber):
    """Native slider whose mutation boundary is the group's durable policy."""
    editable = False

    def __init__(self, group, key):
        self._fan_group = group
        self.key = key
        value = group.registry.policy[key]
        temperature = key.startswith('temperature')
        super().__init__({'id':unique_id(group.entry.entry_id, key),
            'name':f'{group.entry.title} {LABELS[key]}', 'initial':value,
            'min':min(0, value) if temperature else 0,
            'max':max(50, value) if temperature else 100,
            'step':0.1, 'mode':'slider', 'unit_of_measurement':'°C' if temperature else '%'})

    @property
    def available(self):
        return self._fan_group.active

    # Define only the mutation API that this native generation dispatches.
    # Defining the legacy override on NumberEntity itself emits a HA warning.
    if hasattr(InputNumber, 'native_value'):
        async def async_set_native_value(self, value):
            await self._change(value=value)
    else:
        async def async_set_value(self, value):
            await self._change(value=value)

    @property
    def threshold_bounds(self):
        if hasattr(InputNumber, 'native_value'):
            return self.native_min_value, self.native_max_value
        return self._minimum, self._maximum

    async def async_increment(self):
        await self._change(delta=0.1)

    async def async_decrement(self):
        await self._change(delta=-0.1)

    async def _change(self, *, value=None, delta=None):
        try:
            await self._fan_group.save_helper_threshold(self.key, value=value, delta=delta)
        except (ValueError, TypeError, OSError) as error:
            raise HomeAssistantError(str(error)) from error

    def prepare(self, value):
        """Generate all adapter metadata before the durable transaction."""
        temperature = self.key.startswith('temperature')
        old_minimum, old_maximum = self.threshold_bounds
        if old_minimum > old_maximum:
            raise ValueError('Invalid native helper bounds')
        minimum, maximum = (min(old_minimum, 0, value), max(old_maximum, 50, value)) if temperature else (0, 100)
        current = self.native_value if hasattr(InputNumber, 'native_value') else self._current_value
        return minimum, maximum, (current != value or old_minimum != minimum or old_maximum != maximum)

    def publish(self, value, prepared=None):
        # Never tighten extended bounds; consume only preflight metadata when
        # publishing a committed transaction.
        minimum, maximum, changed = self.prepare(value) if prepared is None else prepared
        if hasattr(InputNumber, 'native_value'):
            self._attr_native_min_value = minimum
            self._attr_native_max_value = maximum
            self._attr_native_value = value
        else:
            self._config['min'], self._config['max'] = minimum, maximum
            self._current_value = value
        if changed and self.hass is not None and self.platform.entities.get(self.entity_id) is self:
            self.async_write_ha_state()


class ThresholdHelpers:
    def __init__(self, group):
        self._fan_group = group
        self.entities = {key:ThresholdInputNumber(group, key) for key in KEYS}
        self.platform = EntityPlatform(hass=group.hass, logger=_LOGGER, domain='input_number',
            platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
        self.platform.config_entry = group.entry
        self.platform.async_prepare()

    def mapping(self):
        registry = er.async_get(self._fan_group.hass)
        return {key:identity for key in KEYS if (identity := registry.async_get_entity_id('input_number', DOMAIN, unique_id(self._fan_group.entry.entry_id, key)))
                and registry.async_get(identity).config_entry_id == self._fan_group.entry.entry_id}

    def prepare_sync(self, policy):
        return {key:entity.prepare(policy[key]) for key, entity in self.entities.items()}

    def sync(self, prepared=None):
        for key, entity in self.entities.items():
            entity.publish(self._fan_group.registry.policy[key], None if prepared is None else prepared[key])

    def unavailable(self):
        for entity in self.entities.values():
            if entity.hass is not None and self.platform.entities.get(entity.entity_id) is entity:
                entity.async_write_ha_state()

    async def async_unload(self):
        await self.platform.async_destroy()


async def async_setup_helpers(group):
    """Create all four before timers start; abort and clean new rows on failure."""
    hass = group.hass
    if 'input_number' not in hass.data.get(DATA_INSTANCES, {}):
        if not await async_setup_component(hass, 'input_number', {}):
            raise HomeAssistantError('Could not set up native input_number')
    registry = er.async_get(hass)
    existing = set()
    for key in KEYS:
        identity = registry.async_get_entity_id('input_number', DOMAIN, unique_id(group.entry.entry_id, key))
        if identity:
            row = registry.async_get(identity)
            if row.config_entry_id != group.entry.entry_id:
                raise HomeAssistantError('Threshold unique ID belongs to another entry; refusing takeover')
            existing.add(identity)
    helpers = ThresholdHelpers(group)
    try:
        await helpers.platform.async_add_entities(helpers.entities.values())
        if len(helpers.platform.entities) != 4 or any(
            (state := hass.states.get(entity.entity_id)) is None
            or state.state in ('unavailable', 'unknown')
            or float(state.state) != group.registry.policy[key]
            for key, entity in helpers.entities.items()
        ):
            raise HomeAssistantError('Could not create all four threshold helpers')
    except BaseException:
        await helpers.async_unload()
        for key in KEYS:
            identity = registry.async_get_entity_id('input_number', DOMAIN, unique_id(group.entry.entry_id, key))
            if identity and identity not in existing and registry.async_get(identity).config_entry_id == group.entry.entry_id:
                registry.async_remove(identity)
        raise
    group.threshold_helpers = helpers


def async_remove_owned_registry(hass, entry):
    """Deletion only; reload/unload must retain entity IDs/customizations."""
    registry = er.async_get(hass)
    for key in KEYS:
        identity = registry.async_get_entity_id('input_number', DOMAIN, unique_id(entry.entry_id, key))
        if identity and registry.async_get(identity).config_entry_id == entry.entry_id:
            registry.async_remove(identity)

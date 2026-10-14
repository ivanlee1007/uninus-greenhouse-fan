"""Deterministic, side-effect-free greenhouse fan control policy."""
from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class Policy:
    temperature_on: float
    temperature_off: float
    humidity_on: float
    humidity_off: float
    duration_seconds: int

    def __post_init__(self):
        values = (self.temperature_on, self.temperature_off, self.humidity_on, self.humidity_off)
        if any(isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) for value in values):
            raise ValueError('Thresholds must be finite numbers')
        if not (-20 <= self.temperature_off < self.temperature_on <= 80):
            raise ValueError('Off thresholds must be lower than on thresholds')
        if not (0 <= self.humidity_off < self.humidity_on <= 100):
            raise ValueError('Humidity must be in [0, 100]')
        if isinstance(self.duration_seconds, bool) or not isinstance(self.duration_seconds, int) or not 0 <= self.duration_seconds <= 86400:
            raise ValueError('Duration must be an integer from 0 through 86400')

    def as_dict(self):
        return asdict(self)


class Controller:
    def __init__(self, policy: Policy):
        self.policy = policy
        self._states = {}
        self.control_mode = 'auto'

    def set_control_mode(self, mode):
        if mode not in ('auto', 'manual'):
            raise ValueError('Invalid control mode')
        self.control_mode = mode
        for fan in self._states:
            if mode == 'auto':
                self.set_mode(fan, 'auto')
            else:
                self.reset(fan)

    def _state(self, fan):
        return self._states.setdefault(fan, {'mode': 'auto', 'pending': None, 'since': None, 'reason': 'unbound'})

    def reset(self, fan):
        state = self._state(fan)
        state['pending'] = state['since'] = None

    def set_policy(self, policy):
        if policy != self.policy:
            self.policy = policy
            for fan in self._states:
                self.reset(fan)

    def set_mode(self, fan, mode):
        if mode not in ('auto', 'on', 'off'):
            raise ValueError('Invalid mode')
        state = self._state(fan)
        state['mode'] = mode
        state['reason'] = 'manual' if mode != 'auto' else 'resumed'
        self.reset(fan)

    def status(self, fan):
        state = self._state(fan)
        if self.control_mode == 'manual':
            return {'mode': 'manual', 'pending': None, 'reason': 'global_manual'}
        return {key: state[key] for key in ('mode', 'pending', 'reason')}

    def evaluate(self, fan, bound, fan_state, temperature, humidity, now):
        state = self._state(fan)
        if self.control_mode == 'manual':
            state['reason'] = 'global_manual'
            self.reset(fan)
            return None
        if state['mode'] != 'auto':
            state['reason'] = 'manual'
            self.reset(fan)
            return None
        if not bound:
            state['reason'] = 'unbound'
            self.reset(fan)
            return None
        if fan_state not in ('on', 'off'):
            state['reason'] = 'fan_unavailable'
            self.reset(fan)
            return None
        try:
            if isinstance(temperature, bool) or isinstance(humidity, bool):
                raise ValueError('Boolean reading')
            t, h = float(temperature), float(humidity)
        except (TypeError, ValueError, OverflowError):
            t = h = float('nan')
        if not isfinite(t) or not isfinite(h):
            state['reason'] = 'sensor_unavailable'
            self.reset(fan)
            return None
        policy = self.policy
        desired = ('on' if t > policy.temperature_on or h > policy.humidity_on else None) if fan_state == 'off' else ('off' if t <= policy.temperature_off and h <= policy.humidity_off else None)
        if desired is None:
            state['reason'] = 'threshold_not_met'
            self.reset(fan)
            return None
        if state['pending'] != desired:
            state['pending'], state['since'] = desired, now
        state['reason'] = 'waiting_duration'
        if now - state['since'] < policy.duration_seconds:
            return None
        self.reset(fan)
        state['reason'] = 'action_requested'
        return desired

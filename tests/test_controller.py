"""Pure policy and control tests; no HA installation required."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/uninus_greenhouse_fan'
spec = importlib.util.spec_from_file_location('fan_controller', ROOT / 'controller.py')
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Policy = module.Policy
Controller = module.Controller


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.policy = Policy(temperature_on=30, temperature_off=25, humidity_on=80, humidity_off=60, duration_seconds=120)
        self.ctl = Controller(self.policy)

    def test_unbound_or_invalid_never_acts_and_resets_pending(self):
        self.assertIsNone(self.ctl.evaluate('fan.a', False, 'off', 31, 55, 0))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 55, 0))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 'unavailable', 55, 130))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 55, 131))
        self.assertEqual(self.ctl.status('fan.a')['pending'], 'on')
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 55, 200))

    def test_on_and_off_both_wait_duration(self):
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 65, 0))
        self.assertEqual(self.ctl.evaluate('fan.a', True, 'off', 31, 65, 120), 'on')
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'on', 24, 59, 121))
        self.assertEqual(self.ctl.evaluate('fan.a', True, 'on', 24, 59, 241), 'off')

    def test_hysteresis_or_on_and_and_off(self):
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 26, 79, 0))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 29, 81, 1))
        self.assertEqual(self.ctl.evaluate('fan.a', True, 'off', 29, 81, 121), 'on')
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'on', 24, 61, 122))
        self.assertEqual(self.ctl.status('fan.a')['pending'], None)

    def test_manual_hold_and_auto_resume_reset_timer(self):
        self.ctl.evaluate('fan.a', True, 'off', 31, 40, 0)
        self.ctl.set_mode('fan.a', 'on')
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 40, 150))
        self.ctl.set_mode('fan.a', 'auto')
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 40, 151))
        self.assertEqual(self.ctl.evaluate('fan.a', True, 'off', 31, 40, 271), 'on')

    def test_policy_or_binding_change_resets_timer(self):
        self.ctl.evaluate('fan.a', True, 'off', 31, 40, 0)
        self.ctl.reset('fan.a')
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 40, 120))
        self.ctl.set_policy(Policy(30, 25, 80, 60, 60))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 40, 120))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 40, 179))
        self.assertEqual(self.ctl.evaluate('fan.a', True, 'off', 31, 40, 180), 'on')

    def test_bad_policy_and_nonfinite_readings(self):
        with self.assertRaises(ValueError):
            Policy(25, 30, 80, 60, 120)
        with self.assertRaises(ValueError):
            Policy(30, 25, 60, 80, 120)
        self.assertEqual(Policy(30, 25, 80, 60, 0).duration_seconds, 0)
        with self.assertRaises(ValueError):
            Policy(30, 25, 80, 60, -1)
        with self.assertRaises(ValueError):
            Policy(30, 25, 80, 60, 86401)
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', float('nan'), 50, 0))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'unknown', 31, 50, 200))

    def test_exact_on_threshold_does_not_start_and_zero_duration_is_immediate(self):
        instant = Controller(Policy(30, 25, 80, 60, 0))
        self.assertIsNone(instant.evaluate('fan.a', True, 'off', 30, 80, 0))
        self.assertEqual(instant.evaluate('fan.a', True, 'off', 31, 80, 1), 'on')

    def test_repeated_tick_does_not_bypass_duration_after_action(self):
        self.ctl.evaluate('fan.a', True, 'off', 31, 50, 0)
        self.assertEqual(self.ctl.evaluate('fan.a', True, 'off', 31, 50, 120), 'on')
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'off', 31, 50, 121))
        self.assertIsNone(self.ctl.evaluate('fan.a', True, 'on', 31, 50, 122))


if __name__ == '__main__':
    unittest.main()

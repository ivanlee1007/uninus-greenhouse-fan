"""Constants for the UNiNUS greenhouse fan controller."""
DOMAIN = "uninus_greenhouse_fan"
POLICY_KEYS = (
    "temperature_on", "temperature_off", "humidity_on", "humidity_off", "duration_seconds"
)
DEFAULT_POLICY = {
    "temperature_on": 29.0,
    "temperature_off": 25.0,
    "humidity_on": 93.4,
    "humidity_off": 81.0,
    "duration_seconds": 120,
}
SCAN_SECONDS = 5

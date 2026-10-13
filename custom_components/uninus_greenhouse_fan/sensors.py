"""Reject mislabeled or unavailable sensor sources before fan actions."""
from math import isfinite

UNITS = {"temperature": "°C", "humidity": "%"}


def compatible_sensor(entity, kind):
    """Check domain, declared device class (if present), and expected unit."""
    if kind not in UNITS or entity is None or not getattr(entity, "entity_id", "").startswith("sensor."):
        return False
    attrs = getattr(entity, "attributes", {})
    return attrs.get("unit_of_measurement") == UNITS[kind] and attrs.get("device_class") in (None, kind)


def safe_reading(entity, kind):
    """Return a finite reading only when source type and unit are trustworthy."""
    if not compatible_sensor(entity, kind):
        return None
    raw = getattr(entity, "state", None)
    if not isinstance(raw, str) or not raw.strip() or raw in ("unknown", "unavailable"):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if isfinite(value) else None

"""Pluggable IP -> geolocation resolver.

This is a stub: production would back `resolve` with MaxMind GeoLite2 or a paid
API. The interface is intentionally tiny so it can be swapped without touching
the impossible-travel logic. Tests inject coordinates via `set_override`.
"""

from __future__ import annotations

import ipaddress
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float
    country: str


# Test/override hook: ip -> GeoPoint. Checked before the sample table.
_OVERRIDES: dict[str, GeoPoint] = {}

# Tiny sample table so the feature is demonstrable without a geo database.
_SAMPLE: dict[str, GeoPoint] = {
    "8.8.8.8": GeoPoint(37.386, -122.084, "US"),
    "1.1.1.1": GeoPoint(-33.494, 143.210, "AU"),
    "203.0.113.7": GeoPoint(35.690, 139.692, "JP"),
}


def set_override(ip: str, point: GeoPoint | None) -> None:
    if point is None:
        _OVERRIDES.pop(ip, None)
    else:
        _OVERRIDES[ip] = point


def clear_overrides() -> None:
    _OVERRIDES.clear()


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return True


def resolve(ip: str | None) -> GeoPoint | None:
    if not ip or _is_private(ip):
        return None
    if ip in _OVERRIDES:
        return _OVERRIDES[ip]
    return _SAMPLE.get(ip)


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance in kilometers."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi = math.radians(b.lat - a.lat)
    dlmb = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))

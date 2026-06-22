"""Geodesy helpers — no external dependencies."""
from __future__ import annotations
import math


_R_NM = 3440.065   # Earth radius in nautical miles


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _R_NM * math.asin(math.sqrt(a))


def point_in_circle(
    point_lat: float,
    point_lon: float,
    center_lat: float,
    center_lon: float,
    radius_nm: float,
) -> bool:
    return haversine_nm(point_lat, point_lon, center_lat, center_lon) <= radius_nm


def bounding_box(lat: float, lon: float, radius_nm: float) -> tuple[float, float, float, float]:
    """Return (min_lat, min_lon, max_lat, max_lon) for a circle."""
    delta_lat = radius_nm / 60.0
    delta_lon = radius_nm / (60.0 * math.cos(math.radians(lat)))
    return lat - delta_lat, lon - delta_lon, lat + delta_lat, lon + delta_lon


def meters_to_nm(m: float) -> float:
    return m / 1852.0


def nm_to_ft(nm: float) -> float:
    return nm * 6076.12

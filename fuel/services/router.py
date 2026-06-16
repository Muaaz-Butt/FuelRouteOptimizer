from __future__ import annotations

import math
import requests
from typing import List, Tuple

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"


def _decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    # Decode Google encoded polyline into list of (lat, lon)
    coords: List[Tuple[float, float]] = []
    index = lat = lon = 0
    length = len(encoded)

    while index < length:
        result = 1
        shift = 0
        b = 0
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break
        lat += ~(result >> 1) if result & 1 else (result >> 1)

        result = 1
        shift = 0
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break
        lon += ~(result >> 1) if result & 1 else (result >> 1)

        coords.append((lat * 1e-5, lon * 1e-5))

    return coords


def get_route_osrm(origin: Tuple[float, float], destination: Tuple[float, float], *, timeout: float = 10.0):
    """Call OSRM route API once and return (distance_m, polyline, coords_list).

    origin and destination are (lat, lon).
    Returns (distance_meters: float, polyline: str|None, coords: list[(lat, lon)]).
    On failure, raises requests.RequestException.
    """
    lon1, lat1 = origin[1], origin[0]
    lon2, lat2 = destination[1], destination[0]
    url = f"{OSRM_URL}/{lon1},{lat1};{lon2},{lat2}"
    params = {"overview": "full", "geometries": "polyline"}
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    routes = data.get("routes") or []
    if not routes:
        raise requests.RequestException("No route returned by OSRM")
    route = routes[0]
    distance_m = float(route.get("distance", 0.0))
    poly = route.get("geometry")
    coords = _decode_polyline(poly) if poly else []
    return distance_m, poly, coords

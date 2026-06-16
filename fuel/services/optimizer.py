from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Tuple, Optional

from django.core.cache import cache

from fuel.models import Truckstop, FuelPrice
from fuel.services.router import get_route_osrm


EARTH_RADIUS_KM = 6371.0


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(x))


@dataclass
class StopEstimate:
    truckstop: Truckstop
    retail_price: float
    added_distance_km: float
    estimated_cost: float


def _get_candidates_bbox(lat: float, lon: float, radius_km: float = 50.0) -> Iterable[Truckstop]:
    # quick bbox filter to reduce DB scan
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(0.0001, math.cos(math.radians(lat))))
    return Truckstop.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=lat - lat_delta,
        latitude__lte=lat + lat_delta,
        longitude__gte=lon - lon_delta,
        longitude__lte=lon + lon_delta,
    ).prefetch_related('prices')


def _best_price_for_truckstop(ts: Truckstop) -> Optional[FuelPrice]:
    try:
        return ts.prices.order_by('retail_price').first()
    except Exception:
        return None


def optimize_route(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    *,
    mpg: float = 10.0,
    tank_range_miles: float = 500.0,
    max_results: int = 5,
    cache_ttl: int = 300,
) -> dict:
    """Compute route via OSRM (one API call), find fuel stops along the route and estimate total cost.

    Assumptions:
    - Single OSRM call per request.
    - Vehicle fuel efficiency is `mpg` (default 10 mpg).
    - Max range is `tank_range_miles` (default 500 miles).
    - If OSRM is unavailable, falls back to straight-line distance and returns no polyline.
    """
    key = f"opt_route:{origin[0]}:{origin[1]}:{destination[0]}:{destination[1]}:{mpg}:{tank_range_miles}:{max_results}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    # Try OSRM once
    try:
        distance_m, polyline, coords = get_route_osrm(origin, destination)
        route_km = distance_m / 1000.0
        route_miles = route_km / 1.609344
    except Exception:
        # fallback to direct haversine
        route_km = haversine_km(origin, destination)
        route_miles = route_km / 1.609344
        polyline = None
        coords = [origin, destination]

    # if route fits in tank, choose cheapest stop near route (optional)
    tank_range_km = tank_range_miles * 1.609344
    tank_gallons = tank_range_miles / mpg

    # sample route coords cumulative distances
    cumdist_km: List[float] = [0.0]
    for i in range(1, len(coords)):
        cumdist_km.append(cumdist_km[-1] + haversine_km(coords[i - 1], coords[i]))

    total_km = cumdist_km[-1] if cumdist_km else route_km
    total_miles = total_km / 1.609344

    # determine refuel points (distances along route in km)
    refuel_points_km: List[float] = []
    if total_miles <= tank_range_miles:
        refuel_points_km = []
    else:
        # need refuels at roughly every tank_range_miles interval
        remaining_miles = total_miles
        pos_miles = tank_range_miles
        while pos_miles < total_miles:
            refuel_points_km.append(pos_miles * 1.609344)
            pos_miles += tank_range_miles

    suggested_stops = []
    total_cost = 0.0

    def find_coord_at_km(km_pos: float) -> Tuple[float, float]:
        # find route coordinate closest to km_pos using cumulative distances
        if not cumdist_km:
            return coords[-1]
        for i in range(1, len(cumdist_km)):
            if cumdist_km[i] >= km_pos:
                return coords[i]
        return coords[-1]
    # Build route bounding box expanded by search radius and query DB once
    def route_bbox(coords_list: List[Tuple[float, float]], padding_km: float = 50.0):
        lats = [c[0] for c in coords_list]
        lons = [c[1] for c in coords_list]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        # degree deltas approximations
        lat_delta = padding_km / 111.0
        lon_delta = padding_km / (111.0 * max(0.0001, math.cos(math.radians((min_lat + max_lat) / 2.0))))
        return (min_lat - lat_delta, max_lat + lat_delta, min_lon - lon_delta, max_lon + lon_delta)

    search_radius_km = 50.0
    if coords:
        min_lat, max_lat, min_lon, max_lon = route_bbox(coords, padding_km=search_radius_km)
        candidates_qs = Truckstop.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
        ).prefetch_related('prices')
    else:
        candidates_qs = Truckstop.objects.filter(latitude__isnull=False, longitude__isnull=False).prefetch_related('prices')

    # helper: compute min distance from a truckstop to route coordinates
    def min_distance_to_route_km(ts_lat: float, ts_lon: float, route_coords: List[Tuple[float, float]]) -> float:
        if not route_coords:
            return haversine_km((ts_lat, ts_lon), destination)
        min_d = float('inf')
        for rc in route_coords:
            d = haversine_km((ts_lat, ts_lon), rc)
            if d < min_d:
                min_d = d
        return min_d

    prev_miles = 0.0
    stops_chosen = []
    for idx, km_point in enumerate(refuel_points_km):
        # segment miles from previous stop to this refuel point
        seg_miles = (km_point / 1.609344) - prev_miles
        prev_miles = km_point / 1.609344

        # find coordinate along route for this km point
        lat, lon = find_coord_at_km(km_point)

        # evaluate candidates (already bbox filtered)
        best = None
        best_cost = None
        for ts in candidates_qs:
            price_obj = _best_price_for_truckstop(ts)
            if price_obj is None:
                continue
            dist_to_route_km = min_distance_to_route_km(float(ts.latitude), float(ts.longitude), coords)
            if dist_to_route_km > search_radius_km:
                continue
            # detour assumed as round-trip from route to station
            detour_miles = (dist_to_route_km * 2.0) / 1.609344
            gallons_needed = seg_miles / mpg
            gallons_needed += detour_miles / mpg
            cost = float(price_obj.retail_price) * gallons_needed
            # prefer lower cost, and closer distance as tiebreaker
            if best is None or (cost < best_cost) or (abs(cost - best_cost) < 1e-6 and dist_to_route_km < best[2]):
                best = (ts, price_obj, dist_to_route_km)
                best_cost = cost

        if best is None:
            suggested_stops.append({
                "error": "no_candidate_near_refuel_point",
                "km_point": round(km_point, 3),
            })
            continue

        ts, price_obj, dist_to_route_km = best
        seg_miles_for_cost = seg_miles
        gallons_for_seg = seg_miles_for_cost / mpg
        detour_miles = (dist_to_route_km * 2.0) / 1.609344
        gallons_for_detour = detour_miles / mpg
        cost_here = float(price_obj.retail_price) * (gallons_for_seg + gallons_for_detour)

        suggested_stops.append(
            {
                "opis_truckstop_id": ts.opis_truckstop_id,
                "canonical_name": ts.canonical_name,
                "address": ts.address,
                "city": ts.city,
                "state": ts.state,
                "latitude": float(ts.latitude),
                "longitude": float(ts.longitude),
                "retail_price": float(price_obj.retail_price),
                "added_distance_km": round(dist_to_route_km * 2.0, 3),
                "estimated_cost": round(cost_here, 4),
            }
        )
        total_cost += cost_here
        stops_chosen.append(ts)

    # compute remaining segment (final leg) cost if any
    if total_miles > prev_miles:
        final_seg_miles = total_miles - prev_miles
        # price for final segment: assume last chosen stop or nearest to destination
        if stops_chosen:
            last_ts = stops_chosen[-1]
            last_price = _best_price_for_truckstop(last_ts)
            price_val = float(last_price.retail_price) if last_price else 0.0
        else:
            # fallback: choose nearest to destination
            lat, lon = destination
            candidates = list(_get_candidates_bbox(lat, lon, radius_km=50.0))
            price_val = 0.0
            if candidates:
                p = _best_price_for_truckstop(candidates[0])
                price_val = float(p.retail_price) if p else 0.0

        total_cost += price_val * (final_seg_miles / mpg)

    payload = {
        "origin": {"latitude": origin[0], "longitude": origin[1]},
        "destination": {"latitude": destination[0], "longitude": destination[1]},
        "route_polyline": polyline,
        "distance_miles": round(total_miles, 3),
        "suggested_stops": suggested_stops[:max_results],
        "total_money_spent": round(total_cost, 4),
    }

    cache.set(key, payload, cache_ttl)
    return payload

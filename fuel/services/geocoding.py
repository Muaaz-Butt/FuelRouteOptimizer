import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from fuel.models import GeocodeCache, GeocodeStatus, Truckstop

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "FuelRouteOptimizer/1.0 (fuel-route-assessment)"
LOW_CONFIDENCE_THRESHOLD = Decimal("0.35")


@dataclass(frozen=True)
class GeocodeResult:
    latitude: Decimal | None
    longitude: Decimal | None
    confidence: Decimal | None
    status: str
    raw_response: dict


def _get_user_agent() -> str:
    return getattr(settings, "GEOCODING_USER_AGENT", DEFAULT_USER_AGENT)


def _get_request_delay() -> float:
    return float(getattr(settings, "GEOCODING_REQUEST_DELAY", 1.1))


def _fetch_nominatim(query: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 0,
        }
    )
    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}",
        headers={"User-Agent": _get_user_agent(), "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode_query(query: str, *, use_cache: bool = True) -> tuple[GeocodeResult, bool]:
    if use_cache:
        cached = GeocodeCache.objects.filter(query=query).first()
        if cached:
            if cached.latitude is not None and cached.longitude is not None:
                status = (
                    GeocodeStatus.LOW_CONFIDENCE
                    if cached.confidence is not None and cached.confidence < LOW_CONFIDENCE_THRESHOLD
                    else GeocodeStatus.OK
                )
                return (
                    GeocodeResult(
                        latitude=cached.latitude,
                        longitude=cached.longitude,
                        confidence=cached.confidence,
                        status=status,
                        raw_response=cached.raw_response,
                    ),
                    False,
                )
            return (
                GeocodeResult(
                    latitude=None,
                    longitude=None,
                    confidence=None,
                    status=GeocodeStatus.FAILED,
                    raw_response=cached.raw_response,
                ),
                False,
            )

    try:
        results = _fetch_nominatim(query)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Geocoding request failed for %r: %s", query, exc)
        GeocodeCache.objects.update_or_create(
            query=query,
            defaults={"raw_response": {"error": str(exc)}},
        )
        return (
            GeocodeResult(
                latitude=None,
                longitude=None,
                confidence=None,
                status=GeocodeStatus.FAILED,
                raw_response={"error": str(exc)},
            ),
            True,
        )

    if not results:
        GeocodeCache.objects.update_or_create(
            query=query,
            defaults={"raw_response": {"results": []}},
        )
        return (
            GeocodeResult(
                latitude=None,
                longitude=None,
                confidence=None,
                status=GeocodeStatus.FAILED,
                raw_response={"results": []},
            ),
            True,
        )

    top = results[0]
    latitude = Decimal(str(top["lat"]))
    longitude = Decimal(str(top["lon"]))
    confidence = Decimal(str(top.get("importance", 0)))
    status = GeocodeStatus.OK
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        status = GeocodeStatus.LOW_CONFIDENCE

    GeocodeCache.objects.update_or_create(
        query=query,
        defaults={
            "latitude": latitude,
            "longitude": longitude,
            "confidence": confidence,
            "raw_response": top,
        },
    )
    return (
        GeocodeResult(
            latitude=latitude,
            longitude=longitude,
            confidence=confidence,
            status=status,
            raw_response=top,
        ),
        True,
    )


def geocode_truckstop(
    truckstop: Truckstop,
    *,
    delay: float | None = None,
    use_cache: bool = True,
) -> GeocodeResult:
    result: GeocodeResult | None = None
    sleep_for = _get_request_delay() if delay is None else delay

    for index, query in enumerate(truckstop.geocode_queries):
        candidate, called_api = geocode_query(query, use_cache=use_cache)

        if called_api and sleep_for > 0:
            time.sleep(sleep_for)

        if candidate.status == GeocodeStatus.FAILED:
            continue

        result = candidate
        if index > 0 and result.status == GeocodeStatus.OK:
            result = GeocodeResult(
                latitude=result.latitude,
                longitude=result.longitude,
                confidence=result.confidence,
                status=GeocodeStatus.LOW_CONFIDENCE,
                raw_response={**result.raw_response, "fallback_query": query},
            )
        break

    if result is None:
        result = GeocodeResult(
            latitude=None,
            longitude=None,
            confidence=None,
            status=GeocodeStatus.FAILED,
            raw_response={"queries": truckstop.geocode_queries},
        )

    truckstop.latitude = result.latitude
    truckstop.longitude = result.longitude
    truckstop.geocode_status = result.status
    truckstop.geocoded_at = timezone.now()
    truckstop.save(
        update_fields=["latitude", "longitude", "geocode_status", "geocoded_at"]
    )

    return result

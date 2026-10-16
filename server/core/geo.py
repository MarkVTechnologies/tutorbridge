"""
Address search and distances (PRD §18: "Google Maps / OpenStreetMap — address autocomplete, distance; cache results").

Provider: Google Geocoding when GOOGLE_MAPS_API_KEY is set, otherwise OpenStreetMap Nominatim
(free; its usage policy requires a descriptive User-Agent, at most 1 request/second and caching —
all handled here). Every lookup goes through the server so keys never reach browsers and
repeated searches cost nothing.
"""
import hashlib
import logging
import math
import time

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

CACHE_SECONDS = 30 * 24 * 3600
# Rough bounding box around Lagos, used to prefer (not restrict to) local results.
LAGOS_VIEWBOX = "2.70,6.80,4.35,6.35"


def haversine_km(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return None
    lat1, lng1, lat2, lng2 = (math.radians(float(v)) for v in (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def provider():
    return "google" if settings.GOOGLE_MAPS_API_KEY else settings.GEO_PROVIDER


def search(query, limit=5):
    """Return [{label, lat, lng}] for a free-text Nigerian address. Cached; empty list on provider failure."""
    q = " ".join((query or "").split())
    if len(q) < 4:
        return []
    key = "geo:" + provider() + ":" + hashlib.sha256(q.lower().encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        results = _google(q, limit) if provider() == "google" else _nominatim(q, limit) if provider() == "nominatim" else []
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("Geocoding failed for %r: %s", q, e)
        return []  # don't cache failures
    cache.set(key, results, CACHE_SECONDS)
    return results


def _nominatim_slot(timeout=3.0):
    """Global 1 request/second limit across all workers (Nominatim policy), using the shared cache as a lock."""
    deadline = time.monotonic() + timeout
    while not cache.add("geo:nominatim:slot", 1, 1):
        if time.monotonic() > deadline:
            raise requests.RequestException("Nominatim rate limit: busy")
        time.sleep(0.2)


def _nominatim(q, limit):
    _nominatim_slot()
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "format": "jsonv2", "countrycodes": "ng", "limit": limit, "viewbox": LAGOS_VIEWBOX, "addressdetails": 0},
        headers={"User-Agent": f"TutorBridge/1.0 ({settings.GEO_CONTACT_EMAIL})", "Accept-Language": "en"},
        timeout=5,
    )
    resp.raise_for_status()
    return [{"label": r["display_name"], "lat": round(float(r["lat"]), 6), "lng": round(float(r["lon"]), 6)} for r in resp.json()[:limit]]


def _google(q, limit):
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": q, "components": "country:NG", "region": "ng", "key": settings.GOOGLE_MAPS_API_KEY},
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        raise ValueError(data.get("error_message") or data.get("status"))
    return [{"label": r["formatted_address"], "lat": round(r["geometry"]["location"]["lat"], 6), "lng": round(r["geometry"]["location"]["lng"], 6)}
            for r in data.get("results", [])[:limit]]


def nearest_area(lat, lng, max_km=15):
    """The closest active neighbourhood to a point, if any is within max_km."""
    from core.models import Area

    best, best_d = None, None
    for area in Area.objects.filter(is_active=True, lat__isnull=False, lng__isnull=False):
        d = haversine_km(lat, lng, area.lat, area.lng)
        if d is not None and d <= max_km and (best_d is None or d < best_d):
            best, best_d = area, d
    return best

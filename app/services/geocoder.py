"""
Geocoder service interfacing with OpenStreetMap Nominatim API.
"""

import asyncio
import time
import logging
from typing import List
import httpx

from app.config import settings
from app.models.route_models import GeocodeResult
from app.utils.cache import geocode_cache

logger = logging.getLogger(__name__)

# Lock to enforce Nominatim 1 request per second policy across uncached requests
_nominatim_lock = asyncio.Lock()
_last_request_time = 0.0


async def geocode_location(query: str) -> List[GeocodeResult]:
    """
    Search for location coordinates using OpenStreetMap Nominatim.
    Utilizes caching, custom User-Agent, and throttling to comply with usage policies.
    """
    query_clean = query.strip()
    if not query_clean:
        return []

    cache_key = f"geocode:{query_clean.lower()}"
    cached_res = geocode_cache.get(cache_key)
    if cached_res is not None:
        logger.info(f"Returning cached geocode results for '{query_clean}'")
        return cached_res

    headers = {
        "User-Agent": settings.USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    params = {
        "q": query_clean,
        "format": "json",
        "addressdetails": 1,
        "limit": 5,
    }

    global _last_request_time
    async with _nominatim_lock:
        # Rate limit throttling: 1 second delay between outbound requests to Nominatim
        elapsed = time.time() - _last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        _last_request_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=settings.NOMINATIM_TIMEOUT) as client:
                response = await client.get(settings.NOMINATIM_URL, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                results: List[GeocodeResult] = []
                for item in data:
                    lat = float(item.get("lat", 0.0))
                    lon = float(item.get("lon", 0.0))
                    name = item.get("display_name", query_clean)
                    results.append(GeocodeResult(
                        display_name=name,
                        latitude=lat,
                        longitude=lon
                    ))

                geocode_cache.set(cache_key, results)
                return results

        except httpx.TimeoutException:
            logger.error(f"Nominatim timeout while geocoding '{query_clean}'")
            raise RuntimeError("Geocoding service timed out. Please try again.")
        except httpx.HTTPStatusError as exc:
            logger.error(f"Nominatim HTTP error {exc.response.status_code} for query '{query_clean}'")
            raise RuntimeError("Geocoding service encountered an HTTP error.")
        except Exception as exc:
            logger.error(f"Geocoding error for '{query_clean}': {str(exc)}")
            raise RuntimeError("Failed to resolve location coordinates.")

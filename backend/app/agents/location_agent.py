import json
import time
import urllib.request
import urllib.parse
import urllib.error

USER_AGENT = "TheligaiMSMEAssessment/1.0"


def verify_location(shop_name: str, address_or_area: str) -> dict:
    try:
        query = f"{shop_name} {address_or_area}"
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "limit": 3,
        })
        time.sleep(1)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode())
        if results:
            first = results[0]
            return {
                "location_found": True,
                "matched_name": first.get("display_name", "").split(",")[0],
                "coordinates": {"lat": first["lat"], "lon": first["lon"]},
                "address": first["display_name"],
            }
        return {"location_found": False}
    except Exception:
        return {"location_found": False, "error": "location lookup unavailable"}


def check_address_consistency(voice_location: str, nominatim_result: dict) -> str | None:
    if not voice_location or not nominatim_result.get("location_found"):
        return None
    voice_words = set(voice_location.lower().split())
    address_lower = nominatim_result.get("address", "").lower()
    overlap = voice_words & set(address_lower.split())
    common = {"near", "the", "a", "an", "in", "at", "of", "and", "or", "to", "is", "are"}
    meaningful = overlap - common
    if not meaningful:
        return "Officer\u2019s stated location does not clearly match public map records \u2014 verify address."
    return None

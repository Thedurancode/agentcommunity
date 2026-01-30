"""
Google Places API Service for address autocomplete and geocoding.

Provides:
- Address autocomplete suggestions as user types
- Full address details from place_id
- Geocoding (lat/lng) for addresses
"""
import httpx
from typing import Optional, List, Dict, Any

from app.core.config import settings


class GooglePlacesService:
    """Service for Google Places API interactions."""

    BASE_URL = "https://maps.googleapis.com/maps/api/place"

    def __init__(self):
        if not settings.GOOGLE_PLACES_API_KEY:
            raise ValueError("GOOGLE_PLACES_API_KEY not configured")
        self.api_key = settings.GOOGLE_PLACES_API_KEY

    def is_available(self) -> bool:
        """Check if service is available."""
        return bool(settings.GOOGLE_PLACES_API_KEY)

    async def autocomplete(
        self,
        query: str,
        types: str = "address",
        components: Optional[str] = "country:us",
        session_token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get address autocomplete suggestions.

        Args:
            query: The text to search for
            types: Place types to filter (default: "address")
            components: Country restrictions (default: "country:us")
            session_token: Optional session token for billing optimization

        Returns:
            List of prediction objects with description and place_id
        """
        params = {
            "input": query,
            "types": types,
            "key": self.api_key,
        }

        if components:
            params["components"] = components
        if session_token:
            params["sessiontoken"] = session_token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/autocomplete/json",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK" and data.get("status") != "ZERO_RESULTS":
                error_msg = data.get("error_message", data.get("status", "Unknown error"))
                raise ValueError(f"Google Places API error: {error_msg}")

            predictions = data.get("predictions", [])
            return [
                {
                    "place_id": p["place_id"],
                    "description": p["description"],
                    "main_text": p.get("structured_formatting", {}).get("main_text"),
                    "secondary_text": p.get("structured_formatting", {}).get("secondary_text"),
                    "types": p.get("types", []),
                }
                for p in predictions
            ]

    async def get_place_details(
        self,
        place_id: str,
        session_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get full address details from a place_id.

        Args:
            place_id: The Google place_id from autocomplete
            session_token: Optional session token (should match autocomplete call)

        Returns:
            Structured address data with components and coordinates
        """
        params = {
            "place_id": place_id,
            "fields": "formatted_address,address_components,geometry,name,place_id",
            "key": self.api_key,
        }

        if session_token:
            params["sessiontoken"] = session_token

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/details/json",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK":
                error_msg = data.get("error_message", data.get("status", "Unknown error"))
                raise ValueError(f"Google Places API error: {error_msg}")

            result = data.get("result", {})
            return self._parse_place_details(result)

    def _parse_place_details(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Google place details into structured format."""
        components = result.get("address_components", [])
        geometry = result.get("geometry", {})
        location = geometry.get("location", {})

        # Extract address components
        parsed = {
            "place_id": result.get("place_id"),
            "formatted_address": result.get("formatted_address"),
            "street_number": None,
            "street_name": None,
            "address": None,  # Will be street_number + street_name
            "city": None,
            "state": None,
            "state_short": None,
            "zip_code": None,
            "county": None,
            "country": None,
            "country_short": None,
            "latitude": location.get("lat"),
            "longitude": location.get("lng"),
        }

        for component in components:
            types = component.get("types", [])
            long_name = component.get("long_name")
            short_name = component.get("short_name")

            if "street_number" in types:
                parsed["street_number"] = long_name
            elif "route" in types:
                parsed["street_name"] = long_name
            elif "locality" in types:
                parsed["city"] = long_name
            elif "sublocality" in types and not parsed["city"]:
                parsed["city"] = long_name
            elif "administrative_area_level_1" in types:
                parsed["state"] = long_name
                parsed["state_short"] = short_name
            elif "administrative_area_level_2" in types:
                parsed["county"] = long_name.replace(" County", "")
            elif "postal_code" in types:
                parsed["zip_code"] = long_name
            elif "country" in types:
                parsed["country"] = long_name
                parsed["country_short"] = short_name

        # Build full street address
        if parsed["street_number"] and parsed["street_name"]:
            parsed["address"] = f"{parsed['street_number']} {parsed['street_name']}"
        elif parsed["street_name"]:
            parsed["address"] = parsed["street_name"]

        return parsed

    async def geocode(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Geocode an address string to get coordinates.

        Args:
            address: Full address string

        Returns:
            Dict with lat, lng, and formatted_address, or None if not found
        """
        params = {
            "address": address,
            "key": self.api_key,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK":
                return None

            results = data.get("results", [])
            if not results:
                return None

            result = results[0]
            location = result.get("geometry", {}).get("location", {})

            return {
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
                "formatted_address": result.get("formatted_address"),
                "place_id": result.get("place_id"),
            }


def get_google_places_service() -> GooglePlacesService:
    """Get Google Places service instance."""
    return GooglePlacesService()


def is_google_places_available() -> bool:
    """Check if Google Places API is configured."""
    return bool(settings.GOOGLE_PLACES_API_KEY)

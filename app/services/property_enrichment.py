"""
Property Enrichment Service.

Enriches property data with external information:
- Property details (beds, baths, sqft, year built)
- Valuation (zestimate, tax assessed value)
- Location data (lat/lng, county)
- Price history, photos, schools

Uses external enrichment database or falls back to geocoding-only mode.
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
import httpx

from app.core.config import settings
from app.models.property import Property, PropertyEnrichment
from app.services.google_places import is_google_places_available, get_google_places_service


class PropertyEnrichmentService:
    """Service for enriching property data."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._enrichment_engine = None
        self._enrichment_session_maker = None

    @property
    def enrichment_engine(self):
        """Lazy-load enrichment database engine."""
        if self._enrichment_engine is None and settings.ENRICHMENT_DATABASE_URL:
            self._enrichment_engine = create_async_engine(
                settings.ENRICHMENT_DATABASE_URL,
                echo=False
            )
        return self._enrichment_engine

    @property
    def enrichment_session_maker(self):
        """Lazy-load enrichment session maker."""
        if self._enrichment_session_maker is None and self.enrichment_engine:
            self._enrichment_session_maker = async_sessionmaker(
                self.enrichment_engine,
                expire_on_commit=False
            )
        return self._enrichment_session_maker

    def is_available(self) -> bool:
        """Check if enrichment is available (either database or geocoding)."""
        return bool(settings.ENRICHMENT_DATABASE_URL) or is_google_places_available()

    def has_enrichment_database(self) -> bool:
        """Check if external enrichment database is configured."""
        return bool(settings.ENRICHMENT_DATABASE_URL)

    async def enrich_property(
        self,
        property: Property,
        force: bool = False
    ) -> Optional[PropertyEnrichment]:
        """
        Enrich a property with external data.

        Args:
            property: The Property model to enrich
            force: If True, re-enrich even if enrichment already exists

        Returns:
            PropertyEnrichment record or None if enrichment failed
        """
        # Check if already enriched
        if property.enrichment and not force:
            return property.enrichment

        # Build full address for lookup
        address_parts = [property.address, property.city, property.state, property.zip_code]
        full_address = ", ".join(filter(None, address_parts))

        if not full_address:
            return None

        enrichment_data = {}

        # Try enrichment database first
        if self.has_enrichment_database():
            db_data = await self._query_enrichment_database(
                address=property.address,
                city=property.city,
                state=property.state,
                zip_code=property.zip_code
            )
            if db_data:
                enrichment_data.update(db_data)

        # Fall back to geocoding if no database data
        if not enrichment_data.get("latitude") and is_google_places_available():
            geo_data = await self._geocode_address(full_address)
            if geo_data:
                enrichment_data.update(geo_data)

        if not enrichment_data:
            return None

        # Create or update enrichment record
        if property.enrichment:
            enrichment = property.enrichment
            for key, value in enrichment_data.items():
                if hasattr(enrichment, key) and value is not None:
                    setattr(enrichment, key, value)
            enrichment.enriched_at = datetime.utcnow()
        else:
            enrichment = PropertyEnrichment(
                property_id=property.id,
                **{k: v for k, v in enrichment_data.items() if hasattr(PropertyEnrichment, k)}
            )
            self.db.add(enrichment)

        await self.db.commit()
        await self.db.refresh(enrichment)

        return enrichment

    async def _query_enrichment_database(
        self,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Query external enrichment database for property data."""
        if not self.enrichment_session_maker:
            return None

        try:
            async with self.enrichment_session_maker() as session:
                # Build query based on available fields
                # Adjust this query based on your actual enrichment database schema
                query = text("""
                    SELECT
                        zpid,
                        parcel_id,
                        bedrooms,
                        bathrooms,
                        living_area,
                        lot_size,
                        year_built,
                        home_type,
                        property_subtype,
                        latitude,
                        longitude,
                        county,
                        county_fips,
                        zestimate,
                        zestimate_low,
                        zestimate_high,
                        rent_zestimate,
                        tax_assessed_value,
                        tax_annual_amount,
                        price,
                        price_per_sqft,
                        home_status,
                        photos,
                        price_history,
                        tax_history,
                        schools,
                        home_facts,
                        has_pool,
                        has_garage,
                        has_basement
                    FROM properties
                    WHERE
                        (address ILIKE :address OR :address IS NULL)
                        AND (city ILIKE :city OR :city IS NULL)
                        AND (state ILIKE :state OR :state IS NULL)
                        AND (zip_code = :zip_code OR :zip_code IS NULL)
                    LIMIT 1
                """)

                result = await session.execute(
                    query,
                    {
                        "address": f"%{address}%" if address else None,
                        "city": city,
                        "state": state,
                        "zip_code": zip_code
                    }
                )
                row = result.fetchone()

                if not row:
                    return None

                # Map database row to enrichment data
                return {
                    "zpid": row.zpid,
                    "parcel_id": row.parcel_id,
                    "bedrooms": row.bedrooms,
                    "bathrooms": float(row.bathrooms) if row.bathrooms else None,
                    "living_area": row.living_area,
                    "lot_size": row.lot_size,
                    "year_built": row.year_built,
                    "home_type": row.home_type,
                    "property_subtype": row.property_subtype,
                    "latitude": float(row.latitude) if row.latitude else None,
                    "longitude": float(row.longitude) if row.longitude else None,
                    "county": row.county,
                    "county_fips": row.county_fips,
                    "zestimate": row.zestimate,
                    "zestimate_low": row.zestimate_low,
                    "zestimate_high": row.zestimate_high,
                    "rent_zestimate": row.rent_zestimate,
                    "tax_assessed_value": row.tax_assessed_value,
                    "tax_annual_amount": float(row.tax_annual_amount) if row.tax_annual_amount else None,
                    "price": row.price,
                    "price_per_sqft": float(row.price_per_sqft) if row.price_per_sqft else None,
                    "home_status": row.home_status,
                    "photos": row.photos,
                    "price_history": row.price_history,
                    "tax_history": row.tax_history,
                    "schools": row.schools,
                    "home_facts": row.home_facts,
                    "has_pool": row.has_pool,
                    "has_garage": row.has_garage,
                    "has_basement": row.has_basement,
                }

        except Exception as e:
            # Log error but don't fail the whole request
            print(f"Enrichment database query failed: {e}")
            return None

    async def _geocode_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Geocode address using Google Places API."""
        if not is_google_places_available():
            return None

        try:
            service = get_google_places_service()
            result = await service.geocode(address)

            if not result:
                return None

            return {
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
            }

        except Exception as e:
            print(f"Geocoding failed: {e}")
            return None

    async def enrich_from_google_place(
        self,
        property: Property,
        place_details: Dict[str, Any]
    ) -> Optional[PropertyEnrichment]:
        """
        Create enrichment from Google Place details.

        Used when property is created from address autocomplete.
        """
        enrichment_data = {
            "latitude": place_details.get("latitude"),
            "longitude": place_details.get("longitude"),
            "county": place_details.get("county"),
        }

        # Try to get additional data from enrichment database if available
        if self.has_enrichment_database():
            db_data = await self._query_enrichment_database(
                address=place_details.get("address"),
                city=place_details.get("city"),
                state=place_details.get("state_short") or place_details.get("state"),
                zip_code=place_details.get("zip_code")
            )
            if db_data:
                # Database data takes precedence for detailed fields
                enrichment_data.update(db_data)

        # Create enrichment record
        enrichment = PropertyEnrichment(
            property_id=property.id,
            **{k: v for k, v in enrichment_data.items() if hasattr(PropertyEnrichment, k) and v is not None}
        )
        self.db.add(enrichment)
        await self.db.commit()
        await self.db.refresh(enrichment)

        return enrichment


def get_enrichment_service(db: AsyncSession) -> PropertyEnrichmentService:
    """Get property enrichment service instance."""
    return PropertyEnrichmentService(db)


def is_enrichment_available() -> bool:
    """Check if any enrichment source is configured."""
    return bool(settings.ENRICHMENT_DATABASE_URL) or is_google_places_available()

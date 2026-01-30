"""
PDF Report Generation Service.

Generates professional property intelligence reports from research dossiers.
Uses Jinja2 for templating and WeasyPrint for PDF rendering.
"""
import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.property import Property, PropertyResearch, PropertyEnrichment, ResearchStatus


# Template directory
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class PDFReportService:
    """Service for generating PDF property reports."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True
        )

    async def generate_report(
        self,
        property_id: int,
        include_comps: bool = True,
        include_timeline: bool = True
    ) -> bytes:
        """
        Generate a PDF report for a property.

        Args:
            property_id: ID of the property
            include_comps: Include comparable sales section
            include_timeline: Include ownership timeline

        Returns:
            PDF file as bytes
        """
        # Load property with relationships
        result = await self.db.execute(
            select(Property).where(Property.id == property_id)
        )
        property = result.scalar_one_or_none()
        if not property:
            raise ValueError(f"Property {property_id} not found")

        # Load enrichment
        enrichment_result = await self.db.execute(
            select(PropertyEnrichment).where(PropertyEnrichment.property_id == property_id)
        )
        enrichment = enrichment_result.scalar_one_or_none()

        # Load research
        research_result = await self.db.execute(
            select(PropertyResearch).where(PropertyResearch.property_id == property_id)
        )
        research = research_result.scalar_one_or_none()

        # Parse dossier if available
        dossier = None
        if research and research.dossier:
            try:
                dossier = json.loads(research.dossier)
            except json.JSONDecodeError:
                pass

        # Build template context
        context = self._build_context(property, enrichment, research, dossier)

        # Render template
        template = self.env.get_template("property_report.html")
        html_content = template.render(**context)

        # Generate PDF
        pdf_bytes = HTML(string=html_content).write_pdf()

        return pdf_bytes

    def _build_context(
        self,
        property: Property,
        enrichment: Optional[PropertyEnrichment],
        research: Optional[PropertyResearch],
        dossier: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build the template context from property data."""

        # Basic property info
        context = {
            "brand_name": research.brand_name if research else "Property Intelligence",
            "address": property.address or "Address Unknown",
            "city": property.city or "",
            "state": property.state or "",
            "zip_code": property.zip_code or "",
            "report_date": datetime.now().strftime("%B %d, %Y"),
            "intended_use": research.intended_use if research else "BUY/HOLD",
        }

        # Property image (from enrichment photos if available)
        property_image = None
        if enrichment and enrichment.photos:
            try:
                photos = json.loads(enrichment.photos)
                if photos and len(photos) > 0:
                    property_image = photos[0] if isinstance(photos[0], str) else photos[0].get("url")
            except (json.JSONDecodeError, TypeError):
                pass
        context["property_image"] = property_image

        # Value estimate
        if research and research.value_estimate_low and research.value_estimate_high:
            context["value_range"] = f"${research.value_estimate_low:,} - ${research.value_estimate_high:,}"
        elif enrichment and enrichment.zestimate:
            context["value_range"] = f"${enrichment.zestimate:,}"
        else:
            context["value_range"] = "Not Available"

        # Value confidence
        context["value_confidence"] = 0
        if dossier:
            value_band = dossier.get("comps_and_market_snapshot", {}).get("value_band_estimate", {})
            context["value_confidence"] = value_band.get("confidence", 0)

        # Current owner
        context["current_owner"] = research.current_owner if research else None

        # Assessed value
        if research and research.assessed_value:
            context["assessed_value_formatted"] = f"${research.assessed_value:,}"
        elif enrichment and enrichment.tax_assessed_value:
            context["assessed_value_formatted"] = f"${enrichment.tax_assessed_value:,}"
        else:
            context["assessed_value_formatted"] = "Not Available"

        # Zoning
        context["zoning"] = research.zoning_classification if research else None
        context["zoning_summary"] = None
        if dossier:
            zoning_data = dossier.get("permits_zoning_violations", {})
            summary = zoning_data.get("zoning_constraints_summary", {})
            if isinstance(summary, dict) and summary.get("value"):
                context["zoning_summary"] = summary["value"]
            elif isinstance(summary, str):
                context["zoning_summary"] = summary

        # Property facts
        context["beds"] = enrichment.bedrooms if enrichment else None
        context["baths"] = enrichment.bathrooms if enrichment else None
        context["sqft_formatted"] = f"{enrichment.living_area:,}" if enrichment and enrichment.living_area else None
        context["year_built"] = enrichment.year_built if enrichment else None

        # Additional property facts table
        property_facts = []
        if enrichment:
            if enrichment.lot_size:
                property_facts.append({"label": "Lot Size", "value": f"{enrichment.lot_size:,} sq ft"})
            if enrichment.home_type:
                property_facts.append({"label": "Property Type", "value": enrichment.home_type})
            if enrichment.has_pool:
                property_facts.append({"label": "Pool", "value": "Yes"})
            if enrichment.has_garage:
                property_facts.append({"label": "Garage", "value": "Yes"})
            if enrichment.has_basement:
                property_facts.append({"label": "Basement", "value": "Yes"})
        context["property_facts"] = property_facts if property_facts else None

        # Risk scores
        risks = []
        if research:
            risk_map = [
                ("Title", research.risk_title),
                ("Tax", research.risk_tax),
                ("Permits", research.risk_permit),
                ("Environmental", research.risk_environmental),
                ("Market", research.risk_market),
                ("Neighborhood", research.risk_neighborhood),
            ]
            for label, score in risk_map:
                if score is not None:
                    level = "low" if score <= 3 else "medium" if score <= 6 else "high"
                    risks.append({"label": label, "score": score, "level": level})
        context["risks"] = risks if risks else [
            {"label": "Title", "score": 5, "level": "medium"},
            {"label": "Tax", "score": 3, "level": "low"},
            {"label": "Permits", "score": 4, "level": "medium"},
            {"label": "Environmental", "score": 2, "level": "low"},
            {"label": "Market", "score": 5, "level": "medium"},
            {"label": "Neighborhood", "score": 4, "level": "medium"},
        ]

        # Ownership timeline
        ownership_timeline = []
        if dossier:
            timeline = dossier.get("ownership_and_title_timeline", {}).get("timeline_30y", [])
            for transfer in timeline[:10]:  # Limit to 10 entries
                if isinstance(transfer, dict):
                    ownership_timeline.append({
                        "date": self._extract_value(transfer.get("date", "Unknown")),
                        "grantor": self._extract_value(transfer.get("grantor", "Unknown")),
                        "grantee": self._extract_value(transfer.get("grantee", "Unknown")),
                        "type": self._extract_value(transfer.get("deed_type", "Unknown")),
                        "consideration": self._extract_value(transfer.get("consideration", "N/A")),
                    })
        context["ownership_timeline"] = ownership_timeline if ownership_timeline else None

        # Title red flags
        title_flags = []
        if dossier:
            flags = dossier.get("ownership_and_title_timeline", {}).get("title_red_flags", {}).get("items", [])
            for flag in flags:
                if isinstance(flag, dict) and flag.get("value"):
                    title_flags.append(flag["value"])
                elif isinstance(flag, str):
                    title_flags.append(flag)
        context["title_flags"] = title_flags if title_flags else None

        # Tax history
        tax_history = []
        if dossier:
            history = dossier.get("taxes_and_assessments", {}).get("history", [])
            for tax in history[:5]:  # Limit to 5 years
                if isinstance(tax, dict):
                    tax_history.append({
                        "year": self._extract_value(tax.get("year", "N/A")),
                        "assessed": self._format_currency(tax.get("assessed_value")),
                        "billed": self._format_currency(tax.get("tax_billed")),
                        "status": self._extract_value(tax.get("status", "Unknown")),
                    })
        context["tax_history"] = tax_history if tax_history else None

        # Permits
        permits = []
        if dossier:
            permit_list = dossier.get("permits_zoning_violations", {}).get("permits", [])
            for permit in permit_list[:10]:
                if isinstance(permit, dict):
                    permits.append({
                        "date": self._extract_value(permit.get("date", "Unknown")),
                        "type": self._extract_value(permit.get("type", "Unknown")),
                        "description": self._extract_value(permit.get("scope", permit.get("description", "N/A"))),
                        "status": self._extract_value(permit.get("status", "Unknown")),
                    })
        context["permits"] = permits if permits else None

        # Comparable sales
        comps = []
        if dossier:
            comp_sets = dossier.get("comps_and_market_snapshot", {}).get("comp_sets", {})
            primary_comps = comp_sets.get("primary", [])
            for comp in primary_comps[:6]:  # Limit to 6 comps
                if isinstance(comp, dict):
                    comps.append({
                        "address": self._extract_value(comp.get("address", "Unknown")),
                        "distance": self._extract_value(comp.get("distance", "N/A")),
                        "beds": self._extract_value(comp.get("beds", "N/A")),
                        "baths": self._extract_value(comp.get("baths", "N/A")),
                        "sqft": self._extract_value(comp.get("sqft", "N/A")),
                        "sold_price": self._format_currency(comp.get("sold_price", comp.get("sold"))),
                        "price_sqft": self._format_currency(comp.get("price_sqft", comp.get("$/sqft"))),
                        "date": self._extract_value(comp.get("sale_date", comp.get("date", "N/A"))),
                    })
        context["comps"] = comps if comps else None

        # Rent estimate
        if dossier:
            rent_data = dossier.get("comps_and_market_snapshot", {}).get("rent_estimate", {})
            if isinstance(rent_data, dict) and rent_data.get("value"):
                context["rent_estimate"] = self._format_currency(rent_data["value"])
            else:
                context["rent_estimate"] = None

            yield_data = dossier.get("comps_and_market_snapshot", {}).get("gross_yield_range", {})
            if isinstance(yield_data, dict) and yield_data.get("value"):
                context["gross_yield"] = yield_data["value"]
            else:
                context["gross_yield"] = None
        else:
            context["rent_estimate"] = None
            context["gross_yield"] = None

        # Neighborhood
        if dossier:
            neighborhood = dossier.get("neighborhood_intelligence", {})

            schools = neighborhood.get("schools", {})
            if isinstance(schools, dict) and schools.get("value"):
                context["schools"] = schools["value"]
            else:
                context["schools"] = None

            transit = neighborhood.get("transit_access", {})
            if isinstance(transit, dict) and transit.get("value"):
                context["transit"] = transit["value"]
            else:
                context["transit"] = None

            env = neighborhood.get("environmental", {})
            flood = env.get("fema_flood_zone", {})
            if isinstance(flood, dict) and flood.get("value"):
                context["flood_zone"] = flood["value"]
            else:
                context["flood_zone"] = None

            # Environmental concerns
            env_concerns = []
            epa_sites = env.get("epa_njdep_sites", {})
            if isinstance(epa_sites, dict) and epa_sites.get("value"):
                env_concerns.append(epa_sites["value"])
            context["environmental_concerns"] = env_concerns if env_concerns else None
        else:
            context["schools"] = None
            context["transit"] = None
            context["flood_zone"] = None
            context["environmental_concerns"] = None

        # Next steps
        if dossier:
            next_steps_data = dossier.get("risk_scorecard_and_next_steps", {})

            context["top_questions"] = next_steps_data.get("top_10_questions", [])[:10]
            context["top_documents"] = next_steps_data.get("top_10_documents", [])[:10]
            context["next_steps"] = next_steps_data.get("next_steps_checklist", [])[:10]
        else:
            context["top_questions"] = None
            context["top_documents"] = None
            context["next_steps"] = None

        return context

    def _extract_value(self, data: Any) -> str:
        """Extract value from data that might be a dict with 'value' key or a string."""
        if isinstance(data, dict):
            return str(data.get("value", "Unknown"))
        return str(data) if data else "Unknown"

    def _format_currency(self, value: Any) -> str:
        """Format a value as currency."""
        if value is None:
            return "N/A"
        if isinstance(value, dict):
            value = value.get("value")
        if value is None:
            return "N/A"
        try:
            num = float(str(value).replace("$", "").replace(",", ""))
            return f"${num:,.0f}"
        except (ValueError, TypeError):
            return str(value)


def get_pdf_service(db: AsyncSession) -> PDFReportService:
    """Get PDF report service instance."""
    return PDFReportService(db)

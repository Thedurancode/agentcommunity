"""
Property Research Service - Deep Due Diligence Analysis.

Uses OpenAI to perform comprehensive property research including:
- Identity & data validation
- Ownership & title timeline
- Tax & assessment history
- Permits, zoning, violations
- Market comps & valuation
- Neighborhood intelligence
- Risk scorecard

Generates a structured JSON dossier for PDF report generation.
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.property import Property, PropertyResearch, PropertyEnrichment, ResearchStatus


# The comprehensive research prompt template
RESEARCH_PROMPT_TEMPLATE = '''YOU ARE: A senior real-estate due diligence analyst producing a citation-backed Property Intelligence Dossier.

WHITE-LABELING:
- Do not mention ChatGPT/OpenAI or any assistant branding.
- Write as an internal analyst for {brand_name}.
- Output ONLY JSON that matches the required schema.

RISK PROFILE:
- Risk sensitivity: HIGH. Conservative defaults.
- Use only publicly available information. No legal advice.
- If anything cannot be verified, set it to Unknown object with reason + how_to_verify.

SUBJECT:
- Address input: {address_input}
- City/State/ZIP: {city}, {state} {zip_code}
- County hypothesis: {county_hypothesis} (must verify)
- Parcel/APN: unknown (must identify: block/lot + qualifier/unit IDs)
- Owner hypothesis: {owner_hypothesis} (must verify)
- Intended use: {intended_use} (BUY/HOLD; also note differences for flip/wholesale)
- Radius scan: 0.5 mi, 2 mi primary, 5 mi secondary
- Time windows: 30 years property history; 24 months news (flag last 90 days)

SEED SOURCES (secondary portals; do not treat as authoritative without verification):
{seed_sources}

PRIMARY / AUTHORITATIVE TARGETS (prioritize):
1) Municipality tax assessor + tax collector (proof book / tax list / tax inquiry)
2) County Clerk land records (deeds, mortgages, satisfactions, liens)
3) Municipal zoning map / ordinance + planning board materials
4) Construction permits / code enforcement
5) FEMA flood maps (MSC / FIRMette)
6) NJDEP + EPA for environmental sites
7) Crime/safety stats from reputable statistical sources (avoid anecdotes)
8) School assignment from official district sources; ratings may be included but must be labeled "third-party"

CRITICAL OUTPUT RULES:
- Return ONLY valid JSON and nothing else.
- Every non-obvious claim MUST be a Claim object with inline citations.
- Every table must be an array of row objects with a required "source" citations array.
- If sources disagree: include BOTH in "conflicts" and include a "resolution" with reliability rationale.
- Dates must be ISO YYYY-MM-DD when known; otherwise Unknown object.

TASK ORDER (DO IN ORDER):
(1) Identity & Data Validation
- Normalize USPS-style address (incl. common abbreviations).
- Confirm county, jurisdiction, block/lot, qualifier/unit/legal description if applicable.
- Capture alternate IDs: portal IDs (Zillow ZPID, Redfin ID, MLS ID if visible), tax IDs, GIS links.
- If multiple parcels/units match, map them clearly with evidence.

(2) Ownership & Title Signals (not legal advice)
- Build 30-year transfer timeline:
  transfer date, grantor, grantee, deed type, consideration, recording reference (book/page or instrument).
- Summarize mortgages + satisfactions when accessible.
- Flag red flags: quitclaim, rapid flips, foreclosure indicators, unreleased liens, HOA liens, lis pendens.
- If land records are paywalled/unavailable: mark "Secondary-only" and explain how to obtain official chain.

(3) Taxes, Assessments, Delinquency
- Current assessed value + components (land vs improvements) and ≥10-year history if possible.
- Table: tax year, assessed value, tax billed, paid/delinquent status, notes.
- Flag tax sale, special assessments, exemptions, abrupt assessment jumps.

(4) Permits, Code, Violations, Zoning
- Identify zoning classification and summarize constraints (use municipal ordinance/map).
- Permit history: date, type, scope, status, contractor (if listed).
- Code enforcement / violations if searchable.
- If not online: Unknown + who to contact + exact department name.

(5) Physical Snapshot (Public only)
- Reconcile beds/baths/sqft/year built/parking/HVAC/basement/materials across multiple sources.
- Call out discrepancies and choose "most reliable" with rationale.
- Add HOA details: fee, what it includes, rental rules (if found), reserves/litigation flags (if disclosed).

(6) Market Context: Comps & Trends (Buy/Hold)
- Build 3 comp sets with tables:
  A) Primary (same community/<=1 mi; last 6–18 months)
  B) Secondary (2–3 mi; similar style/size)
  C) Risk-band (price cuts, high DOM, distressed if known)
- Each comp row: address, distance, beds/baths/sqft/year, list/sold, $/sqft, DOM, sale date, notes, source.
- Provide value band estimate (NOT appraisal): low/high + confidence + method notes.
- Rent estimate: include rent comps if possible + gross yield range.
- Trend read (24 months) using at least one market data source.

(7) Neighborhood & Area Intelligence (0.5/2/5 mi)
- Schools (assigned public schools + boundary caveat; include district confirmation source)
- Transit/access (highways, rail, park-and-ride)
- Employers/anchors (hospitals, campuses, retail, major employers)
- Planned development/infrastructure (rezonings, major projects, roadworks)
- Environmental/safety:
  - FEMA flood zone
  - EPA/NJDEP sites (brownfields, Superfund proximity, permits)
  - Crime/safety statistics (reputable source)

(8) News & Area Narrative (Last 24 Months; flag last 90 days)
- Collect items impacting value/risk within 2–5 miles:
  rezonings, developments, lawsuits/HOA controversies, infrastructure, school changes,
  environmental events, major employer shifts.
- For each: headline, publisher, date, summary, why it matters, source.

(9) Risk Scorecard & Recommendations
- Score each 0–10 (0 low → 10 high): title, tax, permits, environmental, market/liquidity, neighborhood trajectory.
- Provide:
  - Top 10 diligence questions (HOA-specific)
  - Top 10 documents to request
  - Next steps checklist

CITATION REQUIREMENTS:
- Every non-obvious claim must include citations with: source_name, url, accessed_at.
- Prefer authoritative sources; portals are secondary.
- If a portal conflicts with municipal/county records: municipal/county wins unless proven otherwise.

NOW PRODUCE THE JSON OUTPUT USING THE EXACT SCHEMA PROVIDED (no extra top-level keys):

{{
  "meta": {{
    "brand": "{brand_name}",
    "subject_address_input": "{address_input}",
    "normalized_address": {{}},
    "analysis_date_local": "{analysis_date}",
    "intended_use": "{intended_use}",
    "radius_scan_miles": {{ "r0_5": 0.5, "r2": 2, "r5": 5 }},
    "time_windows": {{ "property_years": 30, "news_months": 24, "news_flag_days": 90 }}
  }},
  "identity_and_validation": {{
    "county": {{}},
    "jurisdiction": {{}},
    "block_lot_qualifier": {{
      "block": {{}},
      "lot": {{}},
      "qualifier": {{}},
      "legal_description": {{}}
    }},
    "alternate_ids": {{
      "zpid": {{}},
      "redfin_id": {{}},
      "mls_id": {{}},
      "tax_ids": [],
      "gis_links": []
    }},
    "unit_ambiguity": {{
      "status": "known",
      "summary": "",
      "candidates": []
    }},
    "conflicts": []
  }},
  "property_facts": {{
    "property_type": {{}},
    "year_built": {{}},
    "beds": {{}},
    "baths": {{}},
    "sqft": {{}},
    "hoa": {{
      "exists": {{}},
      "monthly_fee": {{}},
      "includes": {{}},
      "rental_rules": {{}},
      "reserves_signals": {{}},
      "litigation_signals": {{}}
    }},
    "parking": {{}},
    "hvac": {{}},
    "basement": {{}},
    "materials_exterior": {{}},
    "utilities": {{
      "water": {{}},
      "sewer": {{}},
      "electric": {{}},
      "gas": {{}}
    }},
    "discrepancies": {{ "items": [] }}
  }},
  "ownership_and_title_timeline": {{
    "current_owner": {{}},
    "timeline_30y": [],
    "mortgages_and_satisfactions": [],
    "title_red_flags": {{ "items": [] }},
    "unknowns": []
  }},
  "taxes_and_assessments": {{
    "assessed_value_current": {{}},
    "assessment_components": {{ "land": {{}}, "improvement": {{}} }},
    "history": [],
    "delinquency": {{}},
    "tax_sale_history": {{}},
    "special_assessments": {{}}
  }},
  "permits_zoning_violations": {{
    "zoning_classification": {{}},
    "zoning_constraints_summary": {{}},
    "permits": [],
    "violations": [],
    "unknowns": []
  }},
  "sales_and_listing_history": [],
  "comps_and_market_snapshot": {{
    "value_band_estimate": {{
      "status": "unknown",
      "low": null,
      "high": null,
      "confidence": 0,
      "method_notes": "",
      "citations": []
    }},
    "comp_sets": {{ "primary": [], "secondary": [], "risk_band": [] }},
    "rent_estimate": {{}},
    "rent_comps": [],
    "gross_yield_range": {{}},
    "trend_read_24m": {{}}
  }},
  "neighborhood_intelligence": {{
    "schools": {{}},
    "transit_access": {{}},
    "employers_anchors": {{}},
    "planned_development": {{}},
    "environmental": {{
      "fema_flood_zone": {{}},
      "epa_njdep_sites": {{}},
      "air_noise": {{}}
    }},
    "crime_safety": {{}}
  }},
  "news_and_area_narrative": [],
  "risk_scorecard_and_next_steps": {{
    "scores_0_to_10": {{
      "title_ownership": {{ "score": 0, "evidence": [] }},
      "tax_financial": {{ "score": 0, "evidence": [] }},
      "permit_code": {{ "score": 0, "evidence": [] }},
      "environmental": {{ "score": 0, "evidence": [] }},
      "market_liquidity": {{ "score": 0, "evidence": [] }},
      "neighborhood_trajectory": {{ "score": 0, "stance": "neutral", "evidence": [] }}
    }},
    "top_10_questions": [],
    "top_10_documents": [],
    "next_steps_checklist": []
  }},
  "source_log": []
}}'''

DEFAULT_SEED_SOURCES = "Movoto, Compass, Redfin, Zillow, Realtor.com, CountyOffice, local tax assessor websites"


class PropertyResearchService:
    """Service for deep property due diligence research."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._openai_client = None

    @property
    def openai_client(self) -> Optional[AsyncOpenAI]:
        """Lazy-load OpenAI client."""
        if self._openai_client is None and settings.OPENAI_API_KEY:
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    def is_available(self) -> bool:
        """Check if research service is available."""
        return bool(settings.OPENAI_API_KEY)

    async def start_research(
        self,
        property: Property,
        brand_name: str = "Property Intelligence",
        intended_use: str = "BUY/HOLD",
        owner_hypothesis: Optional[str] = None,
        seed_sources: Optional[str] = None,
        force: bool = False
    ) -> PropertyResearch:
        """
        Start deep research for a property.

        Args:
            property: The Property to research
            brand_name: Brand name for white-labeling the report
            intended_use: BUY/HOLD, FLIP, or WHOLESALE
            owner_hypothesis: Known/suspected owner name
            seed_sources: Comma-separated list of data sources
            force: If True, re-research even if already completed

        Returns:
            PropertyResearch record (may be in_progress)
        """
        # Check for existing research
        result = await self.db.execute(
            select(PropertyResearch).where(PropertyResearch.property_id == property.id)
        )
        research = result.scalar_one_or_none()

        if research:
            if research.status == ResearchStatus.COMPLETED and not force:
                return research
            # Reset for re-research
            research.status = ResearchStatus.IN_PROGRESS
            research.started_at = datetime.utcnow()
            research.error_message = None
        else:
            research = PropertyResearch(
                property_id=property.id,
                status=ResearchStatus.IN_PROGRESS,
                brand_name=brand_name,
                intended_use=intended_use,
                started_at=datetime.utcnow()
            )
            self.db.add(research)

        await self.db.commit()
        await self.db.refresh(research)

        # Run the actual research
        try:
            dossier = await self._perform_research(
                property=property,
                brand_name=brand_name,
                intended_use=intended_use,
                owner_hypothesis=owner_hypothesis,
                seed_sources=seed_sources or DEFAULT_SEED_SOURCES
            )

            # Store results
            research.dossier = json.dumps(dossier)
            research.status = ResearchStatus.COMPLETED
            research.completed_at = datetime.utcnow()

            # Extract key fields for quick access
            self._extract_key_fields(research, dossier)

            await self.db.commit()
            await self.db.refresh(research)

        except Exception as e:
            research.status = ResearchStatus.FAILED
            research.error_message = str(e)
            await self.db.commit()
            raise

        return research

    async def _perform_research(
        self,
        property: Property,
        brand_name: str,
        intended_use: str,
        owner_hypothesis: Optional[str],
        seed_sources: str
    ) -> Dict[str, Any]:
        """Perform the actual research using OpenAI."""
        if not self.openai_client:
            raise ValueError("OpenAI API key not configured")

        # Build full address
        address_parts = [property.address, property.city, property.state, property.zip_code]
        full_address = ", ".join(filter(None, address_parts))

        # Get county from enrichment if available
        county_hypothesis = "Unknown"
        if property.enrichment and property.enrichment.county:
            county_hypothesis = property.enrichment.county

        # Build the prompt
        prompt = RESEARCH_PROMPT_TEMPLATE.format(
            brand_name=brand_name,
            address_input=full_address,
            city=property.city or "Unknown",
            state=property.state or "Unknown",
            zip_code=property.zip_code or "Unknown",
            county_hypothesis=county_hypothesis,
            owner_hypothesis=owner_hypothesis or "Unknown",
            intended_use=intended_use,
            seed_sources=seed_sources,
            analysis_date=datetime.utcnow().strftime("%Y-%m-%d")
        )

        # Call OpenAI for deep research analysis
        # Using GPT-4o with high token limit for comprehensive analysis
        response = await self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior real-estate due diligence analyst. You produce comprehensive, citation-backed property intelligence dossiers. You MUST return ONLY valid JSON matching the exact schema provided. No markdown, no explanations - just the JSON object."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            max_tokens=16000,
            response_format={"type": "json_object"}
        )

        # Extract the response text
        response_text = response.choices[0].message.content or ""

        # Parse JSON from response
        try:
            # Try to find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                dossier = json.loads(json_str)
            else:
                raise ValueError("No valid JSON found in response")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse research response as JSON: {e}")

        return dossier

    def _extract_key_fields(self, research: PropertyResearch, dossier: Dict[str, Any]) -> None:
        """Extract key fields from dossier for quick access."""
        try:
            # Normalized address
            meta = dossier.get("meta", {})
            normalized = meta.get("normalized_address", {})
            if isinstance(normalized, dict) and normalized.get("value"):
                research.normalized_address = normalized["value"]
            elif isinstance(normalized, str):
                research.normalized_address = normalized

            # Identity
            identity = dossier.get("identity_and_validation", {})
            county = identity.get("county", {})
            if isinstance(county, dict) and county.get("value"):
                research.county = county["value"]
            elif isinstance(county, str):
                research.county = county

            block_lot = identity.get("block_lot_qualifier", {})
            if block_lot:
                block = block_lot.get("block", {})
                lot = block_lot.get("lot", {})
                block_val = block.get("value") if isinstance(block, dict) else block
                lot_val = lot.get("value") if isinstance(lot, dict) else lot
                if block_val or lot_val:
                    research.block_lot = f"{block_val or ''}/{lot_val or ''}"

            # Ownership
            ownership = dossier.get("ownership_and_title_timeline", {})
            owner = ownership.get("current_owner", {})
            if isinstance(owner, dict) and owner.get("value"):
                research.current_owner = owner["value"]
            elif isinstance(owner, str):
                research.current_owner = owner

            # Taxes
            taxes = dossier.get("taxes_and_assessments", {})
            assessed = taxes.get("assessed_value_current", {})
            if isinstance(assessed, dict) and assessed.get("value"):
                try:
                    research.assessed_value = int(assessed["value"])
                except (ValueError, TypeError):
                    pass
            elif isinstance(assessed, (int, float)):
                research.assessed_value = int(assessed)

            # Zoning
            permits = dossier.get("permits_zoning_violations", {})
            zoning = permits.get("zoning_classification", {})
            if isinstance(zoning, dict) and zoning.get("value"):
                research.zoning_classification = zoning["value"]
            elif isinstance(zoning, str):
                research.zoning_classification = zoning

            # Value estimates
            comps = dossier.get("comps_and_market_snapshot", {})
            value_band = comps.get("value_band_estimate", {})
            if value_band.get("low"):
                try:
                    research.value_estimate_low = int(value_band["low"])
                except (ValueError, TypeError):
                    pass
            if value_band.get("high"):
                try:
                    research.value_estimate_high = int(value_band["high"])
                except (ValueError, TypeError):
                    pass

            # Risk scores
            risk = dossier.get("risk_scorecard_and_next_steps", {})
            scores = risk.get("scores_0_to_10", {})

            if scores.get("title_ownership", {}).get("score") is not None:
                research.risk_title = scores["title_ownership"]["score"]
            if scores.get("tax_financial", {}).get("score") is not None:
                research.risk_tax = scores["tax_financial"]["score"]
            if scores.get("permit_code", {}).get("score") is not None:
                research.risk_permit = scores["permit_code"]["score"]
            if scores.get("environmental", {}).get("score") is not None:
                research.risk_environmental = scores["environmental"]["score"]
            if scores.get("market_liquidity", {}).get("score") is not None:
                research.risk_market = scores["market_liquidity"]["score"]
            if scores.get("neighborhood_trajectory", {}).get("score") is not None:
                research.risk_neighborhood = scores["neighborhood_trajectory"]["score"]

        except Exception:
            # Don't fail if extraction has issues
            pass

    async def get_research(self, property_id: int) -> Optional[PropertyResearch]:
        """Get research for a property."""
        result = await self.db.execute(
            select(PropertyResearch).where(PropertyResearch.property_id == property_id)
        )
        return result.scalar_one_or_none()

    async def get_dossier(self, property_id: int) -> Optional[Dict[str, Any]]:
        """Get the full dossier JSON for a property."""
        research = await self.get_research(property_id)
        if not research or not research.dossier:
            return None
        try:
            return json.loads(research.dossier)
        except json.JSONDecodeError:
            return None


def get_research_service(db: AsyncSession) -> PropertyResearchService:
    """Get property research service instance."""
    return PropertyResearchService(db)


def is_research_available() -> bool:
    """Check if research service is available."""
    return bool(settings.OPENAI_API_KEY)

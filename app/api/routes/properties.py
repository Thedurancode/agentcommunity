from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import httpx

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.property import Property, PropertyContact, PropertyContract, PropertyPhase, PropertyNote, PropertyPhoneCall, PropertySMS, PropertyEnrichment, PropertyResearch, ContractStatus, CallStatus, SMSStatus, SMSDirection
from app.schemas.property import (
    PropertyCreate, PropertyResponse, PropertyUpdate, PropertyWithDetails, PropertyList,
    PropertyContactCreate, PropertyContactResponse, PropertyContactUpdate,
    PropertyContractCreate, PropertyContractResponse, PropertyContractUpdate,
    PropertyPhaseCreate, PropertyPhaseResponse, PropertyPhaseUpdate,
    PropertyNoteCreate, PropertyNoteResponse, PropertyNoteUpdate, PropertyNoteWithContact,
    DocuSealTemplate, DocuSealSendRequest, DocuSealSubmissionResponse,
    PhoneCallCreate, PhoneCallResponse, PhoneCallUpdate, PhoneCallWithContact, PhoneCallInitiateResponse,
    SMSCreate, SMSResponse, SMSWithContact, SMSSendResponse, SMSConversation,
    AddressPrediction, AddressAutocompleteResponse, AddressDetails, PropertyCreateFromPlace,
    PropertyEnrichmentResponse, PropertyWithEnrichment, PropertyWithFullDetails,
    PropertyResearchRequest, PropertyResearchSummary, PropertyResearchFull,
)
from app.api.deps import get_current_user
from app.services.docuseal import DocuSealService, map_docuseal_status_to_contract_status
from app.services.vapi import VapiService
from app.services.twilio_sms import get_twilio_service
from app.services.google_places import get_google_places_service, is_google_places_available
from app.services.property_enrichment import get_enrichment_service, is_enrichment_available
from app.services.property_research import get_research_service, is_research_available
from app.services.pdf_report import get_pdf_service
from app.services.email import get_email_service


router = APIRouter(prefix="/properties", tags=["properties"])


async def get_property_or_404(
    property_id: int,
    user: User,
    db: AsyncSession,
    load_relations: bool = False
) -> Property:
    """Get property by ID, checking ownership."""
    query = select(Property).where(Property.id == property_id)
    if load_relations:
        query = query.options(
            selectinload(Property.contacts),
            selectinload(Property.contracts),
            selectinload(Property.phases),
            selectinload(Property.notes)
        )

    result = await db.execute(query)
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        )

    # Check ownership (admins can access all)
    if user.role != UserRole.ADMIN and property.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this property",
        )

    return property


# ============ Address Autocomplete ============

@router.get("/address/autocomplete", response_model=AddressAutocompleteResponse)
async def address_autocomplete(
    query: str,
    session_token: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Get address autocomplete suggestions as the user types.

    Use the returned place_id to get full address details or create a property.
    Pass the same session_token across autocomplete and details calls for billing optimization.
    """
    if not is_google_places_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API not configured"
        )

    if len(query) < 3:
        return AddressAutocompleteResponse(predictions=[])

    try:
        service = get_google_places_service()
        predictions = await service.autocomplete(
            query=query,
            session_token=session_token
        )
        return AddressAutocompleteResponse(
            predictions=[AddressPrediction(**p) for p in predictions]
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/address/details/{place_id}", response_model=AddressDetails)
async def get_address_details(
    place_id: str,
    session_token: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Get full address details from a Google place_id.

    Returns structured address components (street, city, state, zip) and coordinates.
    """
    if not is_google_places_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API not configured"
        )

    try:
        service = get_google_places_service()
        details = await service.get_place_details(
            place_id=place_id,
            session_token=session_token
        )
        return AddressDetails(**details)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/from-place", response_model=PropertyWithEnrichment, status_code=status.HTTP_201_CREATED)
async def create_property_from_place(
    property_data: PropertyCreateFromPlace,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a property from a Google Place selection.

    This is the recommended way to create properties:
    1. User types address -> autocomplete suggestions
    2. User selects address -> gets place_id
    3. Call this endpoint with place_id -> property created with full address and auto-enriched
    """
    if not is_google_places_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API not configured"
        )

    try:
        # Get full address details from Google
        places_service = get_google_places_service()
        place_details = await places_service.get_place_details(property_data.place_id)

        # Create property with structured address
        property = Property(
            name=property_data.name or place_details.get("formatted_address", "New Property"),
            address=place_details.get("address"),
            city=place_details.get("city"),
            state=place_details.get("state_short") or place_details.get("state"),
            zip_code=place_details.get("zip_code"),
            country=place_details.get("country_short") or place_details.get("country", "USA"),
            property_type=property_data.property_type,
            description=property_data.description,
            status=property_data.status,
            owner_id=current_user.id,
        )
        db.add(property)
        await db.commit()
        await db.refresh(property)

        # Auto-enrich with property data
        enrichment_service = get_enrichment_service(db)
        enrichment = await enrichment_service.enrich_from_google_place(property, place_details)

        # Reload property with enrichment
        result = await db.execute(
            select(Property)
            .options(selectinload(Property.enrichment))
            .where(Property.id == property.id)
        )
        property = result.scalar_one()

        return property

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============ Property CRUD ============

@router.post("", response_model=PropertyWithEnrichment, status_code=status.HTTP_201_CREATED)
async def create_property(
    property_data: PropertyCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new property.

    If the property has an address, it will be automatically enriched
    with property data (beds, baths, value, etc.) in the background.

    For best results, use the /from-place endpoint with Google autocomplete.
    """
    property = Property(
        **property_data.model_dump(),
        owner_id=current_user.id,
    )
    db.add(property)
    await db.commit()
    await db.refresh(property)

    # Auto-enrich if we have an address
    if property.address and is_enrichment_available():
        try:
            enrichment_service = get_enrichment_service(db)
            await enrichment_service.enrich_property(property)
            # Reload with enrichment
            result = await db.execute(
                select(Property)
                .options(selectinload(Property.enrichment))
                .where(Property.id == property.id)
            )
            property = result.scalar_one()
        except Exception:
            # Don't fail property creation if enrichment fails
            pass

    return property


@router.get("", response_model=PropertyList)
async def list_properties(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all properties for the current user."""
    if current_user.role == UserRole.ADMIN:
        result = await db.execute(select(Property).offset(skip).limit(limit))
        properties = result.scalars().all()
        count_result = await db.execute(select(Property))
        total = len(count_result.scalars().all())
    else:
        result = await db.execute(
            select(Property)
            .where(Property.owner_id == current_user.id)
            .offset(skip)
            .limit(limit)
        )
        properties = result.scalars().all()
        count_result = await db.execute(
            select(Property).where(Property.owner_id == current_user.id)
        )
        total = len(count_result.scalars().all())

    return PropertyList(properties=list(properties), total=total)


@router.get("/{property_id}", response_model=PropertyWithDetails)
async def get_property(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a property with all details."""
    property = await get_property_or_404(property_id, current_user, db, load_relations=True)
    return property


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: int,
    property_data: PropertyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a property."""
    property = await get_property_or_404(property_id, current_user, db)

    update_data = property_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(property, field, value)

    await db.commit()
    await db.refresh(property)
    return property


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a property."""
    property = await get_property_or_404(property_id, current_user, db)
    await db.delete(property)
    await db.commit()
    return None


# ============ Property Enrichment ============

@router.post("/{property_id}/enrich", response_model=PropertyEnrichmentResponse)
async def enrich_property(
    property_id: int,
    force: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger property enrichment.

    Fetches property data (beds, baths, value, etc.) from external sources.
    Use force=True to re-enrich even if data already exists.
    """
    if not is_enrichment_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Property enrichment not configured"
        )

    property = await get_property_or_404(property_id, current_user, db, load_relations=True)

    if not property.address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Property must have an address for enrichment"
        )

    try:
        enrichment_service = get_enrichment_service(db)
        enrichment = await enrichment_service.enrich_property(property, force=force)

        if not enrichment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No enrichment data found for this address"
            )

        return enrichment

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Enrichment failed: {str(e)}"
        )


@router.get("/{property_id}/enrichment", response_model=PropertyEnrichmentResponse)
async def get_property_enrichment(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get enrichment data for a property."""
    property = await get_property_or_404(property_id, current_user, db, load_relations=True)

    result = await db.execute(
        select(PropertyEnrichment).where(PropertyEnrichment.property_id == property_id)
    )
    enrichment = result.scalar_one_or_none()

    if not enrichment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No enrichment data for this property. Use POST /enrich to fetch."
        )

    return enrichment


# ============ Property Research (Deep Due Diligence) ============

@router.post("/{property_id}/research", response_model=PropertyResearchSummary, status_code=status.HTTP_202_ACCEPTED)
async def start_property_research(
    property_id: int,
    request: PropertyResearchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Start comprehensive due diligence research for a property.

    This performs deep AI-powered research including:
    - Identity & data validation (parcel, block/lot, tax IDs)
    - Ownership & title timeline (30 years)
    - Tax & assessment history
    - Permits, zoning, violations
    - Market comps & valuation
    - Neighborhood intelligence (schools, transit, employers)
    - Environmental & safety data
    - Risk scorecard with recommendations

    The research may take 30-60 seconds to complete. Poll GET /research for status.
    """
    if not is_research_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Property research not configured (OpenAI API key required)"
        )

    property = await get_property_or_404(property_id, current_user, db, load_relations=True)

    if not property.address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Property must have an address for research"
        )

    try:
        research_service = get_research_service(db)
        research = await research_service.start_research(
            property=property,
            brand_name=request.brand_name,
            intended_use=request.intended_use,
            owner_hypothesis=request.owner_hypothesis,
            seed_sources=request.seed_sources,
            force=request.force
        )
        return research

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Research failed: {str(e)}"
        )


@router.get("/{property_id}/research", response_model=PropertyResearchSummary)
async def get_property_research_status(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get research status and summary for a property."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyResearch).where(PropertyResearch.property_id == property_id)
    )
    research = result.scalar_one_or_none()

    if not research:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No research for this property. Use POST /research to start."
        )

    return research


@router.get("/{property_id}/research/dossier")
async def get_property_research_dossier(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the full research dossier JSON for a property.

    Returns the complete due diligence report with all sections:
    - meta
    - identity_and_validation
    - property_facts
    - ownership_and_title_timeline
    - taxes_and_assessments
    - permits_zoning_violations
    - sales_and_listing_history
    - comps_and_market_snapshot
    - neighborhood_intelligence
    - news_and_area_narrative
    - risk_scorecard_and_next_steps
    - source_log

    This JSON can be used to generate PDF reports.
    """
    await get_property_or_404(property_id, current_user, db)

    research_service = get_research_service(db)
    dossier = await research_service.get_dossier(property_id)

    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No research dossier available. Start research first with POST /research."
        )

    return dossier


@router.get("/{property_id}/research/pdf")
async def get_property_research_pdf(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate and download a PDF report for a property.

    Creates a professional, modern PDF report including:
    - Cover page with property image
    - Executive summary with risk scores
    - Property facts (beds, baths, sqft, etc.)
    - Ownership timeline
    - Tax history
    - Zoning & permits
    - Market comps & valuation
    - Neighborhood intelligence
    - Next steps checklist

    Returns a downloadable PDF file.
    """
    property = await get_property_or_404(property_id, current_user, db)

    try:
        pdf_service = get_pdf_service(db)
        pdf_bytes = await pdf_service.generate_report(property_id)

        # Create filename from address
        filename = f"property_report_{property_id}"
        if property.address:
            safe_address = "".join(c if c.isalnum() or c in " -" else "_" for c in property.address)
            filename = f"report_{safe_address[:30]}"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.pdf"'
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(e)}"
        )


@router.post("/{property_id}/research/email")
async def email_property_report(
    property_id: int,
    to_email: str,
    cc_emails: Optional[List[str]] = None,
    custom_message: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate and email a PDF report for a property.

    Sends a professional email with the property report as a PDF attachment.
    The email includes branding and a summary of what's in the report.

    Args:
        property_id: ID of the property (must have completed research)
        to_email: Recipient email address
        cc_emails: Optional list of CC recipients
        custom_message: Optional custom message to include in the email

    Returns:
        Email send status and ID
    """
    from app.core.config import settings

    if not settings.RESEND_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service not configured (RESEND_API_KEY required)"
        )

    property = await get_property_or_404(property_id, current_user, db)

    # Get research for brand name
    result = await db.execute(
        select(PropertyResearch).where(PropertyResearch.property_id == property_id)
    )
    research = result.scalar_one_or_none()

    brand_name = research.brand_name if research else "Property Intelligence"

    # Generate PDF
    try:
        pdf_service = get_pdf_service(db)
        pdf_bytes = await pdf_service.generate_report(property_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(e)}"
        )

    # Build address string
    address_parts = [property.address, property.city, property.state, property.zip_code]
    property_address = ", ".join(filter(None, address_parts)) or f"Property #{property_id}"

    # Send email
    try:
        email_service = get_email_service()
        result = await email_service.send_property_report_email(
            to=to_email,
            property_address=property_address,
            pdf_bytes=pdf_bytes,
            brand_name=brand_name,
            custom_message=custom_message
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Email sending failed: {result.get('error', 'Unknown error')}"
            )

        return {
            "success": True,
            "email_id": result.get("email_id"),
            "message": f"Report sent to {to_email}",
            "property_address": property_address
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email sending failed: {str(e)}"
        )


# ============ Contact CRUD ============

@router.post("/{property_id}/contacts", response_model=PropertyContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    property_id: int,
    contact_data: PropertyContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a contact to a property."""
    await get_property_or_404(property_id, current_user, db)

    contact = PropertyContact(
        **contact_data.model_dump(),
        property_id=property_id,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.get("/{property_id}/contacts", response_model=List[PropertyContactResponse])
async def list_contacts(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all contacts for a property."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContact).where(PropertyContact.property_id == property_id)
    )
    return result.scalars().all()


@router.patch("/{property_id}/contacts/{contact_id}", response_model=PropertyContactResponse)
async def update_contact(
    property_id: int,
    contact_id: int,
    contact_data: PropertyContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a contact."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContact).where(
            PropertyContact.id == contact_id,
            PropertyContact.property_id == property_id
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    update_data = contact_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/{property_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    property_id: int,
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a contact."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContact).where(
            PropertyContact.id == contact_id,
            PropertyContact.property_id == property_id
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    await db.delete(contact)
    await db.commit()
    return None


# ============ Contract CRUD ============

@router.post("/{property_id}/contracts", response_model=PropertyContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    property_id: int,
    contract_data: PropertyContractCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a contract to a property."""
    await get_property_or_404(property_id, current_user, db)

    contract = PropertyContract(
        **contract_data.model_dump(),
        property_id=property_id,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


@router.get("/{property_id}/contracts", response_model=List[PropertyContractResponse])
async def list_contracts(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all contracts for a property."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContract).where(PropertyContract.property_id == property_id)
    )
    return result.scalars().all()


@router.patch("/{property_id}/contracts/{contract_id}", response_model=PropertyContractResponse)
async def update_contract(
    property_id: int,
    contract_id: int,
    contract_data: PropertyContractUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a contract."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContract).where(
            PropertyContract.id == contract_id,
            PropertyContract.property_id == property_id
        )
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    update_data = contract_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contract, field, value)

    await db.commit()
    await db.refresh(contract)
    return contract


@router.delete("/{property_id}/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    property_id: int,
    contract_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a contract."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContract).where(
            PropertyContract.id == contract_id,
            PropertyContract.property_id == property_id
        )
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    await db.delete(contract)
    await db.commit()
    return None


# ============ Phase CRUD ============

@router.post("/{property_id}/phases", response_model=PropertyPhaseResponse, status_code=status.HTTP_201_CREATED)
async def create_phase(
    property_id: int,
    phase_data: PropertyPhaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a phase to a property."""
    await get_property_or_404(property_id, current_user, db)

    phase = PropertyPhase(
        **phase_data.model_dump(),
        property_id=property_id,
    )
    db.add(phase)
    await db.commit()
    await db.refresh(phase)
    return phase


@router.get("/{property_id}/phases", response_model=List[PropertyPhaseResponse])
async def list_phases(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all phases for a property, ordered by order field."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhase)
        .where(PropertyPhase.property_id == property_id)
        .order_by(PropertyPhase.order)
    )
    return result.scalars().all()


@router.patch("/{property_id}/phases/{phase_id}", response_model=PropertyPhaseResponse)
async def update_phase(
    property_id: int,
    phase_id: int,
    phase_data: PropertyPhaseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a phase."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhase).where(
            PropertyPhase.id == phase_id,
            PropertyPhase.property_id == property_id
        )
    )
    phase = result.scalar_one_or_none()

    if not phase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phase not found")

    update_data = phase_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(phase, field, value)

    await db.commit()
    await db.refresh(phase)
    return phase


@router.delete("/{property_id}/phases/{phase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phase(
    property_id: int,
    phase_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a phase."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhase).where(
            PropertyPhase.id == phase_id,
            PropertyPhase.property_id == property_id
        )
    )
    phase = result.scalar_one_or_none()

    if not phase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phase not found")

    await db.delete(phase)
    await db.commit()
    return None


# ============ Note CRUD ============

@router.post("/{property_id}/notes", response_model=PropertyNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    property_id: int,
    note_data: PropertyNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a note to a property.

    Notes can optionally be associated with a contact by providing contact_id.
    If contact_id is provided, the note is attributed to that contact.
    Otherwise, it's attributed to the authenticated user.
    """
    await get_property_or_404(property_id, current_user, db)

    # Validate contact_id if provided
    if note_data.contact_id:
        result = await db.execute(
            select(PropertyContact).where(
                PropertyContact.id == note_data.contact_id,
                PropertyContact.property_id == property_id
            )
        )
        contact = result.scalar_one_or_none()
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found for this property"
            )

    note = PropertyNote(
        title=note_data.title,
        content=note_data.content,
        property_id=property_id,
        created_by_id=current_user.id if not note_data.contact_id else None,
        contact_id=note_data.contact_id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("/{property_id}/notes", response_model=List[PropertyNoteResponse])
async def list_notes(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all notes for a property, ordered by most recent first."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyNote)
        .where(PropertyNote.property_id == property_id)
        .order_by(PropertyNote.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{property_id}/notes/{note_id}", response_model=PropertyNoteWithContact)
async def get_note(
    property_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific property note with contact details if applicable."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyNote)
        .options(selectinload(PropertyNote.contact))
        .where(
            PropertyNote.id == note_id,
            PropertyNote.property_id == property_id
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    return note


@router.patch("/{property_id}/notes/{note_id}", response_model=PropertyNoteResponse)
async def update_note(
    property_id: int,
    note_id: int,
    note_data: PropertyNoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a property note."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyNote).where(
            PropertyNote.id == note_id,
            PropertyNote.property_id == property_id
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    update_data = note_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/{property_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    property_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a property note."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyNote).where(
            PropertyNote.id == note_id,
            PropertyNote.property_id == property_id
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    await db.delete(note)
    await db.commit()
    return None


# ============ DocuSeal Integration ============

async def get_contract_or_404(
    property_id: int,
    contract_id: int,
    user: User,
    db: AsyncSession
) -> PropertyContract:
    """Get contract by ID, checking property ownership."""
    await get_property_or_404(property_id, user, db)

    result = await db.execute(
        select(PropertyContract).where(
            PropertyContract.id == contract_id,
            PropertyContract.property_id == property_id
        )
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    return contract


@router.get("/docuseal/templates", response_model=List[DocuSealTemplate])
async def list_docuseal_templates(
    current_user: User = Depends(get_current_user),
):
    """List available DocuSeal templates."""
    try:
        service = DocuSealService()
        templates = await service.list_templates()
        return [
            DocuSealTemplate(
                id=t.get("id"),
                name=t.get("name"),
                created_at=t.get("created_at")
            )
            for t in templates
        ]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="DocuSeal API error")


@router.post("/{property_id}/contracts/{contract_id}/docuseal/send", response_model=DocuSealSubmissionResponse)
async def send_contract_for_signing(
    property_id: int,
    contract_id: int,
    request: DocuSealSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a contract for signing via DocuSeal."""
    contract = await get_contract_or_404(property_id, contract_id, current_user, db)

    if contract.docuseal_submission_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contract already has a DocuSeal submission"
        )

    try:
        service = DocuSealService()
        signers = [{
            "email": request.signer_email,
            "name": request.signer_name or request.signer_email,
        }]

        result = await service.create_submission(
            template_id=request.template_id,
            signers=signers,
        )

        # Handle different response structures
        submission_id = result.get("id") or result.get("submission_id")
        submission_status = result.get("status", "pending")

        # Get signing URL from submitters if available
        signing_url = None
        submitters = result.get("submitters", [])
        if submitters and len(submitters) > 0:
            signing_url = submitters[0].get("embed_src") or submitters[0].get("signing_url")

        # Update contract with DocuSeal info
        contract.docuseal_template_id = request.template_id
        contract.docuseal_submission_id = submission_id
        contract.docuseal_status = submission_status
        contract.signer_email = request.signer_email
        contract.status = ContractStatus.PENDING

        await db.commit()
        await db.refresh(contract)

        return DocuSealSubmissionResponse(
            submission_id=submission_id,
            status=submission_status,
            signing_url=signing_url
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="DocuSeal API error")


@router.get("/{property_id}/contracts/{contract_id}/docuseal/status", response_model=PropertyContractResponse)
async def sync_docuseal_status(
    property_id: int,
    contract_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check and sync DocuSeal submission status for a contract."""
    contract = await get_contract_or_404(property_id, contract_id, current_user, db)

    if not contract.docuseal_submission_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contract has no DocuSeal submission"
        )

    try:
        service = DocuSealService()
        result = await service.get_submission(contract.docuseal_submission_id)

        new_status = result.get("status", contract.docuseal_status)
        contract.docuseal_status = new_status

        # Map to contract status
        mapped_status = map_docuseal_status_to_contract_status(new_status)
        contract.status = ContractStatus(mapped_status)

        # Check for completion and get document URL
        if new_status.lower() in ("completed", "signed"):
            contract.signed_at = datetime.utcnow()
            # Try to get the signed document URL
            docs = result.get("documents", [])
            if docs and len(docs) > 0:
                contract.docuseal_document_url = docs[0].get("url")

        await db.commit()
        await db.refresh(contract)
        return contract

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="DocuSeal API error")


# ============ Phone Calls (Vapi Integration) ============

@router.post("/{property_id}/calls", response_model=PhoneCallInitiateResponse, status_code=status.HTTP_201_CREATED)
async def initiate_phone_call(
    property_id: int,
    call_data: PhoneCallCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate an AI-powered phone call for a property.

    The call will have full context about the property and optionally a specific contact.
    The AI will handle the conversation based on the provided purpose.
    """
    property = await get_property_or_404(property_id, current_user, db, load_relations=True)

    # If contact_id provided, validate and get contact info
    contact = None
    if call_data.contact_id:
        result = await db.execute(
            select(PropertyContact).where(
                PropertyContact.id == call_data.contact_id,
                PropertyContact.property_id == property_id
            )
        )
        contact = result.scalar_one_or_none()
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found for this property"
            )

    # Build context for the AI
    full_address = ", ".join(filter(None, [
        property.address, property.city, property.state, property.zip_code
    ]))

    context = {
        "property_id": property.id,
        "property_name": property.name,
        "property_address": full_address or None,
        "property_type": property.property_type,
        "property_status": property.status.value if property.status else None,
        "property_description": property.description,
        "contact_id": contact.id if contact else None,
        "contact_name": contact.name if contact else None,
        "contact_type": contact.contact_type.value if contact else None,
        "contact_company": contact.company if contact else None,
        "additional_context": call_data.additional_context,
    }

    try:
        service = VapiService()
        result = await service.create_call(
            phone_number=call_data.phone_number,
            purpose=call_data.purpose,
            context=context,
            assistant_id=call_data.assistant_id,
            first_message=call_data.first_message,
        )

        # Get call ID from response
        vapi_call_id = result.get("id")
        if not vapi_call_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get call ID from Vapi"
            )

        # Create phone call record
        import json
        phone_call = PropertyPhoneCall(
            property_id=property_id,
            contact_id=call_data.contact_id,
            initiated_by_id=current_user.id,
            vapi_call_id=vapi_call_id,
            phone_number=call_data.phone_number,
            purpose=call_data.purpose,
            status=CallStatus.QUEUED,
            call_context=json.dumps(context),
        )
        db.add(phone_call)
        await db.commit()
        await db.refresh(phone_call)

        return PhoneCallInitiateResponse(
            call_id=phone_call.id,
            vapi_call_id=vapi_call_id,
            status=result.get("status", "queued"),
            message=f"Call initiated to {call_data.phone_number}"
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Vapi API error")


@router.get("/{property_id}/calls", response_model=List[PhoneCallResponse])
async def list_phone_calls(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all phone calls for a property, ordered by most recent first."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhoneCall)
        .where(PropertyPhoneCall.property_id == property_id)
        .order_by(PropertyPhoneCall.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{property_id}/calls/{call_id}", response_model=PhoneCallWithContact)
async def get_phone_call(
    property_id: int,
    call_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific phone call."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhoneCall)
        .options(selectinload(PropertyPhoneCall.contact))
        .where(
            PropertyPhoneCall.id == call_id,
            PropertyPhoneCall.property_id == property_id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    return call


@router.get("/{property_id}/calls/{call_id}/sync", response_model=PhoneCallResponse)
async def sync_call_status(
    property_id: int,
    call_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Sync call status and transcript from Vapi."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhoneCall).where(
            PropertyPhoneCall.id == call_id,
            PropertyPhoneCall.property_id == property_id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    try:
        service = VapiService()
        vapi_call = await service.get_call(call.vapi_call_id)

        # Update status
        vapi_status = vapi_call.get("status", "")
        if vapi_status:
            status_map = {
                "queued": CallStatus.QUEUED,
                "ringing": CallStatus.RINGING,
                "in-progress": CallStatus.IN_PROGRESS,
                "ended": CallStatus.ENDED,
                "failed": CallStatus.FAILED,
                "busy": CallStatus.FAILED,
                "no-answer": CallStatus.NO_ANSWER,
            }
            call.status = status_map.get(vapi_status.lower(), call.status)

        # Update timestamps
        if vapi_call.get("startedAt"):
            call.started_at = datetime.fromisoformat(vapi_call["startedAt"].replace("Z", "+00:00"))
        if vapi_call.get("endedAt"):
            call.ended_at = datetime.fromisoformat(vapi_call["endedAt"].replace("Z", "+00:00"))

        # Calculate duration
        if call.started_at and call.ended_at:
            call.duration_seconds = int((call.ended_at - call.started_at).total_seconds())

        # Update transcript
        if vapi_call.get("transcript"):
            call.transcript = vapi_call["transcript"]

        # Update summary if available
        if vapi_call.get("summary"):
            call.summary = vapi_call["summary"]

        # Update recording URL
        if vapi_call.get("recordingUrl"):
            call.recording_url = vapi_call["recordingUrl"]

        await db.commit()
        await db.refresh(call)
        return call

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Vapi API error")


@router.patch("/{property_id}/calls/{call_id}", response_model=PhoneCallResponse)
async def update_phone_call(
    property_id: int,
    call_id: int,
    call_data: PhoneCallUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update call outcome and follow-up notes after call ends."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhoneCall).where(
            PropertyPhoneCall.id == call_id,
            PropertyPhoneCall.property_id == property_id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    update_data = call_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(call, field, value)

    await db.commit()
    await db.refresh(call)
    return call


@router.post("/{property_id}/calls/{call_id}/end", response_model=PhoneCallResponse)
async def end_phone_call(
    property_id: int,
    call_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """End an active phone call."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyPhoneCall).where(
            PropertyPhoneCall.id == call_id,
            PropertyPhoneCall.property_id == property_id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    if call.status == CallStatus.ENDED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Call already ended")

    try:
        service = VapiService()
        await service.end_call(call.vapi_call_id)

        call.status = CallStatus.ENDED
        call.ended_at = datetime.utcnow()

        await db.commit()
        await db.refresh(call)
        return call

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Call already ended on Vapi side
            call.status = CallStatus.ENDED
            await db.commit()
            await db.refresh(call)
            return call
        raise HTTPException(status_code=e.response.status_code, detail="Vapi API error")


@router.post("/{property_id}/contacts/{contact_id}/call", response_model=PhoneCallInitiateResponse, status_code=status.HTTP_201_CREATED)
async def call_contact(
    property_id: int,
    contact_id: int,
    purpose: str,
    additional_context: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Quick endpoint to call a property contact using their stored phone number.
    """
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContact).where(
            PropertyContact.id == contact_id,
            PropertyContact.property_id == property_id
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact has no phone number")

    # Create call data using contact's phone
    call_data = PhoneCallCreate(
        phone_number=contact.phone,
        purpose=purpose,
        contact_id=contact_id,
        additional_context=additional_context,
    )

    # Delegate to main call endpoint
    return await initiate_phone_call(property_id, call_data, current_user, db)


# ============ SMS (Twilio Integration) ============

@router.post("/{property_id}/sms", response_model=SMSSendResponse, status_code=status.HTTP_201_CREATED)
async def send_sms(
    property_id: int,
    sms_data: SMSCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send an SMS message related to a property.

    The message can optionally be linked to a contact.
    """
    await get_property_or_404(property_id, current_user, db)

    # If contact_id provided, validate
    contact = None
    if sms_data.contact_id:
        result = await db.execute(
            select(PropertyContact).where(
                PropertyContact.id == sms_data.contact_id,
                PropertyContact.property_id == property_id
            )
        )
        contact = result.scalar_one_or_none()
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found for this property"
            )

    try:
        service = get_twilio_service()
        result = await service.send_sms(
            to_number=sms_data.phone_number,
            message=sms_data.message,
            media_urls=sms_data.media_urls,
        )

        # Store media URLs as JSON
        import json
        media_urls_json = json.dumps(sms_data.media_urls) if sms_data.media_urls else None

        # Create SMS record
        sms = PropertySMS(
            property_id=property_id,
            contact_id=sms_data.contact_id,
            sent_by_id=current_user.id,
            twilio_message_sid=result["message_sid"],
            phone_number=sms_data.phone_number,
            from_number=result["from"],
            to_number=result["to"],
            body=sms_data.message,
            media_urls=media_urls_json,
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.SENT if result["status"] in ("sent", "delivered") else SMSStatus.QUEUED,
            sent_at=result.get("date_sent") or datetime.utcnow(),
        )
        db.add(sms)
        await db.commit()
        await db.refresh(sms)

        return SMSSendResponse(
            sms_id=sms.id,
            twilio_message_sid=result["message_sid"],
            status=result["status"],
            message=f"SMS sent to {sms_data.phone_number}"
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Twilio error: {str(e)}")


@router.get("/{property_id}/sms", response_model=List[SMSResponse])
async def list_sms(
    property_id: int,
    phone_number: Optional[str] = None,
    direction: Optional[SMSDirection] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List SMS messages for a property, optionally filtered by phone number or direction."""
    await get_property_or_404(property_id, current_user, db)

    query = select(PropertySMS).where(PropertySMS.property_id == property_id)

    if phone_number:
        query = query.where(PropertySMS.phone_number == phone_number)
    if direction:
        query = query.where(PropertySMS.direction == direction)

    query = query.order_by(PropertySMS.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{property_id}/sms/{sms_id}", response_model=SMSWithContact)
async def get_sms(
    property_id: int,
    sms_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific SMS message."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertySMS)
        .options(selectinload(PropertySMS.contact))
        .where(
            PropertySMS.id == sms_id,
            PropertySMS.property_id == property_id
        )
    )
    sms = result.scalar_one_or_none()

    if not sms:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SMS not found")

    return sms


@router.get("/{property_id}/sms/{sms_id}/sync", response_model=SMSResponse)
async def sync_sms_status(
    property_id: int,
    sms_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Sync SMS status from Twilio."""
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertySMS).where(
            PropertySMS.id == sms_id,
            PropertySMS.property_id == property_id
        )
    )
    sms = result.scalar_one_or_none()

    if not sms:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SMS not found")

    try:
        service = get_twilio_service()
        twilio_msg = await service.get_message(sms.twilio_message_sid)

        # Map Twilio status to our status
        status_map = {
            "queued": SMSStatus.QUEUED,
            "sending": SMSStatus.SENDING,
            "sent": SMSStatus.SENT,
            "delivered": SMSStatus.DELIVERED,
            "failed": SMSStatus.FAILED,
            "undelivered": SMSStatus.FAILED,
            "received": SMSStatus.RECEIVED,
        }
        twilio_status = twilio_msg.get("status", "").lower()
        if twilio_status in status_map:
            sms.status = status_map[twilio_status]

        # Update error info if failed
        if twilio_msg.get("error_code"):
            sms.error_code = str(twilio_msg["error_code"])
            sms.error_message = twilio_msg.get("error_message")

        await db.commit()
        await db.refresh(sms)
        return sms

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Twilio error: {str(e)}")


@router.get("/{property_id}/sms/conversations", response_model=List[SMSConversation])
async def list_sms_conversations(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all SMS conversations (grouped by phone number) for a property."""
    await get_property_or_404(property_id, current_user, db)

    # Get all unique phone numbers with their latest message
    from sqlalchemy import func, distinct

    # First get all distinct phone numbers with their message counts
    result = await db.execute(
        select(
            PropertySMS.phone_number,
            PropertySMS.contact_id,
            func.count(PropertySMS.id).label("message_count"),
            func.max(PropertySMS.created_at).label("last_message_at")
        )
        .where(PropertySMS.property_id == property_id)
        .group_by(PropertySMS.phone_number, PropertySMS.contact_id)
        .order_by(func.max(PropertySMS.created_at).desc())
    )
    rows = result.all()

    conversations = []
    for row in rows:
        # Get the last message for this phone number
        last_msg_result = await db.execute(
            select(PropertySMS)
            .where(
                PropertySMS.property_id == property_id,
                PropertySMS.phone_number == row.phone_number
            )
            .order_by(PropertySMS.created_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        # Get contact name if available
        contact_name = None
        if row.contact_id:
            contact_result = await db.execute(
                select(PropertyContact).where(PropertyContact.id == row.contact_id)
            )
            contact = contact_result.scalar_one_or_none()
            if contact:
                contact_name = contact.name

        conversations.append(SMSConversation(
            phone_number=row.phone_number,
            contact_id=row.contact_id,
            contact_name=contact_name,
            message_count=row.message_count,
            last_message=last_msg,
            last_message_at=row.last_message_at
        ))

    return conversations


@router.post("/{property_id}/contacts/{contact_id}/sms", response_model=SMSSendResponse, status_code=status.HTTP_201_CREATED)
async def text_contact(
    property_id: int,
    contact_id: int,
    message: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Quick endpoint to text a property contact using their stored phone number.
    """
    await get_property_or_404(property_id, current_user, db)

    result = await db.execute(
        select(PropertyContact).where(
            PropertyContact.id == contact_id,
            PropertyContact.property_id == property_id
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact has no phone number")

    # Create SMS data using contact's phone
    sms_data = SMSCreate(
        phone_number=contact.phone,
        message=message,
        contact_id=contact_id,
    )

    # Delegate to main SMS endpoint
    return await send_sms(property_id, sms_data, current_user, db)
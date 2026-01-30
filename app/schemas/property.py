from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, EmailStr

from app.models.property import PropertyStatus, ContactType, ContractStatus, ContractType, PhaseStatus, CallStatus, SMSStatus, SMSDirection


# ============ Contact Schemas ============

class PropertyContactBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    contact_type: ContactType = ContactType.OTHER
    notes: Optional[str] = None


class PropertyContactCreate(PropertyContactBase):
    pass


class PropertyContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    contact_type: Optional[ContactType] = None
    notes: Optional[str] = None


class PropertyContactResponse(PropertyContactBase):
    id: int
    property_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Contract Schemas ============

class PropertyContractBase(BaseModel):
    title: str
    contract_type: ContractType = ContractType.OTHER
    status: ContractStatus = ContractStatus.DRAFT
    description: Optional[str] = None
    value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    vendor_name: Optional[str] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


class PropertyContractCreate(PropertyContractBase):
    pass


class PropertyContractUpdate(BaseModel):
    title: Optional[str] = None
    contract_type: Optional[ContractType] = None
    status: Optional[ContractStatus] = None
    description: Optional[str] = None
    value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    vendor_name: Optional[str] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


class PropertyContractResponse(PropertyContractBase):
    id: int
    property_id: int
    # DocuSeal fields
    docuseal_template_id: Optional[int] = None
    docuseal_submission_id: Optional[int] = None
    docuseal_status: Optional[str] = None
    docuseal_document_url: Optional[str] = None
    signer_email: Optional[str] = None
    signed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ DocuSeal Schemas ============

class DocuSealTemplate(BaseModel):
    id: int
    name: str
    created_at: Optional[datetime] = None


class DocuSealSendRequest(BaseModel):
    template_id: int
    signer_email: str
    signer_name: Optional[str] = None


class DocuSealSubmissionResponse(BaseModel):
    submission_id: int
    status: str
    signing_url: Optional[str] = None


# ============ Phase Schemas ============

class PropertyPhaseBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: PhaseStatus = PhaseStatus.NOT_STARTED
    order: int = 0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None


class PropertyPhaseCreate(PropertyPhaseBase):
    pass


class PropertyPhaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[PhaseStatus] = None
    order: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None


class PropertyPhaseResponse(PropertyPhaseBase):
    id: int
    property_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Note Schemas ============

class PropertyNoteBase(BaseModel):
    title: str
    content: Optional[str] = None


class PropertyNoteCreate(PropertyNoteBase):
    contact_id: Optional[int] = None


class PropertyNoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class PropertyNoteResponse(PropertyNoteBase):
    id: int
    property_id: int
    created_by_id: Optional[int] = None
    contact_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PropertyNoteWithContact(PropertyNoteResponse):
    contact: Optional[PropertyContactResponse] = None


# ============ Phone Call Schemas ============

class PhoneCallCreate(BaseModel):
    """Request to initiate a phone call."""
    phone_number: str  # E.164 format: +1234567890
    purpose: str  # Brief description of call purpose
    contact_id: Optional[int] = None  # Link to a property contact
    additional_context: Optional[str] = None  # Extra context for the AI
    first_message: Optional[str] = None  # Custom greeting
    assistant_id: Optional[str] = None  # Vapi assistant ID (optional)


class PhoneCallResponse(BaseModel):
    id: int
    property_id: int
    contact_id: Optional[int] = None
    initiated_by_id: int
    vapi_call_id: str
    phone_number: str
    purpose: str
    status: CallStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    recording_url: Optional[str] = None
    outcome: Optional[str] = None
    follow_up_required: bool = False
    follow_up_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PhoneCallWithContact(PhoneCallResponse):
    contact: Optional[PropertyContactResponse] = None


class PhoneCallUpdate(BaseModel):
    """Update call outcome/notes after call ends."""
    outcome: Optional[str] = None
    follow_up_required: Optional[bool] = None
    follow_up_notes: Optional[str] = None


class PhoneCallInitiateResponse(BaseModel):
    """Response when initiating a call."""
    call_id: int
    vapi_call_id: str
    status: str
    message: str


# ============ SMS Schemas ============

class SMSCreate(BaseModel):
    """Request to send an SMS message."""
    phone_number: str  # E.164 format: +1234567890
    message: str  # Message body
    contact_id: Optional[int] = None  # Link to a property contact
    media_urls: Optional[List[str]] = None  # Optional media URLs for MMS


class SMSResponse(BaseModel):
    """Response model for SMS messages."""
    id: int
    property_id: int
    contact_id: Optional[int] = None
    sent_by_id: Optional[int] = None
    twilio_message_sid: str
    phone_number: str
    from_number: str
    to_number: str
    body: str
    media_urls: Optional[str] = None
    direction: SMSDirection
    status: SMSStatus
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SMSWithContact(SMSResponse):
    """SMS response with contact details."""
    contact: Optional[PropertyContactResponse] = None


class SMSSendResponse(BaseModel):
    """Response when sending an SMS."""
    sms_id: int
    twilio_message_sid: str
    status: str
    message: str


class SMSConversation(BaseModel):
    """A conversation thread with a phone number."""
    phone_number: str
    contact_id: Optional[int] = None
    contact_name: Optional[str] = None
    message_count: int
    last_message: Optional[SMSResponse] = None
    last_message_at: Optional[datetime] = None


# ============ Property Schemas ============

class PropertyBase(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = "USA"
    description: Optional[str] = None
    property_type: Optional[str] = None
    status: PropertyStatus = PropertyStatus.PROSPECTING
    status_note: Optional[str] = None


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None
    status: Optional[PropertyStatus] = None
    status_note: Optional[str] = None


class PropertyResponse(PropertyBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PropertyWithDetails(PropertyResponse):
    contacts: List[PropertyContactResponse] = []
    contracts: List[PropertyContractResponse] = []
    phases: List[PropertyPhaseResponse] = []
    notes: List[PropertyNoteResponse] = []


class PropertyList(BaseModel):
    properties: List[PropertyResponse]
    total: int


# ============ Address Autocomplete Schemas ============

class AddressPrediction(BaseModel):
    """A single address autocomplete suggestion."""
    place_id: str
    description: str
    main_text: Optional[str] = None
    secondary_text: Optional[str] = None


class AddressAutocompleteResponse(BaseModel):
    """Response for address autocomplete."""
    predictions: List[AddressPrediction]


class AddressDetails(BaseModel):
    """Full address details from Google Places."""
    place_id: str
    formatted_address: str
    address: Optional[str] = None  # Street address
    city: Optional[str] = None
    state: Optional[str] = None
    state_short: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PropertyCreateFromPlace(BaseModel):
    """Create property from Google Place selection."""
    place_id: str
    name: Optional[str] = None  # If not provided, uses formatted_address
    property_type: Optional[str] = None
    description: Optional[str] = None
    status: PropertyStatus = PropertyStatus.PROSPECTING


# ============ Enrichment Schemas ============

class PropertyEnrichmentResponse(BaseModel):
    """Property enrichment data."""
    id: int
    property_id: int

    # Property details
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    living_area: Optional[int] = None
    lot_size: Optional[int] = None
    year_built: Optional[int] = None
    home_type: Optional[str] = None

    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    county: Optional[str] = None

    # Valuation
    zestimate: Optional[int] = None
    zestimate_low: Optional[int] = None
    zestimate_high: Optional[int] = None
    rent_zestimate: Optional[int] = None
    tax_assessed_value: Optional[int] = None

    # Status
    price: Optional[int] = None
    price_per_sqft: Optional[float] = None
    home_status: Optional[str] = None

    # Features
    has_pool: Optional[bool] = None
    has_garage: Optional[bool] = None
    has_basement: Optional[bool] = None

    # Metadata
    enriched_at: Optional[datetime] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class PropertyWithEnrichment(PropertyResponse):
    """Property with enrichment data included."""
    enrichment: Optional[PropertyEnrichmentResponse] = None

    class Config:
        from_attributes = True


class PropertyWithFullDetails(PropertyWithDetails):
    """Property with all details including enrichment."""
    enrichment: Optional[PropertyEnrichmentResponse] = None

    class Config:
        from_attributes = True


# ============ Research Schemas ============

class ResearchStatus(str, Enum):
    """Research status enum for schema."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PropertyResearchRequest(BaseModel):
    """Request to start property research."""
    brand_name: str = "Property Intelligence"
    intended_use: str = "BUY/HOLD"
    owner_hypothesis: Optional[str] = None
    seed_sources: Optional[str] = None
    force: bool = False


class PropertyResearchSummary(BaseModel):
    """Summary of property research results."""
    id: int
    property_id: int
    status: str
    brand_name: Optional[str] = None
    intended_use: Optional[str] = None

    # Key extracted fields
    normalized_address: Optional[str] = None
    county: Optional[str] = None
    block_lot: Optional[str] = None
    current_owner: Optional[str] = None
    assessed_value: Optional[int] = None
    zoning_classification: Optional[str] = None
    value_estimate_low: Optional[int] = None
    value_estimate_high: Optional[int] = None

    # Risk scores (0-10)
    risk_title: Optional[int] = None
    risk_tax: Optional[int] = None
    risk_permit: Optional[int] = None
    risk_environmental: Optional[int] = None
    risk_market: Optional[int] = None
    risk_neighborhood: Optional[int] = None

    # Error info
    error_message: Optional[str] = None

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PropertyResearchFull(PropertyResearchSummary):
    """Full property research including the dossier JSON."""
    dossier: Optional[dict] = None

    class Config:
        from_attributes = True


class RiskScores(BaseModel):
    """Risk scores extracted from research."""
    title: Optional[int] = None
    tax: Optional[int] = None
    permit: Optional[int] = None
    environmental: Optional[int] = None
    market: Optional[int] = None
    neighborhood: Optional[int] = None
    overall: Optional[float] = None  # Average of all scores

from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SQLEnum, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PropertyStatus(str, Enum):
    """Property status."""
    PROSPECTING = "prospecting"
    UNDER_CONTRACT = "under_contract"
    IN_DEVELOPMENT = "in_development"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"


class ContactType(str, Enum):
    """Contact type for property contacts."""
    OWNER = "owner"
    MANAGER = "manager"
    CONTRACTOR = "contractor"
    AGENT = "agent"
    TENANT = "tenant"
    VENDOR = "vendor"
    OTHER = "other"


class ContractStatus(str, Enum):
    """Contract status."""
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ContractType(str, Enum):
    """Contract type."""
    PURCHASE = "purchase"
    LEASE = "lease"
    SERVICE = "service"
    CONSTRUCTION = "construction"
    MANAGEMENT = "management"
    OTHER = "other"


class PhaseStatus(str, Enum):
    """Phase status."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"


class CallStatus(str, Enum):
    """Phone call status."""
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    ENDED = "ended"
    FAILED = "failed"
    NO_ANSWER = "no_answer"


class SMSStatus(str, Enum):
    """SMS message status."""
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RECEIVED = "received"  # For inbound messages


class SMSDirection(str, Enum):
    """SMS direction."""
    OUTBOUND = "outbound"
    INBOUND = "inbound"


if TYPE_CHECKING:
    from app.models.user import User


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="USA")

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    property_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # residential, commercial, land, etc.

    status: Mapped[PropertyStatus] = mapped_column(
        SQLEnum(PropertyStatus), default=PropertyStatus.PROSPECTING
    )
    status_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Owner of this property record
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="properties")
    contacts: Mapped[List["PropertyContact"]] = relationship("PropertyContact", back_populates="property", cascade="all, delete-orphan")
    contracts: Mapped[List["PropertyContract"]] = relationship("PropertyContract", back_populates="property", cascade="all, delete-orphan")
    phases: Mapped[List["PropertyPhase"]] = relationship("PropertyPhase", back_populates="property", cascade="all, delete-orphan")
    notes: Mapped[List["PropertyNote"]] = relationship("PropertyNote", back_populates="property", cascade="all, delete-orphan")
    phone_calls: Mapped[List["PropertyPhoneCall"]] = relationship("PropertyPhoneCall", back_populates="property", cascade="all, delete-orphan")
    sms_messages: Mapped[List["PropertySMS"]] = relationship("PropertySMS", back_populates="property", cascade="all, delete-orphan")
    enrichment: Mapped[Optional["PropertyEnrichment"]] = relationship("PropertyEnrichment", back_populates="property", uselist=False, cascade="all, delete-orphan")
    research: Mapped[Optional["PropertyResearch"]] = relationship("PropertyResearch", back_populates="property", uselist=False, cascade="all, delete-orphan")


class PropertyContact(Base):
    __tablename__ = "property_contacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)

    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_type: Mapped[ContactType] = mapped_column(SQLEnum(ContactType), default=ContactType.OTHER)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="contacts")
    property_notes: Mapped[List["PropertyNote"]] = relationship("PropertyNote", back_populates="contact")
    phone_calls: Mapped[List["PropertyPhoneCall"]] = relationship("PropertyPhoneCall", back_populates="contact")
    sms_messages: Mapped[List["PropertySMS"]] = relationship("PropertySMS", back_populates="contact")


class PropertyContract(Base):
    __tablename__ = "property_contracts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)

    title: Mapped[str] = mapped_column(String(255))
    contract_type: Mapped[ContractType] = mapped_column(SQLEnum(ContractType), default=ContractType.OTHER)
    status: Mapped[ContractStatus] = mapped_column(SQLEnum(ContractStatus), default=ContractStatus.DRAFT)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # DocuSeal Integration
    docuseal_template_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    docuseal_submission_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    docuseal_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    docuseal_document_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    signer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="contracts")


class PropertyPhase(Base):
    __tablename__ = "property_phases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[PhaseStatus] = mapped_column(SQLEnum(PhaseStatus), default=PhaseStatus.NOT_STARTED)

    order: Mapped[int] = mapped_column(Integer, default=0)  # For ordering phases

    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="phases")


class PropertyNote(Base):
    __tablename__ = "property_notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)

    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Creator: either user OR contact (not both)
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("property_contacts.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="notes")
    created_by: Mapped[Optional["User"]] = relationship("User")
    contact: Mapped[Optional["PropertyContact"]] = relationship("PropertyContact", back_populates="property_notes")


class PropertyPhoneCall(Base):
    __tablename__ = "property_phone_calls"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("property_contacts.id"), nullable=True, index=True)
    initiated_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    # Vapi call info
    vapi_call_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(50))

    # Call details
    purpose: Mapped[str] = mapped_column(String(500))
    status: Mapped[CallStatus] = mapped_column(SQLEnum(CallStatus), default=CallStatus.QUEUED)

    # Call metadata
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Transcript and summary
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recording_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Additional context sent to AI
    call_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Outcome tracking
    outcome: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # e.g., "scheduled_meeting", "left_voicemail", etc.
    follow_up_required: Mapped[bool] = mapped_column(default=False)
    follow_up_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="phone_calls")
    contact: Mapped[Optional["PropertyContact"]] = relationship("PropertyContact", back_populates="phone_calls")
    initiated_by: Mapped["User"] = relationship("User")


class PropertySMS(Base):
    __tablename__ = "property_sms"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("property_contacts.id"), nullable=True, index=True)
    sent_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)  # Null for inbound

    # Twilio message info
    twilio_message_sid: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(50))  # The external phone number
    from_number: Mapped[str] = mapped_column(String(50))  # Sender number
    to_number: Mapped[str] = mapped_column(String(50))  # Recipient number

    # Message content
    body: Mapped[str] = mapped_column(Text)
    media_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of media URLs

    # Message metadata
    direction: Mapped[SMSDirection] = mapped_column(SQLEnum(SMSDirection), default=SMSDirection.OUTBOUND)
    status: Mapped[SMSStatus] = mapped_column(SQLEnum(SMSStatus), default=SMSStatus.QUEUED)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Timing
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="sms_messages")
    contact: Mapped[Optional["PropertyContact"]] = relationship("PropertyContact", back_populates="sms_messages")
    sent_by: Mapped[Optional["User"]] = relationship("User")


class PropertyEnrichment(Base):
    """Stores enriched property data from external Zillow-style database."""
    __tablename__ = "property_enrichments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), unique=True, index=True)

    # Zillow identifiers
    zpid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    parcel_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Property details
    bedrooms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[Optional[float]] = mapped_column(Numeric(4, 1), nullable=True)
    living_area: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # sqft
    lot_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # sqft
    year_built: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    home_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    property_subtype: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Location
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    county_fips: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Valuation
    zestimate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    zestimate_low: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    zestimate_high: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rent_zestimate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tax_assessed_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tax_annual_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    # Pricing
    price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_per_sqft: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    home_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # FOR_SALE, RECENTLY_SOLD, etc.

    # Property features (stored as JSON)
    photos: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of photo URLs
    price_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    tax_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    schools: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    home_facts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON object
    realty_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON - agent/broker info

    # Additional features
    has_pool: Mapped[Optional[bool]] = mapped_column(default=False)
    has_garage: Mapped[Optional[bool]] = mapped_column(default=False)
    has_basement: Mapped[Optional[bool]] = mapped_column(default=False)
    has_cooling: Mapped[Optional[bool]] = mapped_column(default=False)
    has_heating: Mapped[Optional[bool]] = mapped_column(default=False)
    parking_spaces: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stories: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Neighborhood data
    neighborhood: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    walk_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transit_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bike_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Raw data
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Full JSON from source

    # Metadata
    enriched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="zillow")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="enrichment")


class ResearchStatus(str, Enum):
    """Property research status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PropertyResearch(Base):
    """
    Stores comprehensive due diligence research for a property.

    Generated by AI deep research, includes:
    - Identity validation (parcel, block/lot, tax IDs)
    - Ownership & title timeline
    - Tax & assessment history
    - Permits, zoning, violations
    - Market comps & valuation
    - Neighborhood intelligence
    - Risk scorecard
    """
    __tablename__ = "property_research"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), unique=True, index=True)

    # Research metadata
    status: Mapped[ResearchStatus] = mapped_column(SQLEnum(ResearchStatus), default=ResearchStatus.PENDING)
    brand_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    intended_use: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="BUY/HOLD")

    # The full research dossier as JSON
    dossier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Key extracted fields for quick access
    normalized_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    block_lot: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assessed_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    zoning_classification: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    value_estimate_low: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    value_estimate_high: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Risk scores (0-10)
    risk_title: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_tax: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_permit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_environmental: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_market: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_neighborhood: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="research")

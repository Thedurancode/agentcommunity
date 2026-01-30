from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Code Live OS"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./codeliveos.db"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def convert_postgres_url(cls, v: str) -> str:
        """Convert Fly.io postgres:// to postgresql+asyncpg:// for SQLAlchemy async"""
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg doesn't support sslmode parameter, remove it
        if "sslmode=" in v:
            # Remove sslmode parameter from URL
            import re
            v = re.sub(r'[?&]sslmode=[^&]*', '', v)
            # Clean up any trailing ? or &
            v = v.rstrip('?&')
        return v

    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 525600 * 10  # 10 years

    # GitHub Integration
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: Optional[str] = None

    # AI Integration (Anthropic Claude)
    ANTHROPIC_API_KEY: Optional[str] = None
    AI_MODEL: str = "claude-sonnet-4-20250514"

    # OpenAI (for Whisper transcription)
    OPENAI_API_KEY: Optional[str] = None

    # DocuSeal Integration
    DOCUSEAL_API_KEY: Optional[str] = None
    DOCUSEAL_API_URL: str = "https://api.docuseal.co"

    # Vapi Integration (Voice AI Phone Calls)
    VAPI_API_KEY: Optional[str] = None
    VAPI_API_URL: str = "https://api.vapi.ai"
    VAPI_PHONE_NUMBER_ID: Optional[str] = None  # Your Vapi phone number ID
    VAPI_ASSISTANT_ID: Optional[str] = None  # Default assistant ID (optional)

    # Twilio Integration (SMS)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None  # Your Twilio phone number in E.164 format

    # Google Places API (for address autocomplete)
    GOOGLE_PLACES_API_KEY: Optional[str] = None

    # Property Enrichment Database (External PostgreSQL with Zillow data)
    ENRICHMENT_DATABASE_URL: Optional[str] = None

    # Resend (Email Service)
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM_EMAIL: Optional[str] = None  # e.g., "reports@yourdomain.com"

    @field_validator("ENRICHMENT_DATABASE_URL", mode="after")
    @classmethod
    def convert_enrichment_postgres_url(cls, v: Optional[str]) -> Optional[str]:
        """Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy async"""
        if v is None:
            return v
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg doesn't support sslmode parameter, remove it
        if "sslmode=" in v:
            import re
            v = re.sub(r'[?&]sslmode=[^&]*', '', v)
            v = v.rstrip('?&')
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

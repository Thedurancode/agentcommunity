from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token, verify_api_key
from app.models.user import User, UserRole
from app.models.api_key import APIKey


security = HTTPBearer(auto_error=False)


async def _get_user_from_api_key(api_key: str, db: AsyncSession) -> Optional[User]:
    """Validate API key and return associated user."""
    if not api_key.startswith("clak_"):
        return None

    # Get prefix for lookup (first 12 chars including prefix)
    key_prefix = api_key[:12]

    result = await db.execute(
        select(APIKey).where(
            APIKey.key_prefix == key_prefix,
            APIKey.is_active == True
        )
    )
    api_key_record = result.scalar_one_or_none()

    if api_key_record is None:
        return None

    # Verify the full key hash
    if not verify_api_key(api_key, api_key_record.key_hash):
        return None

    # Update last used timestamp
    api_key_record.last_used_at = datetime.utcnow()
    await db.commit()

    # Get the user
    user_result = await db.execute(select(User).where(User.id == api_key_record.user_id))
    return user_result.scalar_one_or_none()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> User:
    user = None

    # Try API key first
    if x_api_key:
        user = await _get_user_from_api_key(x_api_key, db)
        if user and user.is_active:
            return user
        elif user and not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user",
            )

    # Fall back to JWT Bearer token
    if credentials:
        token = credentials.credentials
        payload = decode_token(token)
        if payload is not None:
            user_id = payload.get("sub")
            if user_id is not None:
                result = await db.execute(select(User).where(User.id == int(user_id)))
                user = result.scalar_one_or_none()

                if user is not None:
                    if not user.is_active:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Inactive user",
                        )
                    return user

    # No valid auth found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def get_optional_user():
    async def _get_optional_user(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
        db: AsyncSession = Depends(get_db)
    ) -> Optional[User]:
        if credentials is None:
            return None
        try:
            token = credentials.credentials
            payload = decode_token(token)
            if payload is None:
                return None
            user_id = payload.get("sub")
            if user_id is None:
                return None
            result = await db.execute(select(User).where(User.id == int(user_id)))
            return result.scalar_one_or_none()
        except Exception:
            return None
    return _get_optional_user

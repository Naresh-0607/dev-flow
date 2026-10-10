from datetime import datetime, timezone
import hashlib
from typing import Annotated
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey, User

api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """Generate SHA-256 hex digest for an API key string."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def get_current_user(
    request: Request,
    raw_api_key: Annotated[str | None, Security(api_key_header_scheme)],
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate request via X-API-Key header.
    
    -------------------------------------------------------------------------
    NOTE (Phase D Web-Session Extension Point):
    When web sessions are introduced in Phase D, check session cookies here
    if X-API-Key is not present.
    -------------------------------------------------------------------------
    """
    if not raw_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    key_hash = hash_api_key(raw_api_key)
    api_key_record = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        .first()
    )

    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )

    # Track last used timestamp
    api_key_record.last_used_at = datetime.now(timezone.utc)
    db.commit()

    # Attach key record to request state for endpoints that need key metadata
    request.state.api_key = api_key_record

    user = db.query(User).filter(User.id == api_key_record.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with API key not found",
        )

    return user

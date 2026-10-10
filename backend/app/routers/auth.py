from typing import Annotated
from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user
from app.models import User
from app.schemas import WhoamiResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/whoami", response_model=WhoamiResponse, summary="Verify authenticated user and key")
def whoami(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> WhoamiResponse:
    """Return current user's username and the label of the API key used for the request."""
    api_key = getattr(request.state, "api_key", None)
    key_label = api_key.label if api_key else "unknown"
    return WhoamiResponse(
        username=current_user.username,
        key_label=key_label,
    )

from typing import Annotated
from fastapi import APIRouter, Body, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import EventBatchResult, EventCreate
from app.services.event_service import process_batch_events, process_single_event

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", summary="Record a git event")
def create_event(
    event: EventCreate,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """Record a git event idempotently. Returns 201 for new events, 200 for duplicates."""
    res, status_code = process_single_event(db=db, user=current_user, event=event)
    response.status_code = status_code
    return res


@router.post("/batch", summary="Batch record git events", response_model=list[EventBatchResult])
def create_events_batch(
    events: Annotated[list[EventCreate], Body(max_length=500)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[EventBatchResult]:
    """Process a batch of up to 500 git events independently."""
    return process_batch_events(db=db, user=current_user, events=events)

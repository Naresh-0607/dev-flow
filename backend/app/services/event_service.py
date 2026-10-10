import hashlib
from typing import Any
from sqlalchemy.orm import Session

from app.models import Branch, Event, Project, User
from app.schemas import EventBatchResult, EventCreate


def calculate_dedupe_key(
    project_id: int,
    event_type: str,
    branch_name: str,
    commit_hash: str | None,
    occurred_at_iso: str,
) -> str:
    """Generate SHA-256 dedupe key: project_id|type|branch_name|commit_hash-or-empty|occurred_at."""
    hash_payload = f"{project_id}|{event_type}|{branch_name}|{commit_hash or ''}|{occurred_at_iso}"
    return hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()


def process_single_event(
    db: Session,
    user: User,
    event: EventCreate,
    auto_commit: bool = True,
) -> tuple[dict[str, Any], int]:
    """
    Process an incoming git event:
    - Get or create Project for current user.
    - Get or create Branch under project.
    - Check dedupe key for idempotency (return 200 {"status": "duplicate"}).
    - Update branch activity and commit info (only advancing last_activity_at).
    - Maintain single active branch rule on checkout.
    - Persist Event row and return 201 {"status": "created", "event_id": ...}.
    """
    identity_key = event.remote_url if event.remote_url else event.repo_path

    # Get or create project
    project = (
        db.query(Project)
        .filter(Project.owner_id == user.id, Project.identity_key == identity_key)
        .first()
    )
    if not project:
        project = Project(
            owner_id=user.id,
            name=event.project,
            repo_path=event.repo_path,
            remote_url=event.remote_url,
            identity_key=identity_key,
        )
        db.add(project)
        db.flush()

    branch_name = event.branch or "(detached)"

    # Get or create branch
    branch = (
        db.query(Branch)
        .filter(Branch.project_id == project.id, Branch.name == branch_name)
        .first()
    )
    if not branch:
        branch = Branch(
            project_id=project.id,
            name=branch_name,
            last_commit_hash=event.commit_hash,
            last_commit_message=event.message,
            last_commit_author=event.author,
            last_activity_at=event.timestamp,
            is_active=True,
        )
        db.add(branch)
        db.flush()

    # Calculate dedupe key
    dedupe_key = calculate_dedupe_key(
        project_id=project.id,
        event_type=event.type,
        branch_name=branch_name,
        commit_hash=event.commit_hash,
        occurred_at_iso=event.timestamp.isoformat(),
    )

    # Check for duplicate event
    existing_event = db.query(Event).filter(Event.dedupe_key == dedupe_key).first()
    if existing_event:
        return {"status": "duplicate"}, 200

    # Advance branch last_activity_at only forward
    if event.timestamp > branch.last_activity_at:
        branch.last_activity_at = event.timestamp

    # Handle event-type-specific logic
    if event.type == "commit":
        branch.last_commit_hash = event.commit_hash
        branch.last_commit_message = event.message
        branch.last_commit_author = event.author
        branch.is_active = True

    elif event.type == "checkout":
        # Mark active branch and ensure only one active branch per project
        db.query(Branch).filter(
            Branch.project_id == project.id,
            Branch.id != branch.id,
        ).update({Branch.is_active: False}, synchronize_session=False)

        branch.is_active = True

    # Create new event record
    raw_payload = event.model_dump(mode="json")
    new_event = Event(
        project_id=project.id,
        branch_id=branch.id,
        branch_name=branch_name,
        type=event.type,
        commit_hash=event.commit_hash,
        message=event.message,
        author=event.author,
        payload=raw_payload,
        occurred_at=event.timestamp,
        dedupe_key=dedupe_key,
    )
    db.add(new_event)

    if auto_commit:
        db.commit()
        db.refresh(new_event)
    else:
        db.flush()

    return {"status": "created", "event_id": new_event.id}, 201


def process_batch_events(
    db: Session,
    user: User,
    events: list[EventCreate],
) -> list[EventBatchResult]:
    """Process up to 500 events independently using savepoints."""
    results: list[EventBatchResult] = []

    for idx, event in enumerate(events):
        try:
            with db.begin_nested():
                res, _ = process_single_event(
                    db=db,
                    user=user,
                    event=event,
                    auto_commit=False,
                )
                results.append(
                    EventBatchResult(
                        index=idx,
                        status=res["status"],
                        event_id=res.get("event_id"),
                    )
                )
        except Exception as exc:
            results.append(
                EventBatchResult(
                    index=idx,
                    status="error",
                    detail=str(exc),
                )
            )

    db.commit()
    return results

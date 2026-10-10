from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Branch, Event, Project, User
from app.schemas import BranchSummary, EventSummary, ProjectDetail, ProjectSummary

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectSummary], summary="List current user's projects")
def list_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[ProjectSummary]:
    """Retrieve all projects owned by the authenticated user with aggregate stats."""
    # Subquery for branch counts and last activity timestamps
    branch_stats = (
        db.query(
            Branch.project_id.label("project_id"),
            func.count(Branch.id).label("branch_count"),
            func.max(Branch.last_activity_at).label("last_activity_at"),
        )
        .group_by(Branch.project_id)
        .subquery()
    )

    # Subquery for active branch name
    active_branches = (
        db.query(
            Branch.project_id.label("project_id"),
            Branch.name.label("active_branch"),
        )
        .filter(Branch.is_active.is_(True))
        .subquery()
    )

    rows = (
        db.query(
            Project,
            func.coalesce(branch_stats.c.branch_count, 0).label("branch_count"),
            active_branches.c.active_branch,
            branch_stats.c.last_activity_at,
        )
        .outerjoin(branch_stats, Project.id == branch_stats.c.project_id)
        .outerjoin(active_branches, Project.id == active_branches.c.project_id)
        .filter(Project.owner_id == current_user.id)
        .order_by(branch_stats.c.last_activity_at.desc().nulls_last())
        .all()
    )

    results: list[ProjectSummary] = []
    for project, branch_count, active_branch, last_activity_at in rows:
        results.append(
            ProjectSummary(
                id=project.id,
                name=project.name,
                repo_path=project.repo_path,
                remote_url=project.remote_url,
                identity_key=project.identity_key,
                created_at=project.created_at,
                branch_count=branch_count,
                active_branch=active_branch,
                last_activity_at=last_activity_at,
            )
        )
    return results


@router.get("/projects/{project_id}", response_model=ProjectDetail, summary="Get project details")
def get_project(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectDetail:
    """Retrieve a single project by ID if owned by current user."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    branch_count = (
        db.query(func.count(Branch.id))
        .filter(Branch.project_id == project.id)
        .scalar()
        or 0
    )
    active_branch = (
        db.query(Branch.name)
        .filter(Branch.project_id == project.id, Branch.is_active.is_(True))
        .first()
    )
    last_activity_at = (
        db.query(func.max(Branch.last_activity_at))
        .filter(Branch.project_id == project.id)
        .scalar()
    )

    return ProjectDetail(
        id=project.id,
        owner_id=project.owner_id,
        name=project.name,
        repo_path=project.repo_path,
        remote_url=project.remote_url,
        identity_key=project.identity_key,
        created_at=project.created_at,
        branch_count=branch_count,
        active_branch=active_branch[0] if active_branch else None,
        last_activity_at=last_activity_at,
    )


@router.get(
    "/projects/{project_id}/branches",
    response_model=list[BranchSummary],
    summary="List branches for a project",
)
def list_branches(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Optional branch name search query"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[BranchSummary]:
    """Retrieve branches belonging to a project, ordered newest activity first."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    query = db.query(Branch).filter(Branch.project_id == project.id)
    if q:
        query = query.filter(Branch.name.ilike(f"%{q.strip()}%"))

    branches = (
        query.order_by(Branch.last_activity_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [BranchSummary.model_validate(b) for b in branches]


@router.get(
    "/branches/{branch_id}/events",
    response_model=list[EventSummary],
    summary="Get event timeline for a branch",
)
def list_branch_events(
    branch_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[EventSummary]:
    """Retrieve event history for a branch, ordered newest first (max limit 200)."""
    branch = (
        db.query(Branch)
        .join(Project, Branch.project_id == Project.id)
        .filter(Branch.id == branch_id, Project.owner_id == current_user.id)
        .first()
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch {branch_id} not found",
        )

    events = (
        db.query(Event)
        .filter(Event.branch_id == branch.id)
        .order_by(Event.occurred_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [EventSummary.model_validate(e) for e in events]

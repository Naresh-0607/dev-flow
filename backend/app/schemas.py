from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import EventType


class EventCreate(BaseModel):
    """Schema for incoming git event."""
    model_config = ConfigDict(extra="allow")

    type: str = Field(..., description="Event type: commit, checkout, merge, scan")
    project: str = Field(..., min_length=1, description="Project name")
    repo_path: str = Field(..., min_length=1, description="Local absolute path to repository")
    remote_url: str | None = Field(default=None, description="Remote Git URL if configured")
    branch: str | None = Field(default=None, description="Branch name or null/empty for detached HEAD")
    commit_hash: str | None = Field(default=None, description="Git commit hash")
    message: str | None = Field(default=None, description="Commit message")
    author: str | None = Field(default=None, description="Author identifier")
    timestamp: datetime = Field(..., description="Time event occurred (must be timezone-aware)")
    previous_branch: str | None = Field(default=None, description="Previous branch when checking out")

    @field_validator("project")
    @classmethod
    def validate_project(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("project must not be empty or whitespace only")
        return trimmed

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("repo_path must not be empty or whitespace only")
        return trimmed

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        valid_types = {e.value for e in EventType}
        if value not in valid_types:
            raise ValueError(f"type must be one of {sorted(valid_types)}")
        return value

    @field_validator("branch")
    @classmethod
    def normalize_branch(cls, value: str | None) -> str:
        if value is None or not value.strip():
            return "(detached)"
        return value.strip()

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_has_tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset")
        return value


class EventResponse(BaseModel):
    """Response returned after processing a git event."""
    status: str
    event_id: int | None = None


class EventBatchResult(BaseModel):
    """Result for an individual event within a batch request."""
    index: int
    status: str
    event_id: int | None = None
    detail: str | None = None


class WhoamiResponse(BaseModel):
    """Response containing authenticated user and key information."""
    username: str
    key_label: str


class ProjectSummary(BaseModel):
    """Summary representation of a project for list endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    repo_path: str
    remote_url: str | None
    identity_key: str
    created_at: datetime
    branch_count: int
    active_branch: str | None
    last_activity_at: datetime | None


class ProjectDetail(ProjectSummary):
    """Detailed representation of a single project."""
    owner_id: int


class BranchSummary(BaseModel):
    """Summary representation of a git branch."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    last_commit_hash: str | None
    last_commit_message: str | None
    last_commit_author: str | None
    last_activity_at: datetime
    is_active: bool
    created_at: datetime


class EventSummary(BaseModel):
    """Representation of an individual git event."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    branch_id: int | None
    branch_name: str
    type: str
    commit_hash: str | None
    message: str | None
    author: str | None
    payload: dict[str, Any]
    occurred_at: datetime
    received_at: datetime

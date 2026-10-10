from datetime import datetime, timezone
import enum
from typing import Any
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class EventType(str, enum.Enum):
    """Supported git event types."""
    COMMIT = "commit"
    CHECKOUT = "checkout"
    MERGE = "merge"
    SCAN = "scan"


class User(Base):
    """User account model."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    """Project repository tracked for a user."""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    repo_path: Mapped[str] = mapped_column(String(500), nullable=False)
    remote_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    identity_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    owner: Mapped["User"] = relationship("User", back_populates="projects")
    branches: Mapped[list["Branch"]] = relationship("Branch", back_populates="project", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship("Event", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("owner_id", "identity_key", name="uq_projects_owner_identity"),
    )


class Branch(Base):
    """Branch within a tracked project."""
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_commit_author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="branches")
    events: Mapped[list["Event"]] = relationship("Event", back_populates="branch")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_branches_project_name"),
    )


class Event(Base):
    """Git event recorded for a project and branch."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), index=True, nullable=True)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="events")
    branch: Mapped["Branch | None"] = relationship("Branch", back_populates="events")

    __table_args__ = (
        Index("ix_events_branch_id_occurred_at", "branch_id", occurred_at.desc()),
    )


class ApiKey(Base):
    """API key associated with a user for agent authentication."""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="api_keys")

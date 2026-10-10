from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 database models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session and closing it on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

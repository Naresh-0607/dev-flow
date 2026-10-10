from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import ApiKey, User
from app.services.user_service import create_api_key, create_user

# Strict safety verification: database URL MUST end with '_test'
if not settings.TEST_DATABASE_URL.endswith("_test"):
    raise RuntimeError(
        f"ABORTING TEST RUN: TEST_DATABASE_URL '{settings.TEST_DATABASE_URL}' does not end with '_test'. "
        "Tests are strictly forbidden from running against non-test databases!"
    )

test_engine = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    """Create all database tables in devflow_test for the test session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    # Keep schema intact for test inspection if needed


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    """Clean all tables between individual tests to ensure complete isolation."""
    yield
    with test_engine.connect() as conn:
        with conn.begin():
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a database session bound to the test database."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient instance with get_db overridden to use devflow_test."""
    def _override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user_factory(db_session: Session):
    """Factory fixture for creating test users with API keys."""
    def _create(
        username: str = "testuser",
        label: str = "testkey",
    ) -> tuple[User, str]:
        user = create_user(db=db_session, username=username)
        _, raw_key = create_api_key(db=db_session, user=user, label=label)
        return user, raw_key

    return _create

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ApiKey
from app.services.user_service import validate_username


def test_whoami_with_valid_key(client: TestClient, user_factory):
    """GET /auth/whoami returns the correct username and key label."""
    user, api_key = user_factory(username="validuser", label="laptop-dev")
    response = client.get("/auth/whoami", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "validuser"
    assert data["key_label"] == "laptop-dev"


def test_whoami_missing_key(client: TestClient):
    """GET /auth/whoami returns 401 when X-API-Key header is omitted."""
    response = client.get("/auth/whoami")
    assert response.status_code == 401
    assert "Missing API key" in response.json()["detail"]


def test_whoami_invalid_key(client: TestClient):
    """GET /auth/whoami returns 401 when an unknown API key is provided."""
    response = client.get("/auth/whoami", headers={"X-API-Key": "df_badkey1234567890"})
    assert response.status_code == 401
    assert "Invalid or inactive API key" in response.json()["detail"]


def test_whoami_inactive_key(client: TestClient, db_session: Session, user_factory):
    """GET /auth/whoami returns 401 when the API key is deactivated."""
    user, api_key = user_factory(username="inactiveuser", label="revoked")
    
    # Deactivate the key
    key_record = db_session.query(ApiKey).filter(ApiKey.user_id == user.id).first()
    key_record.is_active = False
    db_session.commit()

    response = client.get("/auth/whoami", headers={"X-API-Key": api_key})
    assert response.status_code == 401
    assert "Invalid or inactive API key" in response.json()["detail"]


def test_username_validation_reserved_names(db_session: Session):
    """Reserved system usernames must be rejected."""
    reserved = ["admin", "api", "login", "logout", "settings", "me", "www", "devflow", "support"]
    for name in reserved:
        with pytest.raises(ValueError, match="reserved"):
            validate_username(name, db=db_session)


def test_username_validation_uppercase_letters(db_session: Session):
    """Usernames with uppercase characters must be rejected."""
    invalid_cases = ["Naresh", "DEVFLOW", "MyUser"]
    for name in invalid_cases:
        with pytest.raises(ValueError, match="uppercase"):
            validate_username(name, db=db_session)


def test_username_validation_length(db_session: Session):
    """Usernames shorter than 3 or longer than 30 characters must be rejected."""
    with pytest.raises(ValueError, match="between 3 and 30"):
        validate_username("ab", db=db_session)

    with pytest.raises(ValueError, match="between 3 and 30"):
        validate_username("a" * 31, db=db_session)


def test_username_validation_characters(db_session: Session):
    """Usernames containing invalid symbols must be rejected."""
    invalid_cases = ["user@flow", "user_name", "user.name", "user name"]
    for name in invalid_cases:
        with pytest.raises(ValueError, match="letters, numbers, and dashes"):
            validate_username(name, db=db_session)


def test_username_validation_duplicates(user_factory, db_session: Session):
    """Duplicate usernames must be rejected."""
    user_factory(username="existinguser")
    with pytest.raises(ValueError, match="already exists"):
        validate_username("existinguser", db=db_session)

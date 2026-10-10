import re
import secrets
from sqlalchemy.orm import Session

from app.auth import hash_api_key
from app.models import ApiKey, User

RESERVED_USERNAMES = {
    "admin",
    "api",
    "login",
    "logout",
    "settings",
    "me",
    "www",
    "devflow",
    "support",
}

USERNAME_REGEX = re.compile(r"^[a-z0-9-]+$")


def validate_username(username: str, db: Session | None = None) -> str:
    """
    Validate username according to specifications:
    1. No uppercase letters
    2. Not in reserved usernames list
    3. 3-30 characters long
    4. Only lowercase letters, digits, and hyphens
    5. Unique across users (if db session provided)
    """
    if any(c.isupper() for c in username):
        raise ValueError("Username must not contain uppercase letters")

    if username.lower() in RESERVED_USERNAMES:
        raise ValueError(f"'{username}' is a reserved username")

    if len(username) < 3 or len(username) > 30:
        raise ValueError("Username length must be between 3 and 30 characters")

    if not USERNAME_REGEX.match(username):
        raise ValueError("Username can only contain letters, numbers, and dashes")

    if db is not None:
        existing = db.query(User).filter(User.username == username.lower()).first()
        if existing:
            raise ValueError(f"Username '{username}' already exists")

    return username.lower()


def create_user(
    db: Session,
    username: str,
    email: str | None = None,
    is_public: bool = False,
) -> User:
    """Create and persist a new user after validation."""
    validated_username = validate_username(username, db=db)
    user = User(
        username=validated_username,
        email=email,
        is_public=is_public,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_api_key(
    db: Session,
    user: User,
    label: str = "default",
) -> tuple[ApiKey, str]:
    """
    Generate an API key for a user:
    - format: 'df_' + secrets.token_urlsafe(32)
    - key_prefix: first 8 chars
    - key_hash: sha256 hex
    Returns (ApiKey record, plaintext_key).
    """
    plaintext_key = f"df_{secrets.token_urlsafe(32)}"
    key_prefix = plaintext_key[:8]
    key_hash = hash_api_key(plaintext_key)

    api_key = ApiKey(
        user_id=user.id,
        label=label,
        key_prefix=key_prefix,
        key_hash=key_hash,
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return api_key, plaintext_key

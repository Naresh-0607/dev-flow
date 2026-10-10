import argparse
import sys
from pathlib import Path

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db import SessionLocal
from app.services.user_service import create_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new DevFlow user")
    parser.add_argument("username", help="Username (3-30 chars, lowercase, digits, hyphens)")
    parser.add_argument("--email", default=None, help="Optional user email")
    parser.add_argument("--public", action="store_true", help="Set user profile to public")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = create_user(
            db=db,
            username=args.username,
            email=args.email,
            is_public=args.public,
        )
        print(f"Successfully created user: {user.username} (ID: {user.id})")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

import argparse
import sys
from pathlib import Path

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db import SessionLocal
from app.models import User
from app.services.user_service import create_api_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new API key for a DevFlow user")
    parser.add_argument("username", help="Target username")
    parser.add_argument("--label", default="default", help="Descriptive label for the API key (e.g. laptop)")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username.lower()).first()
        if not user:
            print(f"Error: User '{args.username}' not found", file=sys.stderr)
            sys.exit(1)

        api_key, plaintext_key = create_api_key(db=db, user=user, label=args.label)
        print(f"API key created for '{user.username}' (ID: {user.id})")
        print(f"Label: {api_key.label}")
        print(f"Key Prefix: {api_key.key_prefix}")
        print(f"API Key: {plaintext_key}")
        print("IMPORTANT: Save this key now! The plaintext will not be shown again.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

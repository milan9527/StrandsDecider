"""Create, reset or disable a self-managed account without a public registration API."""

import argparse
import getpass
import json
import os
import secrets
from pathlib import Path

from app.auth import canonical_username, configured_store, save_user


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "reset", "disable"])
    parser.add_argument("username")
    parser.add_argument(
        "--generate-to",
        type=Path,
        help="Generate a strong password and save credentials to a new mode-0600 JSON file",
    )
    args = parser.parse_args()
    username = canonical_username(args.username)
    store = configured_store()
    if args.action == "disable":
        user = store.get("USER#" + username)
        if not user:
            parser.error("Account does not exist")
        user["enabled"] = False
        user["version"] = secrets.token_hex(16)
        store.put(user)
    else:
        if args.action == "reset" and not store.get("USER#" + username):
            parser.error("Account does not exist")
        if args.generate_to:
            args.generate_to.parent.mkdir(parents=True, exist_ok=True)
            # Never overwrite an existing credentials file.
            fd = os.open(args.generate_to, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            password = secrets.token_urlsafe(24)
            with os.fdopen(fd, "w") as file:
                json.dump({"username": username, "password": password}, file)
                file.write("\n")
        else:
            password = getpass.getpass("Password (12–128 characters): ")
            if password != getpass.getpass("Confirm password: "):
                parser.error("Passwords do not match")
        save_user(store, username, password, reset=args.action == "reset")
    print(f"Account {args.action} completed: {username}")


if __name__ == "__main__":
    main()

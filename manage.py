#!/usr/bin/env python3
"""Command-line account management — for the deployment/server team.

Lets an operator create, list, and manage user accounts directly on the
server without going through the web UI. Passwords are still hashed with
bcrypt (the exact same function the running app uses) before they ever
touch the database — this script exists so the *operator* only ever types
a plain password once, at the prompt; it never has to be hashed by hand
and it is never written to disk in plain text.

Connects to the same database the app itself uses:
  - If db_config.py exists next to this file (the org's production path),
    its DB_CONFIG is used.
  - Otherwise, falls back to the same POSTGRES_*/DATABASE_URL settings the
    app reads from .env (local/dev/Docker path).

Usage:
    python3 manage.py list-users
    python3 manage.py create-user --username alice --role user
    python3 manage.py reset-password --username alice
    python3 manage.py deactivate-user --username alice
    python3 manage.py activate-user --username alice
    python3 manage.py set-role --username alice --role admin

Passwords are always prompted for interactively (getpass) so they never
appear in shell history, `ps`, or terminal scrollback. Run this from the
backend folder with the same venv the app uses (it needs psycopg2, already
a dependency in requirements.txt).
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg2
import psycopg2.extras

from app.core.security import hash_password  # exact same hashing the app uses


# ─── Connection ────────────────────────────────────────────────────────
def _connection_kwargs() -> dict:
    """Same source-of-truth precedence the app itself uses: db_config.py
    (production, filled in by the deployment team) if present, otherwise
    the .env-driven Settings (local/dev/Docker)."""
    try:
        from db_config import DB_CONFIG  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        if DB_CONFIG.get("host") != "CHANGE_ME":
            return {
                "dbname": DB_CONFIG["dbname"],
                "user": DB_CONFIG["user"],
                "password": DB_CONFIG["password"],
                "host": DB_CONFIG["host"],
                "port": DB_CONFIG["port"],
            }

    from app.core.config import settings

    return {
        "dbname": settings.POSTGRES_DB,
        "user": settings.POSTGRES_USER,
        "password": settings.POSTGRES_PASSWORD,
        "host": settings.POSTGRES_HOST,
        "port": settings.POSTGRES_PORT,
    }


def _connect():
    try:
        return psycopg2.connect(**_connection_kwargs())
    except Exception as exc:
        print(f"Could not connect to the database: {exc}", file=sys.stderr)
        print(
            "Check db_config.py (or .env) has the right host/user/password/dbname.",
            file=sys.stderr,
        )
        sys.exit(1)


# ─── Guards (mirrors app/api/auth/users.py's _guard_last_admin) ────────
def _count_other_active_admins(cur, exclude_user_id: int | None) -> int:
    cur.execute(
        """
        SELECT COUNT(*) FROM users
        WHERE role = 'admin' AND status = 'active'
          AND (%s::int IS NULL OR id != %s)
        """,
        (exclude_user_id, exclude_user_id),
    )
    return cur.fetchone()[0]


def _get_user(cur, username: str):
    cur.execute(
        "SELECT id, username, email, role, status FROM users WHERE username = %s",
        (username,),
    )
    return cur.fetchone()


# ─── Commands ────────────────────────────────────────────────────────
def cmd_list_users(args, cur) -> None:
    cur.execute(
        "SELECT id, username, email, role, status, created_at, last_login_at "
        "FROM users ORDER BY id"
    )
    rows = cur.fetchall()
    if not rows:
        print("No users found.")
        return
    print(f"{'ID':<5}{'USERNAME':<20}{'ROLE':<8}{'STATUS':<12}{'EMAIL':<30}LAST LOGIN")
    for r in rows:
        uid, username, email, role, status, created_at, last_login_at = r
        print(
            f"{uid:<5}{username:<20}{role:<8}{status:<12}{(email or ''):<30}"
            f"{last_login_at or 'never'}"
        )


def cmd_create_user(args, cur) -> None:
    if _get_user(cur, args.username):
        print(f"User '{args.username}' already exists.", file=sys.stderr)
        sys.exit(1)

    role = args.role or "user"
    if role not in ("user", "admin"):
        print("Role must be 'user' or 'admin'.", file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass(f"Password for '{args.username}': ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        sys.exit(1)
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    pw_hash = hash_password(password)
    cur.execute(
        """
        INSERT INTO users (username, email, full_name, password_hash, role,
                            status, must_change_password)
        VALUES (%s, %s, %s, %s, %s, 'active', TRUE)
        RETURNING id
        """,
        (args.username, args.email or "", args.full_name or "", pw_hash, role),
    )
    new_id = cur.fetchone()[0]
    print(f"Created user '{args.username}' (id={new_id}, role={role}). "
          f"They will be prompted to change their password on first login.")


def cmd_reset_password(args, cur) -> None:
    user = _get_user(cur, args.username)
    if not user:
        print(f"No such user: {args.username}", file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass(f"New password for '{args.username}': ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        sys.exit(1)
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    pw_hash = hash_password(password)
    cur.execute(
        "UPDATE users SET password_hash = %s, must_change_password = TRUE "
        "WHERE username = %s",
        (pw_hash, args.username),
    )
    print(f"Password reset for '{args.username}'. "
          f"They will be prompted to change it again on next login.")


def cmd_deactivate_user(args, cur) -> None:
    user = _get_user(cur, args.username)
    if not user:
        print(f"No such user: {args.username}", file=sys.stderr)
        sys.exit(1)
    uid, username, email, role, status = user

    if role == "admin" and status == "active":
        remaining = _count_other_active_admins(cur, exclude_user_id=uid)
        if remaining == 0:
            print(
                "Refusing: this is the last active admin — promote another "
                "admin first, otherwise nobody could administer the system.",
                file=sys.stderr,
            )
            sys.exit(1)

    cur.execute("UPDATE users SET status = 'deactivated' WHERE username = %s", (username,))
    print(f"Deactivated '{username}'.")


def cmd_activate_user(args, cur) -> None:
    user = _get_user(cur, args.username)
    if not user:
        print(f"No such user: {args.username}", file=sys.stderr)
        sys.exit(1)
    cur.execute("UPDATE users SET status = 'active' WHERE username = %s", (args.username,))
    print(f"Activated '{args.username}'.")


def cmd_set_role(args, cur) -> None:
    user = _get_user(cur, args.username)
    if not user:
        print(f"No such user: {args.username}", file=sys.stderr)
        sys.exit(1)
    uid, username, email, role, status = user

    if args.role not in ("user", "admin"):
        print("Role must be 'user' or 'admin'.", file=sys.stderr)
        sys.exit(1)

    if role == "admin" and args.role == "user" and status == "active":
        remaining = _count_other_active_admins(cur, exclude_user_id=uid)
        if remaining == 0:
            print(
                "Refusing: this is the last active admin — promote another "
                "admin first, otherwise nobody could administer the system.",
                file=sys.stderr,
            )
            sys.exit(1)

    cur.execute("UPDATE users SET role = %s WHERE username = %s", (args.role, username))
    print(f"'{username}' is now role={args.role}.")


# ─── CLI wiring ──────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-users", help="List all accounts")
    p.set_defaults(func=cmd_list_users)

    p = sub.add_parser("create-user", help="Create a new account (prompts for password)")
    p.add_argument("--username", required=True)
    p.add_argument("--email", default="")
    p.add_argument("--full-name", default="")
    p.add_argument("--role", choices=["user", "admin"], default="user")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("reset-password", help="Reset an account's password (prompts)")
    p.add_argument("--username", required=True)
    p.set_defaults(func=cmd_reset_password)

    p = sub.add_parser("deactivate-user", help="Deactivate an account (refuses to lock out the last admin)")
    p.add_argument("--username", required=True)
    p.set_defaults(func=cmd_deactivate_user)

    p = sub.add_parser("activate-user", help="Re-activate a deactivated account")
    p.add_argument("--username", required=True)
    p.set_defaults(func=cmd_activate_user)

    p = sub.add_parser("set-role", help="Change an account's role (refuses to demote the last admin)")
    p.add_argument("--username", required=True)
    p.add_argument("--role", choices=["user", "admin"], required=True)
    p.set_defaults(func=cmd_set_role)

    args = parser.parse_args()

    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                args.func(args, cur)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

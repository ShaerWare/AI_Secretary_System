#!/usr/bin/env python3
"""CLI tool for user management.

Usage:
  python scripts/manage_users.py list
  python scripts/manage_users.py create <username> <password> [--role user|admin|guest]
  python scripts/manage_users.py delete <username>
  python scripts/manage_users.py set-password <username> <new_password>
  python scripts/manage_users.py set-role <username> <role>
  python scripts/manage_users.py disable <username>
  python scripts/manage_users.py enable <username>
"""

import argparse
import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.password import hash_password


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"
VALID_ROLES = ("guest", "web", "user", "admin")


def get_connection():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Run 'python scripts/migrate_users.py' first.")
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


def cmd_list(args):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, role, display_name, is_active, created, last_login FROM users ORDER BY id"
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No users found.")
        return

    print(
        f"{'ID':>4}  {'Username':<20} {'Role':<8} {'Active':<7} {'Display Name':<20} {'Last Login'}"
    )
    print("-" * 90)
    for row in rows:
        uid, username, role, display_name, is_active, _created, last_login = row
        active_str = "Yes" if is_active else "No"
        login_str = last_login or "Never"
        print(
            f"{uid:>4}  {username:<20} {role:<8} {active_str:<7} {(display_name or ''):<20} {login_str}"
        )

    print(f"\nTotal: {len(rows)} user(s)")


def cmd_create(args):
    if args.role not in VALID_ROLES:
        print(f"Invalid role: {args.role}. Must be one of {VALID_ROLES}")
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (args.username,))
    if cursor.fetchone():
        print(f"User '{args.username}' already exists.")
        conn.close()
        sys.exit(1)

    pw_hash, salt = hash_password(args.password)

    cursor.execute(
        """INSERT INTO users (username, password_hash, salt, role, display_name, is_active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (args.username, pw_hash, salt, args.role, args.username),
    )
    conn.commit()
    conn.close()
    print(f"Created user '{args.username}' with role '{args.role}'")


def cmd_delete(args):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, role FROM users WHERE username = ?", (args.username,))
    row = cursor.fetchone()
    if not row:
        print(f"User '{args.username}' not found.")
        conn.close()
        sys.exit(1)

    cursor.execute("DELETE FROM users WHERE username = ?", (args.username,))
    conn.commit()
    conn.close()
    print(f"Deleted user '{args.username}'")


def cmd_set_password(args):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (args.username,))
    if not cursor.fetchone():
        print(f"User '{args.username}' not found.")
        conn.close()
        sys.exit(1)

    pw_hash, salt = hash_password(args.password)

    cursor.execute(
        "UPDATE users SET password_hash = ?, salt = ?, updated = CURRENT_TIMESTAMP WHERE username = ?",
        (pw_hash, salt, args.username),
    )
    conn.commit()
    conn.close()
    print(f"Password updated for '{args.username}'")


def cmd_set_role(args):
    if args.role not in VALID_ROLES:
        print(f"Invalid role: {args.role}. Must be one of {VALID_ROLES}")
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (args.username,))
    if not cursor.fetchone():
        print(f"User '{args.username}' not found.")
        conn.close()
        sys.exit(1)

    cursor.execute(
        "UPDATE users SET role = ?, updated = CURRENT_TIMESTAMP WHERE username = ?",
        (args.role, args.username),
    )
    conn.commit()
    conn.close()
    print(f"Role updated for '{args.username}' -> '{args.role}'")


def cmd_toggle_active(args, active: bool):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (args.username,))
    if not cursor.fetchone():
        print(f"User '{args.username}' not found.")
        conn.close()
        sys.exit(1)

    cursor.execute(
        "UPDATE users SET is_active = ?, updated = CURRENT_TIMESTAMP WHERE username = ?",
        (1 if active else 0, args.username),
    )
    conn.commit()
    conn.close()
    status = "enabled" if active else "disabled"
    print(f"User '{args.username}' {status}")


def main():
    parser = argparse.ArgumentParser(description="AI Secretary - User Management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List all users")

    # create
    p_create = subparsers.add_parser("create", help="Create a new user")
    p_create.add_argument("username", help="Username")
    p_create.add_argument("password", help="Password")
    p_create.add_argument(
        "--role", default="user", choices=VALID_ROLES, help="User role (default: user)"
    )

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a user")
    p_delete.add_argument("username", help="Username to delete")

    # set-password
    p_pw = subparsers.add_parser("set-password", help="Change user password")
    p_pw.add_argument("username", help="Username")
    p_pw.add_argument("password", help="New password")

    # set-role
    p_role = subparsers.add_parser("set-role", help="Change user role")
    p_role.add_argument("username", help="Username")
    p_role.add_argument("role", choices=VALID_ROLES, help="New role")

    # disable
    p_dis = subparsers.add_parser("disable", help="Disable a user")
    p_dis.add_argument("username", help="Username to disable")

    # enable
    p_en = subparsers.add_parser("enable", help="Enable a user")
    p_en.add_argument("username", help="Username to enable")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "create":
        cmd_create(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "set-password":
        cmd_set_password(args)
    elif args.command == "set-role":
        cmd_set_role(args)
    elif args.command == "disable":
        cmd_toggle_active(args, active=False)
    elif args.command == "enable":
        cmd_toggle_active(args, active=True)


if __name__ == "__main__":
    main()

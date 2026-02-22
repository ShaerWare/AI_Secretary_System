"""Centralized password hashing — single source of truth.

Supports bcrypt (new) and SHA-256 (legacy, read-only for migration).
"""

import hashlib
import secrets

import bcrypt


def hash_password(password: str) -> tuple[str, str | None]:
    """Hash password with bcrypt.

    Returns:
        (password_hash, salt) — salt is None for bcrypt (embedded in hash).
    """
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    return pw_hash, None


def verify_password(password: str, stored_hash: str, salt: str | None = None) -> bool:
    """Verify password against stored hash.

    Supports both bcrypt ($2b$ prefix) and legacy SHA-256 + salt.
    """
    if stored_hash.startswith(("$2b$", "$2a$", "$2y$")):
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("ascii"))
    # Legacy: SHA-256 + salt
    if salt:
        legacy_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return legacy_hash == stored_hash
    # Legacy: unsalted SHA-256
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return legacy_hash == stored_hash


def needs_rehash(stored_hash: str) -> bool:
    """Check if password hash should be re-hashed to bcrypt."""
    return not stored_hash.startswith(("$2b$", "$2a$", "$2y$"))


def generate_salt() -> str:
    """Generate legacy salt (for backward compat only)."""
    return secrets.token_hex(32)

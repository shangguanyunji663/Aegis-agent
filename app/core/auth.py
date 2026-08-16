from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def random_id(prefix: str, size: int = 12) -> str:
    return f"{prefix}-{secrets.token_hex(size // 2)}"


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def make_password_hash(password: str, salt: str | None = None) -> tuple[str, str]:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 120_000)
    return salt_value, digest.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, digest = make_password_hash(password, salt)
    return hmac.compare_digest(digest, expected_hash)


def expires_after(hours: int) -> datetime:
    return utcnow() + timedelta(hours=hours)


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: str
    username: str
    role: str
    auth_session_id: str

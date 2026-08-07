"""Security primitives: JWT issuing/validation, OTP hashing, phone validation."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException

from app.config import settings

TokenPayload = dict


def normalize_phone(raw: str) -> str:
    """Validate an Indian phone number and return E.164 form."""
    try:
        parsed = phonenumbers.parse(raw, "IN")
    except NumberParseException as exc:
        raise ValueError("Invalid phone number") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def hash_otp(code: str) -> str:
    """HMAC-SHA256 hash of the OTP using the server secret."""
    return hmac.new(
        settings.jwt_secret.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


def generate_otp(length: int = 6) -> str:
    """Cryptographically secure numeric OTP (no leading-zero loss)."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(driver_id: int, token_type: str, minutes: int) -> str:
    now = _now()
    payload: dict = {
        "sub": str(driver_id),
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(driver_id: int) -> str:
    return create_token(driver_id, "access", settings.access_token_minutes)


def create_refresh_token(driver_id: int) -> str:
    return create_token(driver_id, "refresh", settings.refresh_token_days * 24 * 60)


def decode_token(token: str, expected_type: str) -> int:
    """Return the driver_id encoded in the token, raising on any failure."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if payload.get("type") != expected_type:
        raise ValueError("Invalid token type")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Malformed token subject") from exc

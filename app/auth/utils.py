import re
import secrets
import string
from datetime import datetime, timezone

import bcrypt
from flask import current_app, has_app_context

from app.auth.exceptions import WeakPasswordError

MIN_PASSWORD_LENGTH = 12   # NFR-SEC-16, for passwords a user chooses
TEMP_PASSWORD_LENGTH = 8   # generated, expiring, retyped from an SMS, so shorter is fine

#exclude characters that are easily confused with each other
_TEMP_PASSWORD_ALPHABET = "".join(
    c for c in (string.ascii_letters + string.digits) if c not in "0O1lI"
)

# make sure the phone number is in E.164 format. +254 and 07 numbers are the same
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_DIGITS_RE = re.compile(r"^\+?\d+$")

_dummy_hash = None

def utcnow() -> datetime:
    """
    Return a naive datetime in UTC
    Every timestamp column is naive thus cant mix aware and naive datetimes
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(
    plain_password:str
) -> str:
    """hash a pain text password using bcrypt and return a utf-8 encoded string for storage"""
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")

def verify_password(
    plain_password:str,
    password_hash:str
) -> bool:
    """Checks plaintext password against password hash"""
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False

def generate_temp_password(
    length:int = 8
) -> str:
    """Generate a random temporary password of specified length"""
    return ''.join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))

def normalize_phone(
    raw_phone:str
) -> str:
    """Normalize phone number to E.164 format (e.g., +1234567890)"""
    cleaned = re.sub(r"[\s\-()]", "", raw_phone or "")
    if not _PHONE_RE.match(cleaned):
        raise ValueError(f"Invalid phone number format: {raw_phone}")
    return cleaned
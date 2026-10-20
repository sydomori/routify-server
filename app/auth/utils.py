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

    # make passwords more secure by increasing the computational time the server uses to hash the password
    rounds = current_app.config.get("BCRYPT_ROUNDS", 12) if has_app_context() else 12
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=rounds))
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

def burn_password_check(plain_password: str) -> None:
    """
     Spend the same time a bcrypt check would, so a login from an unknown
     or deactivated account isn't faster than one for a real account 
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("timing-equalizer-not-a-real-password")
    verify_password(plain_password, _dummy_hash)

def validate_password_policy(password:str) -> None:
    """Validate password length and complexity. Raise WeakPasswordError if invalid."""
    if not isinstance(password,str) or len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def generate_temp_password(
    length:int = 8
) -> str:
    """Generate a random temporary password of specified length"""
    return ''.join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))

def normalize_phone(
    raw_phone:str
) -> str:
    """
     Normalize a phone number to E.164 format, Kenya as the default country
     Everything that identifies a phone (stored value, login lookup, lockout
    key) goes through this making sure 0711 and 254711 are the same number
    """
    cleaned = re.sub(r"[\s\-()]", "", raw_phone or "")
    if not _DIGITS_RE.match(cleaned):
        raise ValueError(f"{raw_phone} is not a valid phone number")

    if cleaned.startswith("+"):
        candidate = cleaned
    elif cleaned.startswith("00"):
        candidate = "+" + cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 10:
        candidate = "+254" + cleaned[1:]
    elif len(cleaned) == 9 and cleaned[0] in "17":
        candidate = "+254" + cleaned
    else:
        candidate = "+" + cleaned

    if not _E164_RE.match(candidate):
        raise ValueError(f"{raw_phone} is not a valid phone number")

    return candidate

def normalize_email(raw_email:str) -> str:
    return (raw_email or "").strip().lower()
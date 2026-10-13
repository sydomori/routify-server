"""
audit.service is a leaf module ie imports nothing from other modules
record() is the only write path. It never raises into or rolls back the action it describes
"""

import hashlib
import hmac

from flask import g, current_app, has_request_context
from sqlalchemy.orm import Session

from app.extensions import db

from .actions import VALID_ACTIONS, VALID_OUTCOMES
from .models import AuditLog

# Any metadata key containing one of these substrings will be redacted to avoid storing sensitive information in the audit log. This is a security requirement for the system.
_FORBIDDEN_KEY_PARTS = (
    "password", "token", "secret", "api_key", "apikey", "authorization",
    "url", "content", "storage_key",
)


def hash_identifier(value:str)-> str:
    """
     hashes identifiers ie phone numbers that dont match any account thus have no actor id
     raw phone number is PII thus can't be stored in audit log
     hash phone number with secret key so we have something to compare 
     use hmac to avoid rainbow table attacks
     secret key is never stored with the data unlike salting, so if the database is compromised, the attacker can't recompute the hashes without the secret key
    """
    #pick a secret from config to use as the HMAC key, falling back to the app's SECRET_KEY if AUDIT_HASH_KEY is not set
    key = (current_app.config.get("AUDIT_HASH_KEY") or current_app.config["SECRET_KEY"])
    if isinstance(key,str):
        key = key.encode()

    #strips whitespace around value & convert to bytes
    normalized = (value or "").strip().encode()
    return hmac.new(key,normalized,hashlib.sha256).hexdigest()[:32]

def _sanitize(obj):
    """
        recursively redacts any keys in a dict that contain sensitive substrings, and returns a new object with the same structure but with sensitive values replaced by "[redacted]".  
        protects against accidentally logging sensitive information in the audit log, which is a security requirement for the system.
    """
    if isinstance(obj,dict):
        """
         goes through each key, lowercases it & checks if it contains any of the forbidden substrings. 
         If it does, the value is replaced with "[redacted]". 
         Otherwise, the value is recursively sanitized. 
        """
        clean = {}
        for k,v in obj.items():
            if any(part in str(k).lower() for part in _FORBIDDEN_KEY_PARTS):
                clean[k] = "[redacted]"
            else:
                clean[k] = _sanitize(v)
        return clean

    if isinstance(obj,(list,tuple)):
        return [_sanitize(i) for i in obj]
    
    return obj
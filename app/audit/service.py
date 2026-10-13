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

def _validate(action, outcome):
    """
        validates that the action and outcome are in the set of valid actions and outcomes defined in actions.py. 
        raises ValueError if either is invalid. 
        This is a security requirement for the system to ensure that only known actions and outcomes are logged.
    """
    if action not in VALID_ACTIONS:
        return f"unknown audit action: {action!r}"
    if outcome not in VALID_OUTCOMES:
        return f"invalid audit outcome: {outcome!r}"
    return None

def record(
    actor_id, action, entity_type=None, entity_id=None,
    outcome="success", request_id=None, metadata=None):
    """
     appends one audit row AFTER the action it describes
     writes on its own connection so it never rolls back the action it describes
     returns AUditLog or None if the write was skipped or failed
    """
    problem = _validate(action, outcome)
    if problem:
        if current_app.config.get("AUDIT_STRICT", False): # True in Tests/dev
            raise ValueError(problem)
        current_app.logger.error("audit.record skipped: %s", problem)
        return None

    try:
        if request_id is None and has_request_context():
            request_id = getattr(g,"request_id", None)

        row = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            request_id=request_id,
            meta=_sanitize(metadata) if metadata else None,
        )
        with Session(db.engine, expire_on_commit=False) as session, session.begin():
            """
             use db.engine to get a new connection for this session, so it doesn't share the transaction with the caller.
             expire_on_commit=False so the row object is still usable after the commit, allowing us to return it to the caller without needing to refresh it from the database.
            """
            session.add(row)
        return row
    except Exception:
        current_app.logger.exception(
            "audit write failed: action=%s entity=%s:%s outcome=%s request_id=%s",
            action, entity_type, entity_id, outcome, request_id,
        )
        return None
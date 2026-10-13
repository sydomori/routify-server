"""
Shared route guards
moved up from app/auth/decorators.py to avoid circular imports with app/__init__.py
"""

from functools import wraps

from flask import g, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt

from app.audit import actions
from app.audit.service import record
from app.auth.exceptions import UserNotFoundError
from app.auth.service import get_user_by_id

def _load_user():
    """
    loads the current user once per request, and caches it in g.current_user for the rest of the request.
    avoids a second query when role_required and password_change_required are both used on the same route.
    """
    user = getattr(g, "current_user", None)
    if user is None:
        user = get_user_by_id(get_jwt_identity())
        g.current_user = user
    return user

def _deny(status, error, reason, actor_id=None, code=None, **extra_meta):
    """Audit a denied access attempt then build a response"""
    record(
        actor_id=actor_id,
        action=actions.ACCESS_DENIED,
        outcome=actions.OUTCOME_DENIED,
        metadata={
            "reason": reason,
            "endpoint": request.endpoint,
            "method": request.method,
            **extra_meta,
        },
    )
    body = {"error": error}
    if code:
        body["code"] = code
    return jsonify(body), status
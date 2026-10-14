"""
Shared route guards. Lives at app/decorators.py.
moved from auth/decorators.py to app to avoid circular imports (depends on auth.service)
"""
from functools import wraps
 
from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
 
from app.audit import actions
from app.audit.service import record
from app.auth.exceptions import UserNotFoundError
from app.auth.service import get_user_by_id
 
 
def _load_user():
    """
    Load the current user once per request and reuse it (avoids a second
    query when role_required and password_change_required are stacked).
 
    Cached on request.environ, which is unique to each request. Do NOT cache on
    flask.g: when an app context is already pushed (as in the test fixtures), g
    is shared across requests and a stale user would leak between them.
    """
    cached = request.environ.get("routify.current_user")
    if cached is None:
        cached = get_user_by_id(int(get_jwt_identity()))
        request.environ["routify.current_user"] = cached
    return cached
 
 
def _deny(status, error, reason, actor_id=None, code=None, **extra_meta):
    """Audit a denied access attempt (NFR-SEC-14), then build the response."""
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
 
 
def role_required(*allowed_roles):
    """Checks, in order: valid JWT -> account exists -> account is active
    (NFR-SEC-03, one DB read per request) -> role claim in allowed_roles.
 
    Role is read from the token (roles don't change at runtime). is_active is
    NOT, because deactivation must take effect before the token expires.
    """
 
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            actor_id = int(get_jwt_identity())
 
            try:
                user = _load_user()
            except UserNotFoundError:
                return jsonify({"error": "User not found"}), 404
 
            if not user.is_active:
                # 403 (not 401) so the frontend doesn't loop on token refresh
                return _deny(403, "Account deactivated", "inactive_account",
                             actor_id=actor_id, code="account_inactive")
 
            role = get_jwt().get("role")
            if role not in allowed_roles:
                return _deny(403, "Forbidden: insufficient role",
                             "insufficient_role", actor_id=actor_id,
                             role=role, required=list(allowed_roles))
 
            return fn(*args, **kwargs)
 
        return wrapper
 
    return decorator
 
 
def password_change_required(fn):
    """
    Hard gate for accounts still on a temporary password.
 
    Re-reads must_change_password from the DB instead of trusting the JWT, since
    the token would stay stale after the flag flips to false.
    """
 
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        actor_id = int(get_jwt_identity())
 
        try:
            user = _load_user()
        except UserNotFoundError:
            return jsonify({"error": "User not found"}), 404
 
        if user.must_change_password:
            return _deny(403, "Password change required",
                         "password_change_required", actor_id=actor_id,
                         code="password_change_required")
        return fn(*args, **kwargs)
 
    return wrapper
 
 
manager_required = role_required("manager")
driver_required = role_required("driver")
 

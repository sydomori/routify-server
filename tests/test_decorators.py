"""
Tests for app/decorators.py (shared route guards)
Lives in tests/ because th module lives in app, not app/audit
"""

import pytest
from flask_jwt_extended import create_access_token
from flask_jwt_extended.exceptions import NoAuthorizationError

from app.decorators import (
    driver_required, manager_required, password_change_required, role_required,
)

def view():
    return "ok"


def call(app,guarded,headers=None):
    with app.test_request_context("/guarded", headers=headers or {}):
        return guarded()

def test_manager_passes_manager_required(app, make_user, auth_headers, audit_rows):
    """
     Happy path: a manager passes manager_required, and successful access is
     not written to the audit log.
    """
    assert call(app, manager_required(view), auth_headers(make_user("manager"))) == "ok"
    assert audit_rows() == []  # successful access is not audited

def test_driver_passes_driver_required(app, make_user, auth_headers):
    """
     Happy path: a driver passes driver_required.
    """
    assert call(app, driver_required(view), auth_headers(make_user("driver"))) == "ok"

def test_any_listed_role_is_accepted(app, make_user, auth_headers):
    """
     Happy path: role_required accepts any role in its list.
    """
    guarded = role_required("manager", "driver")(view)
    assert call(app, guarded, auth_headers(make_user("driver"))) == "ok"

def test_password_gate_passes_when_flag_is_false(app, make_user, auth_headers):
    """
     Happy path: a user who has already changed their password passes the gate
    """
    user = make_user("driver", must_change_password=False)
    assert call(app, password_change_required(view), auth_headers(user)) == "ok"
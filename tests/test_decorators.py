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


def test_wrong_role_is_denied_and_audited(app, make_user, auth_headers, audit_rows):
    """
     High-risk / security: a wrong-role request is denied (403) and recorded as
     access.denied with the actor, role and required roles
    """
    driver = make_user("driver")
    resp, status = call(app, manager_required(view), auth_headers(driver))
    assert status == 403
    (row,) = audit_rows(action="access.denied")
    assert row.outcome == "denied" and row.actor_id == driver.id
    assert row.meta["reason"] == "insufficient_role"
    assert row.meta["role"] == "driver" and row.meta["required"] == ["manager"]

def test_inactive_account_is_denied_even_with_valid_token(app, make_user, auth_headers, audit_rows):
    """
     High-risk / security: an inactive account is denied even with a valid
     token, and the denial is audited
    """
    manager = make_user("manager", is_active=False)
    resp, status = call(app, manager_required(view), auth_headers(manager))
    assert status == 403
    assert resp.get_json()["code"] == "account_inactive"
    (row,) = audit_rows(action="access.denied")
    assert row.meta["reason"] == "inactive_account" and row.actor_id == manager.id

def test_deactivation_takes_effect_on_the_next_request(app, make_user, auth_headers):
    """
     High-risk / security: the same token works, then stops working on the very
     next request after deactivation
    """
    from app.extensions import db
    manager = make_user("manager")
    headers = auth_headers(manager)  # same token reused
    assert call(app, manager_required(view), headers) == "ok"
    manager.is_active = False
    db.session.commit()
    _, status = call(app, manager_required(view), headers)
    assert status == 403

def test_temp_password_account_is_gated(app, make_user, auth_headers, audit_rows):
    """
     High-risk / security: an account on a temporary password is blocked with
     code=password_change_required, and the denial is audited
    """
    user = make_user("driver", must_change_password=True)
    resp, status = call(app, password_change_required(view), auth_headers(user))
    assert status == 403
    assert resp.get_json()["code"] == "password_change_required"
    (row,) = audit_rows(action="access.denied")
    assert row.meta["reason"] == "password_change_required"
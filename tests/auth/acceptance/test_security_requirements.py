"""
Acceptance tests for the security requirements (end to end through HTTP) of the application. 
The tests ensure that the application adheres to the defined security standards and practices, 
ie. deactivated users loses access, refresh endpoint, temp password expiration, must-change-password restrictions
login lockout & redis failures.
"""

from datetime import timedelta

import pytest

from app.audit import actions
from app.auth.models import User
from app.auth.utils import utcnow
from app.extensions import db
from tests.auth.helpers import bearer, login

def tokens(client, identifier, password):
    """
     Helper function to obtain access and refresh tokens for a given user.
    """
    response = login(client, identifier, password)
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    return bearer(body["access_token"]), bearer(body["refresh_token"])

def onboard_a_driver(client, manager, auth_headers, comms, phone="+254711111111"):
    """
     Mimics the real onboarding flow
     Returns (driver_id, the temp password the SMS carried)
    """
    response = client.post(
        "/api/auth/onboard-driver", json={"name": "Sam Driver", "phone": phone}, headers=auth_headers(manager)
    )
    assert response.status_code == 201
    [(_, temp_password)] = comms.sent("send_onboarding_sms")
    return response.get_json()["id"], temp_password 


# -------- Deactivates user loses access, even with a token that hasn't expired ----------

class TestDeactivatedUserIsDenied:
    @pytest.mark.parametrize("method,url,body", [
        pytest.param("get", "/api/auth/me", None, id="me"),
        pytest.param("post", "/api/auth/change-password",
                     {"new_password": "BrandNewPassword1", "current_password": "DriverPass123"},
                     id="change-password"),
    ])
    def test_a_still_valid_access_token_is_refused_on_routes_open_to_any_logged_in_user(
        self, client, manager, driver, auth_headers, audit_rows, method, url, body
    ):
        access, _ = tokens(client, driver.phone, "DriverPass123")
        assert client.get("/api/auth/me", headers=access).status_code == 200   # the token is genuinely good

        deactivated = client.patch(f"/api/auth/drivers/{driver.id}/deactivate", headers=auth_headers(manager))
        assert deactivated.status_code == 200

        response = getattr(client, method)(url, json=body, headers=access)     # same token, a moment later
        assert response.status_code == 403
        assert response.get_json()["code"] == "account_inactive"
        row = audit_rows(action=actions.ACCESS_DENIED)[-1]
        assert (row.actor_id, row.meta["reason"]) == (driver.id, "inactive_account")

    def test_a_deactivated_manager_is_refused_on_role_protected_routes_too(self, client, manager):
        access, _ = tokens(client, manager.email, "ManagerPass123")
        first = client.post("/api/auth/onboard-driver", json={"name": "A", "phone": "+254711111111"}, headers=access)
        assert first.status_code == 201

        manager.is_active = False   # there is no API to deactivate a manager yet
        db.session.commit()

        again = client.post("/api/auth/onboard-driver", json={"name": "B", "phone": "+254711111112"}, headers=access)
        assert again.status_code == 403
        assert again.get_json()["code"] == "account_inactive"


# ------ Refresh endpoint test ------------------

class TestDeactivatedUserCannotRefresh:
    """
     Access tokens last 15 minutes but refresh tokens last 7 days
     auth/refresh must check is_active otherwise a deactivated driver could
     keep using the app for 7 days after being deactivated
    """

    def test_refresh_works_until_the_account_is_deactivated_then_stops(
        self, client, manager, driver, auth_headers, audit_rows
    ):
        _, refresh = tokens(client, driver.phone, "DriverPass123") # get access/ refresh tokens
        before = client.post("/api/auth/refresh", headers=refresh)
        assert before.status_code == 200 and before.get_json()["access_token"] #make sure the tokens are ok

        client.patch(f"/api/auth/drivers/{driver.id}/deactivate", headers=auth_headers(manager))

        after = client.post("/api/auth/refresh", headers=refresh)
        assert after.status_code == 403   # 403, not 401, so a frontend doesn't loop on refresh
        assert after.get_json()["code"] == "account_inactive"
        assert "access_token" not in after.get_json()
        row = audit_rows(action=actions.ACCESS_DENIED)[-1]
        assert row.actor_id == driver.id
        assert row.meta["reason"] == "inactive_account"
        assert row.meta["endpoint"] == "auth.refresh_route"


# -------- Temporary passwords expire in 72 hrs and are single use ----------------

class TestTempPasswordExpiry:
    @pytest.mark.parametrize("offset, expected_status", [
        pytest.param(timedelta(minutes=-1), 401, id="a-minute-after-expiry-is-rejected"),
        pytest.param(timedelta(minutes=1), 200, id="a-minute-before-expiry-still-works"),
    ])

    def test_the_expiry_boundary(self, client, manager, auth_headers, comms, offset, expected_status):
        """ 
         The temp password is sent to the driver via SMS, and is valid for 72 hours.
         This test checks that the expiry boundary is enforced correctly.
        """
        driver_id, temp_password = onboard_a_driver(client, manager, auth_headers, comms)
        db.session.get(User, driver_id).temp_password_expires_at = utcnow() + offset   # "time passes"
        db.session.commit()

        assert login(client, "+254711111111", temp_password).status_code == expected_status
    
    def test_an_expired_driver_is_rejected_audited_and_rescued_by_a_manager_reset(
        self, client, manager, auth_headers, comms, audit_rows
    ):
        driver_id, temp_password = onboard_a_driver(client, manager, auth_headers, comms)
        db.session.get(User, driver_id).temp_password_expires_at = utcnow() - timedelta(hours=1)
        db.session.commit()

        assert login(client, "+254711111111", temp_password).status_code == 401
        [row] = audit_rows(action=actions.LOGIN_FAILED)
        assert row.meta["reason"] == "temp_password_expired"   # the client saw a generic 401

        reset = client.post(f"/api/auth/drivers/{driver_id}/reset-password", headers=auth_headers(manager))
        assert reset.status_code == 200
        [(_, new_temp)] = comms.sent("send_password_reset_sms")
        relogin = login(client, "+254711111111", new_temp)
        assert relogin.status_code == 200 and relogin.get_json()["must_change_password"] is True

    def test_a_temp_password_is_single_use(self, client, manager, auth_headers, comms):
        driver_id, temp_password = onboard_a_driver(client, manager, auth_headers, comms)
        access, _ = tokens(client, "+254711111111", temp_password)

        changed = client.post("/api/auth/change-password", json={"new_password": "BrandNewPassword1"}, headers=access)
        assert changed.status_code == 200

        assert login(client, "+254711111111", temp_password).status_code == 401
        assert db.session.get(User, driver_id).temp_password_used_at is not None

# --------- A user who must change their password cannot reach normal routes

GATED_ROUTES = [
    pytest.param("post", "/api/auth/onboard-driver", {"name": "X", "phone": "+254711111199"}, id="onboard-driver"),
    pytest.param("post", "/api/auth/invite-manager", {"name": "Y", "phone": "+254700000077", "email": "y@routify.test"}, id="invite-manager"),
    pytest.param("patch", "/api/auth/drivers/12345/deactivate", None, id="deactivate-driver"),
    pytest.param("post", "/api/auth/drivers/12345/reset-password", None, id="reset-password"),
]

class TestPasswordChangeGate:
    @pytest.fixture()
    def gated(self, client, make_user):
        """
         Creates a manager on a temporary password with genuine tokens from login
        """
        user = make_user(role="manager", password="TempPass1", must_change_password=True)
        access, refresh = tokens(client, user.email, "TempPass1")
        return user,access,refresh
    
    @pytest.mark.parametrize("method,url,body", GATED_ROUTES)
    def test_normal_routes_are_refused_until_the_password_is_changed(
        self, client, gated, audit_rows, method, url, body
    ):
        user, access, _ = gated
        response = getattr(client, method)(url, json=body, headers=access)
        assert response.status_code == 403
        assert response.get_json()["code"] == "password_change_required"
        row = audit_rows(action=actions.ACCESS_DENIED)[-1]
        assert (row.actor_id, row.meta["reason"]) == (user.id, "password_change_required")


    def test_the_routes_needed_to_escape_the_gate_stay_open(self, client, gated):
        _, access, refresh = gated
        assert client.get("/api/auth/me", headers=access).status_code == 200
        assert client.post("/api/auth/refresh", headers=refresh).status_code == 200
        changed = client.post("/api/auth/change-password", json={"new_password": "BrandNewPassword1"}, headers=access)
        assert changed.status_code == 200

    def test_the_same_token_is_unblocked_the_moment_the_password_is_changed(self, client, gated):
        """The gate reads the database on every request, not a flag baked into the token."""
        _, access, _ = gated
        payload = {"name": "X", "phone": "+254711111199"}
        assert client.post("/api/auth/onboard-driver", json=payload, headers=access).status_code == 403
        client.post("/api/auth/change-password", json={"new_password": "BrandNewPassword1"}, headers=access)
        assert client.post("/api/auth/onboard-driver", json=payload, headers=access).status_code == 201

    def test_a_new_drivers_first_login_journey(self, client, manager, auth_headers, comms):
        driver_id, temp_password = onboard_a_driver(client, manager, auth_headers, comms)

        first = login(client, "+254711111111", temp_password)
        assert first.get_json()["must_change_password"] is True
        access = bearer(first.get_json()["access_token"])
        assert client.get("/api/auth/me", headers=access).get_json()["must_change_password"] is True

        client.post("/api/auth/change-password", json={"new_password": "BrandNewPassword1"}, headers=access)

        second = login(client, "+254711111111", "BrandNewPassword1")
        assert second.status_code == 200 and second.get_json()["must_change_password"] is False

# ---------- Login lockout and what happens when Redis is down ------------------

class TestLockout:
    def test_five_failures_lock_the_account_for_fifteen_minutes(self, client, manager, lockout_clock):
        for _ in range(5):
            assert login(client, manager.email, "wrong").status_code == 401

        locked = login(client, manager.email, "ManagerPass123")   # even the RIGHT password
        assert locked.status_code == 429
        assert int(locked.headers["Retry-After"]) > 0

        lockout_clock.advance(14 * 60)
        assert login(client, manager.email, "ManagerPass123").status_code == 429   # 14 minutes: still locked
        lockout_clock.advance(61)
        assert login(client, manager.email, "ManagerPass123").status_code == 200   # 15 minutes: free

    def test_locking_one_account_leaves_everyone_else_alone(self, client, manager, driver):
        for _ in range(5):
            login(client, manager.email, "wrong")
        assert login(client, driver.phone, "DriverPass123").status_code == 200


class TestRedisDownFailsOpen:
    """When the lockout store is unreachable, people must still be able to log in. The
    failure must be loud, and bad passwords must still be rejected."""

    def test_logins_keep_working_with_redis_down(self, client, manager, redis_down, caplog):
        with caplog.at_level("ERROR"):
            for _ in range(8):   # well past the limit of 5
                assert login(client, manager.email, "wrong").status_code == 401   # rejected, never 429
            ok = login(client, manager.email, "ManagerPass123")

        assert ok.status_code == 200 and ok.get_json()["access_token"]
        assert "lockout_store_unavailable" in caplog.text
        assert redis_down.ttl.called, "Redis was never attempted, so this test proved nothing"
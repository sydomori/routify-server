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

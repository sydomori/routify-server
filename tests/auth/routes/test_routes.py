"""
 Route tests: HTTP contract only
 For each endpoint: the happy path, who is allowed in,
 which status code each failure maps to, and that no secret leaks into a response.
"""

import uuid

import pytest

from app.audit import actions
from tests.auth.helpers import login

# ---------- health check and request IDs ----------

def test_health_check_reports_a_working_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["database"] == "ok"

class TestRequestId:
    def test_a_well_formed_id_from_the_client_is_kept_and_reaches_the_audit_row(self, client, manager, audit_rows):
        response = client.post(
            "/api/auth/login",
            json={"identifier": manager.email, "password": "ManagerPass123"},
            headers={"X-Request-ID": "abc-123-DEF"},
        )
        assert response.headers["X-Request-ID"] == "abc-123-DEF"
        [row] = audit_rows(action=actions.LOGIN_SUCCESS)
        assert row.request_id == "abc-123-DEF"

    @pytest.mark.parametrize("bad", ["has spaces in it", "x" * 65, "semi;colon", "<script>", ""])
    def test_anything_else_is_replaced_with_a_generated_id(self, client, bad):
        returned = client.get("/api/health", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
        assert returned != bad
        uuid.UUID(returned)

    def test_an_id_is_generated_when_none_is_sent(self, client):
        uuid.UUID(client.get("/api/health").headers["X-Request-ID"])


# ---------- authentication endpoints ----------

class TestLogin:
    def test_success_returns_both_tokens_and_no_secrets(self, client, manager):
        body = login(client, manager.email, "ManagerPass123").get_json()
        assert body["access_token"] and body["refresh_token"]
        assert body["access_token"] != body["refresh_token"]
        assert "password_hash" not in body["user"]

    def test_every_kind_of_rejection_looks_identical_to_the_client(self, client, manager, make_user):
        """So nobody can tell an unknown account from a wrong password, a deactivated
        account or an expired temp password. The audit log keeps the real reason."""
        from datetime import timedelta
        from app.auth.utils import utcnow

        inactive = make_user(role="driver", password="DriverPass123", is_active=False)
        expired = make_user(
            role="driver", password="TempPass1", must_change_password=True,
            temp_password_expires_at=utcnow() - timedelta(minutes=1),
        )
        responses = [
            login(client, "nobody@nowhere.test", "x"),
            login(client, manager.email, "wrong"),
            login(client, inactive.phone, "DriverPass123"),
            login(client, expired.phone, "TempPass1"),
        ]
        assert {r.status_code for r in responses} == {401}
        assert len({r.get_data() for r in responses}) == 1

    def test_a_locked_account_gets_429_with_a_retry_after(self, client, manager):
        for _ in range(5):
            login(client, manager.email, "wrong")
        response = login(client, manager.email, "ManagerPass123")
        assert response.status_code == 429
        assert response.get_json()["code"] == "account_locked"
        assert int(response.headers["Retry-After"]) > 0

    def test_missing_fields_are_a_400(self, client):
        assert client.post("/api/auth/login", json={"identifier": "x"}).status_code == 400

class TestRefresh:
    def test_a_refresh_token_returns_an_access_token_that_works(self, client, manager, refresh_headers):
        response = client.post("/api/auth/refresh", headers=refresh_headers(manager))
        assert response.status_code == 200
        token = response.get_json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.get_json()["id"] == manager.id

    def test_the_two_token_types_are_not_interchangeable(self, client, manager, auth_headers, refresh_headers):
        assert client.post("/api/auth/refresh", headers=auth_headers(manager)).status_code == 422
        assert client.get("/api/auth/me", headers=refresh_headers(manager)).status_code == 422

    def test_a_token_is_required(self, client):
        assert client.post("/api/auth/refresh").status_code == 401

class TestMe:
    def test_returns_the_current_user_without_secrets(self, client, manager, auth_headers):
        body = client.get("/api/auth/me", headers=auth_headers(manager)).get_json()
        assert body["id"] == manager.id
        assert "password_hash" not in body
        assert not any(key.startswith("temp_password") for key in body)

    def test_a_token_is_required(self, client):
        assert client.get("/api/auth/me").status_code == 401

class TestChangePassword:
    def test_a_forced_change_works_with_no_current_password(self, client, make_user, auth_headers):
        driver = make_user(role="driver", password="TempPass1", must_change_password=True)
        response = client.post(
            "/api/auth/change-password", json={"new_password": "BrandNewPassword1"}, headers=auth_headers(driver)
        )
        assert response.status_code == 200
        assert login(client, driver.phone, "BrandNewPassword1").status_code == 200

    def test_a_voluntary_change_without_the_current_password_is_403_with_a_code(self, client, driver, auth_headers):
        response = client.post(
            "/api/auth/change-password", json={"new_password": "BrandNewPassword1"}, headers=auth_headers(driver)
        )
        assert response.status_code == 403
        assert response.get_json()["code"] == "wrong_current_password"

    def test_a_weak_password_is_400_with_a_code(self, client, make_user, auth_headers):
        driver = make_user(role="driver", must_change_password=True)
        response = client.post("/api/auth/change-password", json={"new_password": "short"}, headers=auth_headers(driver))
        assert response.status_code == 400
        assert response.get_json()["code"] == "weak_password"

    def test_a_token_is_required(self, client):
        assert client.post("/api/auth/change-password", json={"new_password": "BrandNewPassword1"}).status_code == 401

# ------------- Manage-only endpoints --------------

class TestOnboardDriver:
    def test_a_manager_creates_a_driver_and_the_temp_password_is_not_in_the_response(
        self, client, manager, auth_headers, comms
    ):
        response = client.post(
            "/api/auth/onboard-driver",
            json={"name": "Sam Driver", "phone": "0711111111"},
            headers=auth_headers(manager),
        )
        assert response.status_code == 201
        assert response.get_json()["phone"] == "+254711111111"
        [(_, temp_password)] = comms.sent("send_onboarding_sms")
        assert temp_password not in response.get_data(as_text=True)

    def test_a_driver_is_forbidden_and_the_attempt_is_audited(self, client, driver, auth_headers, audit_rows):
        response = client.post(
            "/api/auth/onboard-driver", json={"name": "New", "phone": "+254711111112"}, headers=auth_headers(driver)
        )
        assert response.status_code == 403
        [row] = audit_rows(action=actions.ACCESS_DENIED)
        assert row.actor_id == driver.id and row.meta["reason"] == "insufficient_role"

    def test_no_token_is_401(self, client):
        assert client.post("/api/auth/onboard-driver", json={"name": "X", "phone": "+254711111111"}).status_code == 401

    @pytest.mark.parametrize("payload,status", [
        ({"name": "Dupe", "phone": "DRIVER_PHONE"}, 409),
        ({"name": "Bad", "phone": "not-a-phone"}, 400),
        ({"name": "Missing"}, 400),
    ], ids=["duplicate-phone", "invalid-phone", "missing-field"])
    def test_bad_input_maps_to_the_right_status(self, client, manager, driver, auth_headers, payload, status):
        payload = {k: (driver.phone if v == "DRIVER_PHONE" else v) for k, v in payload.items()}
        response = client.post("/api/auth/onboard-driver", json=payload, headers=auth_headers(manager))
        assert response.status_code == status

class TestInviteManager:
    BODY = {"name": "Second", "phone": "+254700000002", "email": "second@routify.test"}

    def test_a_manager_can_invite(self, client, manager, auth_headers):
        response = client.post("/api/auth/invite-manager", json=self.BODY, headers=auth_headers(manager))
        assert response.status_code == 201
        assert response.get_json()["must_change_password"] is True

    def test_a_driver_is_forbidden_and_no_token_is_401(self, client, driver, auth_headers):
        assert client.post("/api/auth/invite-manager", json=self.BODY, headers=auth_headers(driver)).status_code == 403
        assert client.post("/api/auth/invite-manager", json=self.BODY).status_code == 401

    def test_a_duplicate_email_is_409_and_an_invalid_one_is_400(self, client, manager, auth_headers):
        dup = {**self.BODY, "phone": "+254700000009", "email": manager.email}
        assert client.post("/api/auth/invite-manager", json=dup, headers=auth_headers(manager)).status_code == 409
        bad = {**self.BODY, "email": "not-an-email"}
        assert client.post("/api/auth/invite-manager", json=bad, headers=auth_headers(manager)).status_code == 400

class TestDeactivateDriver:
    def test_a_manager_deactivates_a_driver_and_it_is_audited(self, client, manager, driver, auth_headers, audit_rows):
        response = client.patch(f"/api/auth/drivers/{driver.id}/deactivate", headers=auth_headers(manager))
        assert response.status_code == 200
        [row] = audit_rows(action=actions.DRIVER_DEACTIVATE)
        assert (row.actor_id, row.entity_id) == (manager.id, driver.id)

    def test_a_driver_is_forbidden(self, client, driver, auth_headers):
        assert client.patch(f"/api/auth/drivers/{driver.id}/deactivate", headers=auth_headers(driver)).status_code == 403

    def test_unknown_is_404_and_a_manager_target_is_400(self, client, manager, make_user, auth_headers):
        assert client.patch("/api/auth/drivers/99999/deactivate", headers=auth_headers(manager)).status_code == 404
        other = make_user(role="manager")
        assert client.patch(f"/api/auth/drivers/{other.id}/deactivate", headers=auth_headers(manager)).status_code == 400

class TestResetDriverPassword:
    def test_a_manager_resets_and_the_new_password_is_not_in_the_response(
        self, client, manager, driver, auth_headers, comms
    ):
        response = client.post(f"/api/auth/drivers/{driver.id}/reset-password", headers=auth_headers(manager))
        assert response.status_code == 200
        [(_, new_temp)] = comms.sent("send_password_reset_sms")
        assert new_temp not in response.get_data(as_text=True)

    def test_a_driver_is_forbidden_and_no_token_is_401(self, client, driver, auth_headers):
        url = f"/api/auth/drivers/{driver.id}/reset-password"
        assert client.post(url, headers=auth_headers(driver)).status_code == 403
        assert client.post(url).status_code == 401

    def test_unknown_is_404_a_manager_target_is_400_a_deactivated_driver_is_400(
        self, client, manager, driver, make_user, auth_headers
    ):
        headers = auth_headers(manager)
        assert client.post("/api/auth/drivers/99999/reset-password", headers=headers).status_code == 404
        other = make_user(role="manager")
        assert client.post(f"/api/auth/drivers/{other.id}/reset-password", headers=headers).status_code == 400
        driver.is_active = False
        from app.extensions import db
        db.session.commit()
        assert client.post(f"/api/auth/drivers/{driver.id}/reset-password", headers=headers).status_code == 400


# ------------- Public endpoints --------------

class TestBootstrapManager:
    BODY = {"name": "Root", "phone": "+254700000001", "email": "root@routify.test", "password": "RootPassword123"}

    def test_the_first_call_creates_a_manager_without_leaking_the_hash(self, client):
        response = client.post("/api/auth/bootstrap-manager", json=self.BODY)
        assert response.status_code == 201
        assert "password_hash" not in response.get_json()

    def test_the_door_is_closed_once_a_manager_exists_even_with_no_token(self, client, manager):
        assert client.post("/api/auth/bootstrap-manager", json=self.BODY).status_code == 403

    def test_a_short_password_or_missing_fields_are_400(self, client):
        assert client.post("/api/auth/bootstrap-manager", json={**self.BODY, "password": "Elevenchars"}).status_code == 400
        assert client.post("/api/auth/bootstrap-manager", json={"name": "Incomplete"}).status_code == 400


class TestAcceptInvite:
    def token_for_new_invite(self, manager):
        from app.auth import service
        invitee = service.invite_manager("Second", "+254700000002", "second@routify.test", manager)
        return service._generate_invite_token(invitee.id)

    def test_a_valid_invite_sets_the_password_and_does_not_log_the_user_in(self, client, manager):
        token = self.token_for_new_invite(manager)
        response = client.post("/api/auth/accept-invite", json={"token": token, "new_password": "NewManagerPass1"})
        assert response.status_code == 200
        assert "access_token" not in response.get_json()
        assert login(client, "second@routify.test", "NewManagerPass1").status_code == 200

    @pytest.mark.parametrize("token,password", [
        ("garbage", "NewManagerPass1"),
        ("USE_REAL_TOKEN", "Elevenchars"),
    ], ids=["bad-token", "weak-password"])
    def test_a_bad_token_or_weak_password_is_400(self, client, manager, token, password):
        if token == "USE_REAL_TOKEN":
            token = self.token_for_new_invite(manager)
        assert client.post("/api/auth/accept-invite", json={"token": token, "new_password": password}).status_code == 400
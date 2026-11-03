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
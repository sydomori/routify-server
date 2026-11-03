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
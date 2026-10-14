import pytest

from app.audit import actions
from app.audit.service import record

FIELDS = {
    "id","actor_id","action","entity_type","entity_id","outcome","request_id","metadata","created_at"
}

def seed(actor_id, n=3, action=actions.TRIP_START, entity="Trip"):
    for i in range(n):
        record(actor_id,action,entity,i)

def test_manager_can_list_logs(client,manager,auth_headers):
    seed(manager.id,3)
    resp = client.get("/api/audit/logs", headers=auth_headers(manager))
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 3
    assert set(data[0]) == FIELDS and "meta" not in data[0]

def test_results_are_newest_first(client, manager, auth_headers):
    seed(manager.id, 4)
    ids = [r["id"] for r in client.get("/api/audit/logs", headers=auth_headers(manager)).get_json()]
    assert ids == sorted(ids, reverse=True)

def test_filters(client, make_user, manager, auth_headers):
    other = make_user("driver")
    seed(manager.id, 2)
    seed(other.id, 1, actions.ORDER_ASSIGN, "Order")
    h = auth_headers(manager)
    get = lambda q: client.get(f"/api/audit/logs?{q}", headers=h).get_json()
    assert len(get(f"actor_id={manager.id}")) == 2
    assert len(get("action=order.assign")) == 1
    assert len(get("entity_type=Order")) == 1
    assert len(get("start=2000-01-01T00:00:00")) == 3
    assert get("start=2999-01-01T00:00:00") == []
    assert get("end=2000-01-01T00:00:00") == []

def test_pagination(client, manager, auth_headers):
    seed(manager.id, 5)
    h = auth_headers(manager)
    full = [r["id"] for r in client.get("/api/audit/logs?limit=200", headers=h).get_json()]
    page = [r["id"] for r in client.get("/api/audit/logs?limit=2&offset=2", headers=h).get_json()]
    assert page == full[2:4]


#-------- high risk : access control ------------

def test_no_token_is_401_and_not_audited(client, audit_rows):
    """
     a missing token is rejected with 401, and anonymous
     traffic is never written to the audit log (stops audit-table flooding). 
    """
    assert client.get("/api/audit/logs").status_code == 401
    assert audit_rows(action="access.denied") == []

def test_driver_is_forbidden_and_attempt_is_audited(client, make_user, auth_headers, audit_rows):
    """
     wrong-role requests are denied (403) AND audited.
     A driver must not be able to read the audit log
    """
    
    driver = make_user("driver")
    resp = client.get("/api/audit/logs", headers=auth_headers(driver))
    assert resp.status_code == 403
    (row,) = audit_rows(action="access.denied")
    assert row.actor_id == driver.id
    assert row.meta["endpoint"] == "audit.get_logs" and row.meta["method"] == "GET"

def test_denied_row_carries_a_request_id(client, make_user, auth_headers, audit_rows):
    """
     the audited denial carries a request_id, so it can be
     correlated across logs. Also verifies _register_request_id runs.
    """
    client.get("/api/audit/logs", headers=auth_headers(make_user("driver")))
    (row,) = audit_rows(action="access.denied")
    assert row.request_id

def test_deactivated_manager_is_forbidden(client, make_user, auth_headers):
    """
     an inactive account is denied even with a valid token
    """
    resp = client.get("/api/audit/logs", headers=auth_headers(make_user("manager", is_active=False)))
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "account_inactive"

def test_there_is_no_write_endpoint(client, manager, auth_headers):
    """
     there is no write endpoint; audit rows can only be
     created internally through record(), never over HTTP
    """
    h = auth_headers(manager)
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/audit/logs", headers=h, json={}).status_code == 405

def test_sensitive_metadata_is_never_returned(client, manager, auth_headers):
    """
     sensitive metadata is redacted end to end, so it never
     reaches an API response
    """
    record(manager.id, actions.LOGIN_FAILED, metadata={"password": "hunter2"})
    body = client.get("/api/audit/logs", headers=auth_headers(manager)).get_data(as_text=True)
    assert "hunter2" not in body and "[redacted]" in body
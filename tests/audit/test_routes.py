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
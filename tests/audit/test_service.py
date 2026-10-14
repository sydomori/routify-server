import logging

import pytest
from flask import g

from app.audit import actions
from app.audit.models import AuditLog
from app.extensions import db
from app.audit.service import hash_identifier, list_audit_logs, record

def skip_on_sqlite():
    if db.engine.dialect.name == "sqlite":
        pytest.skip("needs a real Postgres test database")

#--------------- happy path ----------------

class TestRecordHappyPath:
    """
     record() stores every field, defaults the outcome to
     success, and takes request_id from flask.g (an explicit value wins)
    """
    def test_writes_row_with_all_fields(self, make_user):
        actor = make_user()
        row = record(actor.id, actions.DRIVER_ASSIGN, "Truck", 5, metadata={"previous_truck_id": 3})
        stored = db.session.get(AuditLog, row.id)
        assert stored.actor_id == actor.id
        assert stored.action == "driver.assign"
        assert stored.entity_type == "Truck"
        assert stored.entity_id == 5
        assert stored.outcome == "success"
        assert stored.meta == {"previous_truck_id": 3}
        assert stored.created_at is not None
 
    def test_outcome_defaults_to_success(self, make_user):
        row = record(make_user().id, actions.TRIP_START, "Trip", 1)
        assert row.outcome == "success"
 
    def test_request_id_taken_from_flask_g(self, app):
        with app.test_request_context():
            g.request_id = "req-123"
            row = record(None, actions.LOGIN_FAILED)
        assert row.request_id == "req-123"
 
    def test_explicit_request_id_wins_over_g(self, app):
        with app.test_request_context():
            g.request_id = "from-g"
            row = record(None, actions.LOGIN_FAILED, request_id="explicit")
        assert row.request_id == "explicit"
 
    def test_no_request_context_gives_null_request_id(self):
        assert record(None, actions.LOGIN_FAILED).request_id is None

class TestListHappyPath:
    """
     list_audit_logs() returns newest first, filters by actor /
     action / entity / date range, and paginates consistently
    """
    def _seed(self, actor_id, n, action=actions.TRIP_START, entity="Trip"):
        for i in range(n):
            record(actor_id, action, entity, i)
 
    def test_newest_first(self, make_user):
        self._seed(make_user().id, 4)
        ids = [r.id for r in list_audit_logs()]
        assert ids == sorted(ids, reverse=True) and len(ids) == 4
 
    def test_filter_by_actor_action_and_entity(self, make_user):
        a, b = make_user(), make_user()
        self._seed(a.id, 2)
        self._seed(b.id, 1, actions.ORDER_ASSIGN, "Order")
        assert len(list_audit_logs(actor_id=a.id)) == 2
        assert len(list_audit_logs(action="order.assign")) == 1
        assert len(list_audit_logs(entity_type="Order")) == 1
 
    def test_date_range_filters(self, make_user):
        from datetime import datetime, timedelta
        self._seed(make_user().id, 2)
        now = datetime.utcnow()
        assert len(list_audit_logs(start_date=now - timedelta(days=1))) == 2
        assert list_audit_logs(start_date=now + timedelta(days=1)) == []
        assert list_audit_logs(end_date=now - timedelta(days=1)) == []
 
    def test_pagination_slices_consistently(self, make_user):
        self._seed(make_user().id, 5)
        full = [r.id for r in list_audit_logs()]
        assert [r.id for r in list_audit_logs(limit=2, offset=2)] == full[2:4]
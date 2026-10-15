import logging

import pytest
from flask import g

from app.audit import actions
from app.audit.models import AuditLog
from app.extensions import db
from app.audit.service import hash_identifier, list_audit_logs, record

def _skip_on_sqlite():
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


#--------- security/ data protection ---------

class TestMetadataSanitising:
    """
     sensitive keys are redacted before
     storage, including nested dicts and lists. Safe keys are preserved.
    """
    @pytest.mark.parametrize("key", [
        "password", "temp_password", "access_token", "refresh_token",
        "api_key", "Authorization", "file_url", "document_content",
        "storage_key", "client_secret",
    ])
    def test_sensitive_keys_are_redacted(self, key):
        row = record(None, actions.LOGIN_FAILED, metadata={key: "super-secret"})
        stored = db.session.get(AuditLog, row.id)
        assert stored.meta[key] == "[redacted]"
        assert "super-secret" not in str(stored.meta)
 
    def test_nested_dicts_and_lists_are_cleaned(self):
        row = record(None, actions.LOGIN_FAILED, metadata={
            "provider": {"api_key": "sk-1", "name": "africas_talking"},
            "attempts": [{"token": "t-1"}, {"ok": True}],
        })
        meta = db.session.get(AuditLog, row.id).meta
        assert meta["provider"] == {"api_key": "[redacted]", "name": "africas_talking"}
        assert meta["attempts"] == [{"token": "[redacted]"}, {"ok": True}]

#------------ sad paths ---------------------


class TestAuditNeverBreaksTheCaller:

    
    def test_db_failure_returns_none_and_logs(self, app, monkeypatch, caplog):
        """
         a dropped DB connection makes record() return None and log the
         error instead of raising into the caller.
        """
        def boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr("app.audit.service.Session", boom)
        with caplog.at_level(logging.ERROR):
            assert record(None, actions.LOGIN_FAILED) is None
        assert "audit write failed" in caplog.text
    
    
    def test_unserializable_metadata_is_swallowed(self, audit_rows):
        """
         metadata that can't be stored as JSON (e.g. a datetime) is
         swallowed. The row is lost, so callers must pass JSON-safe values.
        """
        from datetime import datetime
        assert record(None, actions.LOGIN_FAILED,
                      metadata={"when": datetime.utcnow()}) is None
        assert audit_rows() == []
 
    
    def test_audit_row_survives_callers_rollback(self, audit_rows):
        """
         record() uses its own session, so the audit
         row survives when the caller's transaction is rolled back. Postgres only.
        """
        _skip_on_sqlite()
        # A pending, uncommitted change in the caller's own session...
        db.session.add(AuditLog(action="trip.start", outcome="success"))
        db.session.flush()
        record(None, actions.ACCESS_DENIED, outcome=actions.OUTCOME_DENIED)
        db.session.rollback()  # ...is rolled back; the audit row must remain.
        assert len(audit_rows(action="access.denied")) == 1
        assert audit_rows(action="trip.start") == []
 
    
    def test_unknown_actor_fk_is_swallowed(self, audit_rows):
        """
         a non-existent actor_id breaks the foreign key; record() swallows
         it and writes nothing. Postgres only (SQLite doesn't enforce FKs).
        """
        _skip_on_sqlite()  # SQLite doesn't enforce foreign keys by default
        assert record(999999, actions.LOGIN_FAILED) is None
        assert audit_rows() == []

#---------------- edge cases ------------------------

class TestRecordEdgeCases:
    """
     Boundary / edge: actor_id=None, optional entity fields, empty metadata,
     limit below 1 and above 200, negative offset, and an empty table.
    """
    def test_actor_can_be_none_for_unknown_account(self):
        row = record(None, actions.LOGIN_FAILED, outcome=actions.OUTCOME_DENIED,
                     metadata={"identifier_hash": "abc"})
        assert row.actor_id is None
 
    def test_entity_fields_are_optional(self):
        row = record(None, actions.ACCESS_DENIED, outcome=actions.OUTCOME_DENIED)
        assert row.entity_type is None and row.entity_id is None
 
    @pytest.mark.parametrize("meta", [None, {}])
    def test_empty_metadata_is_stored_as_null(self, meta):
        assert record(None, actions.LOGIN_FAILED, metadata=meta).meta is None
 
    def test_limit_below_one_is_clamped_to_one(self, make_user):
        for i in range(3):
            record(make_user().id, actions.TRIP_START, "Trip", i)
        assert len(list_audit_logs(limit=0)) == 1
 
    def test_limit_is_capped_at_200(self):
        db.session.add_all([AuditLog(action="trip.start", outcome="success")
                            for _ in range(205)])
        db.session.commit()
        assert len(list_audit_logs(limit=10_000)) == 200
 
    def test_negative_offset_is_treated_as_zero(self, make_user):
        record(make_user().id, actions.TRIP_START, "Trip", 1)
        assert len(list_audit_logs(offset=-5)) == 1
 
    def test_empty_table_returns_empty_list(self):
        assert list_audit_logs() == []

#---------------- sad paths -----------------

class TestValidation:
    """
     an unknown action or outcome raises in strict mode (tests/dev)
     and is logged and skipped in non-strict mode (production)
    """
    @pytest.mark.parametrize("action,outcome", [
        ("driver.teleport", "success"), ("", "success"),
        ("trip.start", "maybe"), ("trip.start", ""),
    ])
    def test_strict_mode_raises(self, action, outcome):
        with pytest.raises(ValueError):
            record(None, action, outcome=outcome)
 
    @pytest.mark.parametrize("action,outcome", [
        ("driver.teleport", "success"), ("trip.start", "maybe"),
    ])
    def test_non_strict_logs_and_writes_nothing(
            self, app, monkeypatch, caplog, audit_rows, action, outcome):
        monkeypatch.setitem(app.config, "AUDIT_STRICT", False)
        with caplog.at_level(logging.ERROR):
            assert record(None, action, outcome=outcome) is None
        assert "audit.record skipped" in caplog.text
        assert audit_rows() == []

#----------- hash identifier ----------------
class TestHashIdentifier:
    """ 
     Happy path: the same input always gives the same 32-char hash, and the
     raw value never appears in it.
    """
    def test_deterministic_fixed_length_and_hides_input(self):
        h = hash_identifier("0712345678")
        assert h == hash_identifier("0712345678")
        assert len(h) == 32 and "0712345678" not in h
 
    # Happy path: different accounts get different hashes.
    def test_different_inputs_differ(self):
        assert hash_identifier("0712345678") != hash_identifier("0712345679")
 
    # Boundary / edge: stray whitespace must not create a second identity.
    # (Phone-format normalisation, e.g. +254... vs 07..., is the caller's job.)
    def test_surrounding_whitespace_is_ignored(self):
        assert hash_identifier(" 0712345678 ") == hash_identifier("0712345678")
 
    # High-risk / security: the hash depends on a secret key, so it can't be
    # recomputed by someone who only has the data.
    def test_changing_the_key_changes_the_hash(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "AUDIT_HASH_KEY", "key-one")
        h1 = hash_identifier("0712345678")
        monkeypatch.setitem(app.config, "AUDIT_HASH_KEY", "key-two")
        assert hash_identifier("0712345678") != h1
 
    # Boundary / edge: with no AUDIT_HASH_KEY set, SECRET_KEY is used.
    def test_falls_back_to_secret_key(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "AUDIT_HASH_KEY", None)
        monkeypatch.setitem(app.config, "SECRET_KEY", "fallback-secret")
        assert len(hash_identifier("0712345678")) == 32
 
    # Boundary / edge: empty or None input still returns a hash, no exception.
    @pytest.mark.parametrize("value", ["", None])
    def test_empty_values_do_not_crash(self, value):
        assert len(hash_identifier(value)) == 32
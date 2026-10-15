"""Verifies NFR-SEC-15 at the database level. Skipped unless you point it at a
Postgres database where grants.sql has been applied.

  $env:AUDIT_TEST_APP_DB_URL = "postgresql://routify_app:...@localhost/routify_test"
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


URL = os.environ.get("AUDIT_TEST_APP_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="AUDIT_TEST_APP_DB_URL not set")


@pytest.fixture
def app_role_engine():
    engine = create_engine(URL)
    yield engine
    engine.dispose()


def _seed_row(engine):
    """Insert through the restricted role itself (it is allowed to INSERT), so
    the row lands in the same Postgres database the grants apply to."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO audit_logs (action, outcome) VALUES ('trip.start', 'success')"))


# Happy path: the restricted app role can still do its job (INSERT and
# SELECT). Needs a Postgres DB with grants.sql applied.
def test_app_role_can_insert_and_select(app_role_engine):
    with app_role_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO audit_logs (action, outcome) VALUES ('trip.start', 'success')"))
        assert conn.execute(text("SELECT count(*) FROM audit_logs")).scalar() >= 1


# High-risk / security (NFR-SEC-15): the app role cannot UPDATE, DELETE or
# TRUNCATE audit rows. Proves the append-only claim at the database level.
@pytest.mark.parametrize("statement", [
    "UPDATE audit_logs SET outcome = 'failed'",
    "DELETE FROM audit_logs",
    "TRUNCATE audit_logs",
])
def test_app_role_cannot_modify_or_remove_rows(app_role_engine, statement):
    _seed_row(app_role_engine)
    with pytest.raises(DBAPIError) as exc:
        with app_role_engine.begin() as conn:
            conn.execute(text(statement))
    assert "permission denied" in str(exc.value).lower()
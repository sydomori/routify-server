"""
 tests/audit only fixtures.
 shared fixtures live on tests/conftest.py, not here.
"""

import pytest 

from app.extensions import db
from app.audit.models import AuditLog

@pytest.fixture(autouse=True)
def _audit_strict(app):
    """unknown action/outcome raises in tests instead of being logged"""
    app.config["AUDIT_STRICT"] = True

@pytest.fixture
def audit_rows():
    def _rows(**filters):
        db.session.expire_all()
        return AuditLog.query.filter_by(**filters).order_by(AuditLog.id).all()

    return _rows
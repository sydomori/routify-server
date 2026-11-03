"""
 SERVICE tests for attempt_login(): credentials, lockout rules and 
 what is written to audit log. Real in memory db
 Business rules are tested here with the route tests checking what the status code and JSON response looks like. 
 The route tests are more like integration tests, but they are still fast because they use the in-memory db.
"""

from datetime import timedelta

import pytest

from app.audit import actions
from app.auth import service
from app.auth.utils import utcnow
from app.extensions import db
from tests.auth.helpers import meta_text

def expired_temp_driver(make_user):
    return make_user(
        role="driver", password="TempPass1", must_change_password=True,
        temp_password_expires_at=utcnow() - timedelta(minutes=1),
    )

class TestCredentialOutcomes:
    def test_valid_credentials_succeed_and_are_audited(self, manager, audit_rows):
        result = service.attempt_login(manager.email, "ManagerPass123")
        assert result.user.id == manager.id
        [row] = audit_rows(action=actions.LOGIN_SUCCESS)
        assert (row.actor_id, row.entity_type, row.entity_id) == (manager.id, "User", manager.id)

    def test_wrong_password_is_rejected_with_its_reason_audited(self, manager, audit_rows):
        result = service.attempt_login(manager.email, "nope")
        assert result.user is None and not result.locked
        [row] = audit_rows(action=actions.LOGIN_FAILED)
        assert row.actor_id == manager.id
        assert row.outcome == actions.OUTCOME_DENIED
        assert row.meta["reason"] == "bad_password"

    def test_unknown_account_is_rejected_with_no_actor(self, audit_rows):
        service.attempt_login("0799999999", "whatever")
        [row] = audit_rows(action=actions.LOGIN_FAILED)
        assert row.actor_id is None and row.entity_type is None
        assert row.meta["reason"] == "unknown_account"

    def test_deactivated_account_is_rejected_even_with_the_right_password(self, driver, audit_rows):
        driver.is_active = False
        db.session.commit()
        assert service.attempt_login(driver.phone, "DriverPass123").user is None
        [row] = audit_rows(action=actions.LOGIN_FAILED)
        assert row.meta["reason"] == "inactive_account"

    def test_expired_temp_password_is_rejected_but_only_revealed_for_the_right_password(
        self, make_user, audit_rows
    ):
        driver = expired_temp_driver(make_user)
        service.attempt_login(driver.phone, "TempPass1")        # right password, too late
        service.attempt_login(driver.phone, "WrongPassword")    # a stranger guessing
        reasons = [row.meta["reason"] for row in audit_rows(action=actions.LOGIN_FAILED)]
        assert reasons == ["temp_password_expired", "bad_password"]

    def test_unexpired_temp_password_logs_in(self, make_user):
        driver = make_user(
            role="driver", password="TempPass1", must_change_password=True,
            temp_password_expires_at=utcnow() + timedelta(hours=1),
        )
        assert service.attempt_login(driver.phone, "TempPass1").user.id == driver.id

    def test_audit_rows_never_hold_the_raw_identifier_or_password(self, manager, audit_rows):
        service.attempt_login(manager.email, "SuperSecretGuess1")
        service.attempt_login("0799999999", "SuperSecretGuess1")
        for row in audit_rows():
            text = meta_text(row)
            assert "SuperSecretGuess1" not in text
            assert manager.email not in text
            assert "0799999999" not in text and "+254799999999" not in text

    @pytest.mark.parametrize("spelling", ["0700000001", "+254 700 000 001", "254700000001"])
    def test_a_driver_can_log_in_with_any_spelling_of_their_phone(self, make_user, spelling):
        driver = make_user(role="driver", password="DriverPass123", phone="+254700000001")
        assert service.attempt_login(spelling, "DriverPass123").user.id == driver.id

    def test_email_login_ignores_case(self, manager):
        assert service.attempt_login(manager.email.upper(), "ManagerPass123").user is not None
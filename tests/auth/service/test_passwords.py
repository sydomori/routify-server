"""
  Changing and resetting passwords and the temp password lifecycle
"""

from datetime import timedelta

import pytest

from app.auth import service
from app.audit import actions
from app.auth.exceptions import (
    NotADriverError,
    UserNotFoundError,
    WeakPasswordError,
    WrongCurrentPasswordError,
)

from app.auth.utils import utcnow, verify_password
from app.extensions import db
from tests.auth.helpers import meta_text

class TestTempPasswordLifecycle:
    def test_onboarding_issues_a_72_hour_password_that_is_delivered_and_works(self, manager, comms):
        driver = service.onboard_driver("Sam", "+254711111111", actor_id=manager.id)
        [(phone, temp_password)] = comms.sent("send_onboarding_sms")

        assert phone == driver.phone
        assert timedelta(hours=71, minutes=59) < driver.temp_password_expires_at - utcnow() <= timedelta(hours=72)
        assert service.attempt_login(phone, temp_password).user.id == driver.id

    def test_changing_a_temp_password_stamps_it_as_used(self, make_user):
        driver = make_user(
            role="driver", must_change_password=True,
            temp_password_expires_at=utcnow() + timedelta(hours=10),
        )
        service.change_password(driver.id, "BrandNewPassword1")
        assert driver.temp_password_used_at is not None
        assert driver.must_change_password is False

    def test_an_invited_manager_never_has_temp_password_fields(self, manager):
        invitee = service.invite_manager("Second", "+254700000002", "second@routify.test", manager)
        assert invitee.temp_password_expires_at is None and invitee.temp_password_used_at is None

class TestChangePassword:
    def test_the_forced_first_change_needs_no_current_password(self, make_user):
        driver = make_user(role="driver", password="TempPass1", must_change_password=True)
        service.change_password(driver.id, "BrandNewPassword1")
        assert verify_password("BrandNewPassword1", driver.password_hash)

    @pytest.mark.parametrize("current", [None, "not-it"], ids=["missing", "wrong"])
    def test_a_voluntary_change_needs_the_right_current_password(self, driver, audit_rows, current):
        with pytest.raises(WrongCurrentPasswordError):
            service.change_password(driver.id, "BrandNewPassword1", current_password=current)
        assert verify_password("DriverPass123", driver.password_hash)   # unchanged
        [row] = audit_rows(action=actions.PASSWORD_CHANGE)
        assert row.outcome == actions.OUTCOME_DENIED
        assert row.meta == {"reason": "wrong_current_password"}

    def test_a_voluntary_change_with_the_right_current_password_works(self, driver, audit_rows):
        service.change_password(driver.id, "BrandNewPassword1", current_password="DriverPass123")
        assert service.attempt_login(driver.phone, "DriverPass123").user is None
        assert service.attempt_login(driver.phone, "BrandNewPassword1").user is not None
        [row] = audit_rows(action=actions.PASSWORD_CHANGE)
        assert row.meta == {"forced": False}

    def test_a_weak_password_is_rejected_audited_and_changes_nothing(self, make_user, audit_rows):
        driver = make_user(role="driver", password="TempPass1", must_change_password=True)
        with pytest.raises(WeakPasswordError):
            service.change_password(driver.id, "short")
        assert driver.must_change_password is True
        assert verify_password("TempPass1", driver.password_hash)
        [row] = audit_rows(action=actions.PASSWORD_CHANGE)
        assert row.outcome == actions.OUTCOME_DENIED and row.meta == {"reason": "weak_password"}

    def test_no_password_ever_reaches_the_audit_log(self, driver, audit_rows):
        service.change_password(driver.id, "BrandNewPassword1", current_password="DriverPass123")
        with pytest.raises(WrongCurrentPasswordError):
            service.change_password(driver.id, "AnotherNewPassword1", current_password="wrong-guess-1")
        for row in audit_rows():
            for secret in ("BrandNewPassword1", "AnotherNewPassword1", "DriverPass123", "wrong-guess-1"):
                assert secret not in meta_text(row)

    def test_an_unknown_user_is_reported(self):
        with pytest.raises(UserNotFoundError):
            service.change_password(99999, "BrandNewPassword1")
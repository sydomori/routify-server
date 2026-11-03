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
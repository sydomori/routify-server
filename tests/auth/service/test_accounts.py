"""
 Service tests: creating accounts(driver onboarding, first-manager-bootstrap, manager-invites)
 Also what is handed to communications and audit logs
"""

import sys

import pytest

from app.audit import actions
from app.auth import service
from app.auth.exceptions import DuplicateUserError, WeakPasswordError
from app.auth.utils import verify_password
from tests.auth.helpers import meta_text

# ------------- Driver onboarding ----------------

@pytest.fixture(params=["module missing", "provider raises", "provider reports failure"])
def sms_cannot_be_sent(request, comms, monkeypatch):
    """The three ways an SMS can fail to go out. Onboarding must survive all of them."""
    if request.param == "module missing":
        monkeypatch.setitem(sys.modules, "app.communications.service", None)
    elif request.param == "provider raises":
        comms.results["send_onboarding_sms"] = RuntimeError("provider down")
    else:
        comms.results["send_onboarding_sms"] = False

class TestOnboardDriver:
    def test_creates_a_gated_pending_driver_with_a_canonical_phone(self, manager, audit_rows):
        driver = service.onboard_driver("Sam Driver", "0711 111 111", actor_id=manager.id)

        assert driver.phone == "+254711111111"
        assert (driver.role, driver.driver_status) == ("driver", "pending_documents")
        assert driver.must_change_password is True and driver.is_active is True
        [row] = audit_rows(action=actions.DRIVER_CREATE)
        assert (row.actor_id, row.entity_id, row.meta) == (manager.id, driver.id, {"sms_sent": True})

    def test_the_temp_password_is_never_stored_in_plaintext(self, comms):
        driver = service.onboard_driver("Sam", "+254711111111")
        [(_, temp_password)] = comms.sent("send_onboarding_sms")
        assert temp_password not in driver.password_hash

    def test_the_same_number_in_another_spelling_is_a_duplicate(self):
        service.onboard_driver("First", "+254711111111")
        with pytest.raises(DuplicateUserError):
            service.onboard_driver("Second", "0711111111")

    def test_a_malformed_phone_is_rejected(self):
        with pytest.raises(ValueError):
            service.onboard_driver("Bad Phone", "not-a-phone")

    def test_the_driver_is_still_created_when_the_sms_cannot_be_sent(
        self, sms_cannot_be_sent, manager, audit_rows
    ):
        driver = service.onboard_driver("Sam", "+254711111111", actor_id=manager.id)
        assert driver.id is not None
        [row] = audit_rows(action=actions.DRIVER_CREATE)
        assert row.meta == {"sms_sent": False}

# ------------ First manager bootstrap ----------------

class TestBootstrapFirstManager:
    def test_the_first_manager_is_created_audited_and_needs_no_password_change(self, audit_rows):
        manager = service.bootstrap_first_manager(
            "Root", "+254700000001", "Root@Routify.test", "RootPassword123"
        )
        assert manager.email == "root@routify.test"
        assert manager.must_change_password is False
        [row] = audit_rows(action=actions.MANAGER_BOOTSTRAP)
        assert (row.actor_id, row.outcome) == (manager.id, actions.OUTCOME_SUCCESS)

    def test_the_door_closes_after_the_first_manager_and_the_attempt_is_audited(self, manager, audit_rows):
        with pytest.raises(PermissionError):
            service.bootstrap_first_manager("Second", "+254700000002", "second@routify.test", "SecondPassword123")
        [row] = audit_rows(action=actions.MANAGER_BOOTSTRAP)
        assert row.actor_id is None and row.outcome == actions.OUTCOME_DENIED
        assert row.meta == {"reason": "already_bootstrapped"}

    def test_a_weak_password_is_rejected(self):
        with pytest.raises(WeakPasswordError):
            service.bootstrap_first_manager("Root", "+254700000001", "root@routify.test", "short")
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

# ------------ Manager invites ----------------

def invite(manager, **overrides):
    """Helper to invite a manager with some defaults, so tests can override just the field they care about"""
    args = dict(name="Second", phone="+254700000002", email="second@routify.test", requesting_user=manager)
    args.update(overrides)
    return service.invite_manager(**args)

class TestInviteManager:
    def test_creates_a_gated_manager_with_a_lowercase_email_and_hands_the_link_over(self, manager, comms):
        invitee = invite(manager, email="Second@Routify.TEST")
        assert (invitee.role, invitee.email, invitee.must_change_password) == ("manager", "second@routify.test", True)
        [(user, link)] = comms.sent("send_manager_invite_email")
        assert user.id == invitee.id and "/accept-invite?token=" in link

    def test_only_a_manager_may_invite(self, driver):
        with pytest.raises(PermissionError):
            invite(driver)

    def test_a_duplicate_email_is_caught_whatever_its_case(self, manager):
        with pytest.raises(DuplicateUserError):
            invite(manager, phone="+254700000009", email=manager.email.upper())

    def test_a_duplicate_phone_is_caught(self, manager, driver):
        with pytest.raises(DuplicateUserError):
            invite(manager, phone=driver.phone, email="unique@routify.test")

    def test_audit_points_at_the_invitee_and_holds_a_hash_never_the_email_or_link(
        self, manager, comms, audit_rows
    ):
        invitee = invite(manager)
        [(_, link)] = comms.sent("send_manager_invite_email")
        [row] = audit_rows(action=actions.MANAGER_INVITE)

        assert (row.actor_id, row.entity_type, row.entity_id) == (manager.id, "User", invitee.id)
        assert row.outcome == actions.OUTCOME_SUCCESS
        assert len(row.meta["invitee_hash"]) == 32
        assert "second@routify.test" not in meta_text(row) and link not in meta_text(row)

    @pytest.mark.parametrize("failure", ["module missing", "provider raises", "provider reports failure"])
    def test_the_manager_is_still_created_when_the_email_cannot_be_sent(
        self, failure, manager, comms, monkeypatch, audit_rows
    ):
        if failure == "module missing":
            monkeypatch.setitem(sys.modules, "app.communications.service", None)
        elif failure == "provider raises":
            comms.results["send_manager_invite_email"] = RuntimeError("smtp down")
        else:
            comms.results["send_manager_invite_email"] = False

        invitee = invite(manager)
        assert invitee.id is not None
        [row] = audit_rows(action=actions.MANAGER_INVITE)
        assert row.outcome == actions.OUTCOME_FAILED

class TestAcceptInvite:
    def invited_token(self, manager):
        invitee = invite(manager)
        return invitee, service._generate_invite_token(invitee.id)

    def test_a_valid_invite_sets_the_password_opens_the_gate_and_is_audited(self, manager, audit_rows):
        invitee, token = self.invited_token(manager)
        user = service.accept_invite(token, "NewManagerPass1")

        assert user.must_change_password is False
        assert verify_password("NewManagerPass1", user.password_hash)
        assert service.attempt_login("second@routify.test", "NewManagerPass1").user is not None
        [row] = audit_rows(action=actions.PASSWORD_CHANGE)
        assert (row.actor_id, row.meta) == (invitee.id, {"forced": True, "via": "invite"})
        assert "NewManagerPass1" not in meta_text(row)

    def test_a_weak_password_is_refused_and_the_invite_stays_usable(self, manager):
        _, token = self.invited_token(manager)
        with pytest.raises(ValueError):
            service.accept_invite(token, "short")
        assert service.accept_invite(token, "NewManagerPass1").must_change_password is False

    def test_an_invite_can_only_be_used_once(self, manager):
        _, token = self.invited_token(manager)
        service.accept_invite(token, "FirstPassword123")
        with pytest.raises(ValueError):
            service.accept_invite(token, "SecondPassword123")

    @pytest.mark.parametrize("make_token", [
        lambda driver: "this-is-not-a-real-token",
        lambda driver: service._generate_invite_token(driver.id),   # a token for a driver
        lambda driver: service._generate_invite_token(99999),       # a token for nobody
    ], ids=["garbage", "points-at-a-driver", "points-at-nobody"])
    def test_a_bad_token_is_rejected(self, driver, make_token):
        with pytest.raises(ValueError):
            service.accept_invite(make_token(driver), "SomePassword12345")
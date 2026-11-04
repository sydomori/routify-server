"""
 Service tests for functions other modules call
 Trucks, trips, documents and communications are written against these and
 a change here will break them even if auth tests still pass
"""

import logging 

import pytest

from app.auth import service
from app.auth.exceptions import (
    InvalidDriverStatusError,
    NoManagerFoundError,
    NotADriverError,
    UserNotFoundError,
)
from app.extensions import db

class TestDriverGuards:
    def test_get_driver_status_returns_the_status(self, driver):
        assert service.get_driver_status(driver.id) == "pending_documents"

    def test_get_driver_status_ignores_is_active_on_purpose(self, driver):
        """Its meaning is document verification only. Activity is a separate question."""
        driver.is_active = False
        db.session.commit()
        assert service.get_driver_status(driver.id) == "pending_documents"

    @pytest.mark.parametrize("status", ["pending_documents", "pending_review", "verified", "rejected"])
    def test_every_valid_status_can_be_set(self, driver, status):
        service.set_driver_status(driver.id, status)
        assert service.get_driver_status(driver.id) == status

    def test_an_invalid_status_is_rejected(self, driver):
        with pytest.raises(InvalidDriverStatusError):
            service.set_driver_status(driver.id, "not_a_real_status")

    @pytest.mark.parametrize("call", [service.get_driver_status, service.is_driver_active],
                             ids=["get_driver_status", "is_driver_active"])
    def test_a_manager_or_a_missing_user_is_reported_not_guessed_at(self, manager, call):
        with pytest.raises(NotADriverError):
            call(manager.id)
        with pytest.raises(UserNotFoundError):
            call(99999)


class TestDeactivation:
    def test_deactivating_blocks_login_flips_is_active_and_is_audited(self, manager, driver, audit_rows):
        from app.audit import actions

        assert service.is_driver_active(driver.id) is True
        service.deactivate_driver(driver.id, actor_id=manager.id)

        assert service.is_driver_active(driver.id) is False
        assert service.attempt_login(driver.phone, "DriverPass123").user is None
        [row] = audit_rows(action=actions.DRIVER_DEACTIVATE)
        assert (row.actor_id, row.entity_type, row.entity_id) == (manager.id, "User", driver.id)

    def test_only_drivers_can_be_deactivated(self, manager):
        with pytest.raises(NotADriverError):
            service.deactivate_driver(manager.id)

class TestGetManagerPhone:
    def test_no_manager_raises_instead_of_returning_a_blank_number(self):
        with pytest.raises(NoManagerFoundError):
            service.get_manager_phone()

    def test_drivers_are_never_returned(self, driver):
        with pytest.raises(NoManagerFoundError):
            service.get_manager_phone()

    def test_with_several_managers_the_earliest_created_is_used_and_arguments_are_ignored(self, make_user):
        first = make_user(role="manager")
        make_user(role="manager")
        assert service.get_manager_phone() == first.phone
        assert service.get_manager_phone(truck_id=999, driver_id=999) == first.phone

def test_get_user_by_id_reports_a_missing_user(driver):
    assert service.get_user_by_id(driver.id).id == driver.id
    with pytest.raises(UserNotFoundError):
        service.get_user_by_id(99999)

class TestCommunicationsSoftDependency:
    """auth must never fail because a message could not be sent, and must never leak the
    message, the recipient or the password into its logs while saying so."""

    def test_a_function_that_returns_nothing_counts_as_sent(self, comms):
        comms.results["send_onboarding_sms"] = None   # older behaviour
        assert service._send_onboarding_sms("+254711111111", "Abcd2345") is True

    def test_false_an_exception_and_a_missing_function_all_count_as_not_sent(self, comms):
        comms.results["send_onboarding_sms"] = False
        assert service._send_onboarding_sms("+254711111111", "Abcd2345") is False

        comms.results["send_onboarding_sms"] = RuntimeError("boom")
        assert service._send_onboarding_sms("+254711111111", "Abcd2345") is False

        del comms.send_password_reset_sms
        assert service._send_password_reset_sms("+254711111111", "Abcd2345") is False

    def test_the_failure_log_names_the_error_type_but_nothing_sensitive(self, comms, caplog):
        comms.results["send_onboarding_sms"] = RuntimeError("Abcd2345 +254711111111 leaked in a provider error")
        with caplog.at_level(logging.INFO):
            service._send_onboarding_sms("+254711111111", "Abcd2345")
        assert "communications_send_failed" in caplog.text and "RuntimeError" in caplog.text
        assert "+254711111111" not in caplog.text and "Abcd2345" not in caplog.text
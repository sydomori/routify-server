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
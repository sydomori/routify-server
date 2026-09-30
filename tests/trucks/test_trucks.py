import pytest

from app.auth.exceptions import UserNotFoundError, NotADriverError
from app.trucks import service
from app.trucks.exceptions import (
    DriverInactiveError,
    DuplicatePlateError,
    TruckBusyError,
    TruckNotFoundError,
)

@pytest.fixture(autouse=True)
def _ctx(app):
    yield

def test_create_normalizes_plate_and_rejects_duplicates():
    t = service.create_truck("kcb 123a", "Isuzu")
    assert t.plate_number == "KCB 123A" and t.status == "idle"
    with pytest.raises(DuplicatePlateError):
        service.create_truck("KCB  123A", "Other")

def test_update_only_allows_plate_and_model():
    t = service.create_truck("KAA 111A", "Isuzu")
    service.update_truck(t.id, model="Fuso")
    assert service.get_truck(t.id).model == "Fuso"
    with pytest.raises(ValueError):
        service.update_truck(t.id, status="active")

def test_get_missing_truck():
    with pytest.raises(TruckNotFoundError):
        service.get_truck(999)

def test_assign_verified_driver(make_user):
    d = make_user(role="driver", driver_status="verified")
    t = service.create_truck("KAA 111A", "Isuzu")
    service.assign_driver(t.id, d.id)
    assert service.get_truck_by_driver(d.id).id == t.id

@pytest.mark.parametrize("status", ["pending_documents", "pending_review", "rejected"])
def test_assign_unverified_driver_rejected(make_user, status):
    d = make_user(role="driver", driver_status=status)
    t = service.create_truck("KAA 111A", "Isuzu")
    with pytest.raises(PermissionError):
        service.assign_driver(t.id, d.id)
    assert service.get_truck(t.id).driver_id is None

def test_assign_inactive_driver_rejected(make_user, db):
    d = make_user(role="driver", driver_status="verified")
    d.is_active = False
    db.session.commit()
    t = service.create_truck("KAA 111A", "Isuzu")
    with pytest.raises(DriverInactiveError):
        service.assign_driver(t.id, d.id)

def test_assign_manager_or_missing_user(make_user, manager):
    t = service.create_truck("KAA 111A", "Isuzu")
    with pytest.raises(NotADriverError):
        service.assign_driver(t.id, manager.id)
    with pytest.raises(UserNotFoundError):
        service.assign_driver(t.id, 9999)

def test_assigning_moves_driver_off_previous_truck(make_user):
    d = make_user(role="driver", driver_status="verified")
    a = service.create_truck("KAA 111A", "Isuzu")
    b = service.create_truck("KBB 222B", "Fuso")
    service.assign_driver(a.id, d.id)
    service.assign_driver(b.id, d.id)
    assert service.get_truck(a.id).driver_id is None
    assert service.get_truck_by_driver(d.id).id == b.id

def test_cannot_reassign_active_truck(make_user):
    d1 = make_user(role="driver", driver_status="verified")
    d2 = make_user(role="driver", driver_status="verified")
    t = service.create_truck("KAA 111A", "Isuzu")
    service.assign_driver(t.id, d1.id)
    service.mark_truck_active(t.id)
    with pytest.raises(TruckBusyError):
        service.assign_driver(t.id, d2.id)
    with pytest.raises(TruckBusyError):
        service.delete_truck(t.id)
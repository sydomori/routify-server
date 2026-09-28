from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.auth.service import get_driver_status, get_user_by_id
from app.auth.exceptions import UserNotFoundError
from app.trucks.models import Truck
from app.trucks.exceptions import (
    DriverInactiveError,
    DuplicatePlateError,
    TruckBusyError,
    TruckInUseError,
    TruckNotFoundError,
)

UPDATABLE_FIELDS = {"plate_number", "model"}

def _normalize_plate(plate:str) -> str:
    #plates are upper cased and whitespace collapsed
    return " ".join(plate.upper().split())

def _plate_taken(
    plate:str,
    exclude_id: int | None = None
) -> bool:
    #selects id of any truck whose plate_number matches
    stmt = db.select(Truck.id).where(Truck.plate_number == plate)
    #skips truck if exclude_id is provided
    if exclude_id is not None:
        stmt = stmt.where(Truck.id != exclude_id)
    return db.session.scalar(stmt) is not None

#-------CRUD----------

def create_truck(
    plate_number:str,
    model: str | None = None,
) -> Truck:
    plate = _normalize_plate(plate_number)
    if _plate_taken(plate):
        raise DuplicatePlateError(f"Plate {plate} already exists")

    truck = Truck(plate_number=plate, model=model,status="idle")
    db.session.add(truck)
    db.session.commit()

    return truck

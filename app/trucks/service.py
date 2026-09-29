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

def list_trucks() -> list[Truck]:
    return list(db.session.scalars(db.select(Truck).order_by(Truck.id)))

def get_truck(truck_id:int) -> Truck:
    truck = db.session.get(Truck,truck_id)
    if truck is None:
        raise TruckNotFoundError(f"Truck {truck_id} not found")

    return truck

def update_truck(
    truck_id: int,
    **fields
) -> Truck:
    unknown = set(fields) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Cannot update:{','.join(sorted(unknown))}")
    truck = get_truck(truck_id)
    if "plate_number" in fields:
        plate = _normalize_plate(fields["plate_number"])
        if _plate_taken(plate,exclude_id=truck_id):
            raise DuplicatePlateError(f"Plate {plate} already exists")
        truck.plate_number = plate

    if "model" in fields:
        truck.model = fields["model"]
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise DuplicatePlateError("Plate already exists")
    return truck 

def delete_truck(truck_id:id):
    truck = get_truck(truck_id)
    if truck.status == "active":
        raise TruckBusyError("Truck is on an active trip")
    db.session.delete(truck)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise TruckInUseError("Truck has trips or issue reports and can't be deleted")


#------Driver assignment-------------------

def assign_driver(
    truck_id:int,
    driver_id: int
) -> Truck:
    """
     Second document verification point after trips.start_trip
     Moving a driver from a truck is allowed after the truck is cleared (one drive per truck)
    """

    truck = get_truck(truck_id)

    if get_driver_status(driver_id) != "verified":
        raise PermissionError("Driver documents not verified")

    #check if driver is active
    if not get_user_by_id(driver_id).is_active:
        raise DriverInactiveError("Driver is inactive")

    #check if driver is already assigned
    if truck.driver_id == driver_id:
        return truck

    #cant assign driver to a truck with an active trip
    if truck.status =="active":
        raise TruckBusyError("Truck is on an active trip")

    previous = get_truck_by_driver(driver_id)
    if previous is not None:
        if previous.status == "active":
            raise TruckBusyError("Driver's current truck is on an active trip")
        previous.driver_id = None
        db.session.flush() #free the unique driver id before reassignment

    truck.driver_id = driver_id
    db.session.commit()
    return truck

def get_truck_by_driver(driver_id: int) -> Truck | None:
    return db.session.scalar(db.select(Truck).where(Truck.driver_id == driver_id))

"""Name/status of assigned driver for listings and summaries"""
def driver_summary(truck:Truck)-> dict | None:
    if truck.driver_id is None:
        return None

    try:
        user = get_user_by_id(truck.driver_id)
    except UserNotFoundError:
        return None
    return {"id":user.id,"name":user.name,"driver_status":user.driver_status}

#------toggle status(called by trips)--------

def mark_truck_active(truck_id: int) -> None:
    truck = get_truck(truck_id)
    truck.status = "active"
    db.session.commit()
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
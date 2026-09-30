"""gives trucks module a clean reuseable way to express expected business errors"""

class TruckError(Exception):
    """
     base class for trucks-module errors
     inherits Exception
    """

    status_code = 400

class TruckNotFoundError(TruckError):
    status_code = 404

class DuplicatePlateError(TruckError):
    status_code = 409

class TruckBusyError(TruckError):
    """Truck is on an active trip"""
    status_code = 409

class TruckInUseError(TruckError):
    """Truck referenced by other records (trips, issues) and can't be deleted"""
    status_code = 409

class DriverInactiveError(PermissionError):
    """Deactivated driver. Subclasses PermissionError so it maps to 403 like
    the unverified-driver guard."""
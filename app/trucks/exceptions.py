"""gives trucks module a clean reuseable way to express expected business errors"""

class TruckError(Exception):
    """
     base class for trucks-module errors
     inherits Exception
    """

    status_code = 400

class TruckNotFoundError(TruckError):
    status_code = 404
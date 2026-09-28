"""gives trucks module a clean reuseable way to express expected business errors"""

class TruckError(Exception):
    """
     base class for trucks-module errors
     inherits 
    """

    status_code = 400
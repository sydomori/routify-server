"""create custom exception errors for auth module"""

class AuthError(Exception):
    """base class for authentication errors"""

class UserNotFoundError(AuthError):
    """raised when a user is not found in the database"""

class DuplicateUserError(AuthError):
    """raised when a user with the same email or phone already exists in the database"""

class InvalidDriverStatusError(AuthError):
    """raised when a driver has an invalid status for the requested operation"""

class NotADriverError(AuthError):
    """raised when a user is not a driver but attempts to perform driver-specific actions"""

class NoManagerFoundError(AuthError):
    """Raised by get_manager_phone() when zero managers exist to notify."""

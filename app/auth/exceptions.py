class AuthError(Exception):
    """Base class for all auth-module errors."""


class UserNotFoundError(AuthError):
    pass


class DuplicateUserError(AuthError):
    """Raised when phone or email already exists."""


class InvalidDriverStatusError(AuthError):
    """Raised when set_driver_status() is called with a value outside DRIVER_STATUSES."""


class NotADriverError(AuthError):
    """Raised when a driver-only operation (status get/set, deactivate) targets a manager."""


class NoManagerFoundError(AuthError):
    """Raised by get_manager_phone() when zero managers exist to notify."""


class WeakPasswordError(AuthError, ValueError):
    """New password fails the policy (NFR-SEC-16). Also a ValueError so the invite/bootstrap
    routes' existing `except ValueError` handlers turn it into a 400."""


class WrongCurrentPasswordError(AuthError):
    """A voluntary password change was attempted without the correct current password."""
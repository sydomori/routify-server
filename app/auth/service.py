import importlib
import logging
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadData

from app.audit import actions
from app.audit.service import hash_identifier, record
from app.auth import lockout
from app.auth.exceptions import (
    DuplicateUserError,
    InvalidDriverStatusError,
    NoManagerFoundError,
    NotADriverError,
    UserNotFoundError,
    WrongCurrentPasswordError,
    WeakPasswordError, 
)
from app.auth.models import DRIVER_STATUSES, User
from app.auth.utils import (
    burn_password_check,
    generate_temp_password,
    hash_password,
    normalize_email,
    normalize_identifier,
    normalize_phone,
    utcnow,
    validate_password_policy,
    verify_password,
)
from app.extensions import db

logger = logging.getLogger(__name__)

_INVITE_TOKEN_SALT = "manager-invite"
_INVITE_TOKEN_MAX_AGE_SECONDS = 48 * 60 * 60  # 48 hours, per spec
TEMP_PASSWORD_LIFETIME = timedelta(hours=72)

@dataclass(frozen=True)
class LoginResult:
    user: User | None = None
    locked: bool = False
    retry_after : int = 0
    reason : str | None = None

# --------- Account creation --------------------

def onboard_driver(
    name: str,
    phone: str,
    actor_id: int | None = None
) -> User:
    """
     Creates a driver User with a generated temp password (valid for 72 hrs)
     must_change_password=True, driver_status='pending_documents'
     password is sent by sms through communications.
     actor_id is the manager, for audit log
    """
    normalized_phone = normalize_phone(phone)
    _ensure_unique_contact(phone=normalized_phone)

    temp_password = generate_temp_password()

    driver = User(
        name=name.strip(),
        phone=normalized_phone,
        role="driver",
        password_hash=hash_password(temp_password),
        must_change_password=True,
        driver_status="pending_documents",
        is_active=True,
        temp_password_expires_at=utcnow() + TEMP_PASSWORD_LIFETIME,
    )
    db.session.add(driver)
    db.session.commit()

    sms_sent = _send_onboarding_sms(normalized_phone, temp_password)

    record(actor_id, actions.DRIVER_CREATE, "User", driver.id, metadata={"sms_sent": sms_sent})
    return driver


def bootstrap_first_manager(
    name: str,
    phone: str,
    email: str,
    password:str
) -> User:
    """
     Only called when 0 managers exist in the system
     Raises Permission error otherwise
     Sets must_change_password = False because this manager chooses the password directly, no invite
     Limitation: two simultaneous first-run requests could observe zero manager exists before either commits
     Is run once & documented rather thn locked
    """

    if User.query.filter_by(role="manager").first() is not None:
        record(None, actions.MANAGER_BOOTSTRAP, outcome=actions.OUTCOME_DENIED,
         metadata={"reason": "already_bootstrapped"}
        )
        raise PermissionError("A manager already exists - bootstrap is a one-time only action")

    validate_password_policy(password)
    normalized_phone = normalize_phone(phone)
    _ensure_unique_contact(phone=normalized_phone, email=email)

    manager = User(
       name=name.strip(),
        phone=normalized_phone,
        email=normalize_email(email),
        role="manager",
        password_hash=hash_password(password),
        must_change_password=False,
        driver_status=None,
        is_active=True, 
    ) 

    db.session.add(manager)
    db.session.commit()

    record(manager.id, actions.MANAGER_BOOTSTRAP, "User", manager.id)
    return manager

def invite_manager(
    name: str,
    phone:str,
    email:str,
    requesting_user: User
) -> User:
    """
     Requesting_user (User sending the link) must have a role="manager" otherwise raise a PermissionError
     Creates a User manager with must_change_password=True with a random password that is never sent to 
     the invitee, only the invite link
     Invitee sets their own password so no temp password or expiry fields
    """

    if requesting_user.role != "manager":
        raise PermissionError("Only an existing manager can invite another manager")

    normalized_phone = normalize_phone(phone)
    normalized_email = normalize_email(email)
    _ensure_unique_contact(phone=normalized_phone, email=normalized_email)

    throwaway_password = generate_temp_password()

    invitee = User(
        name=name.strip(),
        phone=normalized_phone,
        email=normalized_email,
        role="manager",
        password_hash=hash_password(throwaway_password),
        must_change_password=True,
        driver_status=None,
        is_active=True,
    )
    db.session.add(invitee)
    db.session.commit()

    token = _generate_invite_token(invitee.id)
    invite_link = f"{current_app.config['FRONTEND_ORIGIN']}/accept-invite?token={token}"
    email_sent = _send_manager_invite_email(invitee, invite_link)

    record(
        requesting_user.id,
        actions.MANAGER_INVITE,
        "User",
        invitee.id,
        outcome=actions.OUTCOME_SUCCESS if email_sent else actions.OUTCOME_FAILED,
        metadata={"invitee_hash": hash_identifier(normalized_email)},
    )
    return invitee

def accept_invite(token:str, new_password:str) -> User:
    """
     Verifies the signed invite token(48 hr expiry)
     Raises ValueError on an expired, invalid or an already used token
     Raises WeakPasswordError & ValueError if password is too short
     Sets User password and must_change_password=False on success
     Does NOT return a JWT — the invitee calls /auth/login separately afterward
    """

    user_id = _verify_invite_token(token)

    try:
        user = get_user_by_id(user_id)
    except UserNotFoundError:
        raise ValueError("Invalid or expired invite token")

    if user.role != "manager":
        raise ValueError("Invalid or expired invite token")

    if not user.must_change_password:
        raise ValueError("This invite token has already been used")

    validate_password_policy(new_password)

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.session.commit()

    record(user.id, actions.PASSWORD_CHANGE, "User", user.id, metadata={"forced": True, "via": "invite"})
    return user


#------------ Login ------------------------

def authenticate_user(identifier:str, password: str) -> User | None:
    """
     Plain credential check: User or None
     lockout and audit live in attempt_login() which login route uses
    """

    normalized = normalize_identifier(identifier)
    if not normalized or not password:
        return None

    user = _find_user(normalized)
    return user if _credential_failure_reason(user, password) is None else None


def attempt_login(identifier: str, password: str) -> LoginResult:
    """
     FULL LOGIN FLOW 
     1. a locked identifier is refused before any DB lockup or bcrypt work.
     2. credentials are checked : unknown/ inactive/ wrong password/ expired temp password
     3. failures are counted and the 5th inside the window locks the identifier for 15 mins
     4. every outcome is audited with the real reason. Caller shows generic 401
    """

    normalized = normalize_identifier(identifier)
    if not normalized or not password:
        return LoginResult(reason="missing_credentials")

    h = hash_identifier(normalized)

    remaining = lockout.seconds_until_unlocked(h)
    if remaining:
        """ 
         Not audited. Counter absorbs these and doesn't set one row per attempt
         Prevents an attacker from flooding audit_logs
        """
        return LoginResult(locked=True, retry_after=remaining)

    user = _find_user(normalized)
    reason = _credential_failure_reason(user, password)

    if reason is None:
        lockout.clear_failures(h)
        record(user.id, actions.LOGIN_SUCCESS,"User", user.id)
        return LoginResult(user=user)

    actor_id = user.id if user else None
    entity_type = "User" if user else None

    _, newly_locked = lockout.register_failure(h)
    if newly_locked:
        record(
           actor_id, actions.LOGIN_LOCKOUT, entity_type, actor_id,
            outcome=actions.OUTCOME_DENIED,
            metadata={
                "identifier_hash": h,
                "window_seconds": lockout.window_seconds(),
                "max_attempts": lockout.max_attempts(),
            }, 
        )
    else:
        record(
            actor_id, actions.LOGIN_FAILED, entity_type, actor_id,
            outcome=actions.OUTCOME_DENIED,
            metadata={"identifier_hash": h, "reason": reason},
        )

    return LoginResult(reason=reason)

# ------------------- Passwords ------------------------

def change_password(user_id: int, new_password: str, current_password: str | None = None) -> None:
    """
     Sets the new password and must_change_password=False.
     A voluntary change(must_change_password already false) needs the correct current password
     The forced first change after a temp password does not (the user has
     just logged in with it).
     New password must be at least 12 characters
     When it was a forced change of a temp password, temp_password_used_at is stamped
    """

    user = get_user_by_id(user_id)
    forced = user.must_change_password

    if not forced and not (current_password and verify_password(current_password, user.password_hash)):
        record(
            user.id, actions.PASSWORD_CHANGE, "User", user.id,
            outcome=actions.OUTCOME_DENIED, metadata={"reason": "wrong_current_password"}
        )
        raise WrongCurrentPasswordError("Current password is incorrect")

    try:
        validate_password_policy(new_password)
    except WeakPasswordError:
        record(
           user.id, actions.PASSWORD_CHANGE, "User", user.id,
            outcome=actions.OUTCOME_DENIED, metadata={"reason": "weak_password"} 
        )
        raise

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    if forced and user.temp_password_expires_at is not None:
        user.temp_password_used_at = utcnow()

    db.session.commit()

    record(
        user.id, actions.PASSWORD_CHANGE,"User",user.id, metadata={"forced": forced}
    )

def reset_driver_password(driver_id:int, requesting_user:User) -> User:
    """
     Manager issues a driver a fresh temp password(valid for 72 hrs)
     for a driver whose first one was expire or lost.
     The new password goes out by SMS alone
    """
    if requesting_user.role != "manager":
        raise PermissionError("Only a manager can reset a driver's password")

    driver = _get_driver_or_raise(driver_id)
    if not driver.is_active:
        raise ValueError("Cannot reset the password for a deactivated driver")

    temp_password = generate_temp_password()
    driver.password_hash = hash_password(temp_password)
    driver.must_change_password = True
    driver.temp_password_expires_at = utcnow() + TEMP_PASSWORD_LIFETIME
    driver.temp_password_used_at = None
    db.session.commit()

    sms_sent = _send_password_reset_sms(driver.phone, temp_password)

    record(
        requesting_user.id, actions.DRIVER_PASSWORD_RESET, "User", driver.id,
        metadata={"sms_sent": sms_sent}
    )
    return driver

# ------------ Lookups for other modules -------------------

def get_driver_status(driver_id:int) -> str:
    """
     Called by trips.service and trucks.service as a guard check before assigning a truck or
     starting a trip
    """
    driver = _get_driver_or_raise(driver_id)
    return driver.driver_status

def is_driver_active(driver_id:int) -> bool:
    """
     Returns false for a deactivated driver.
     Kept separate from get_driver_status so the functions meaning doesnt change under
     trucks/trips (document verification)
    """
    return _get_driver_or_raise(driver_id).is_active

def set_driver_status(driver_id:int, status:str) -> None:
    """Called by documents.service when a review outcome changes"""
    if status not in DRIVER_STATUSES:
        raise InvalidDriverStatusError(
            f"'{status}' is not a valid driver_status (expected one of {DRIVER_STATUSES})"
        )

    driver = _get_driver_or_raise(driver_id)
    driver.driver_status = status
    db.session.commit()

def deactivate_driver(driver_id:int, actor_id:int | None=None):
    driver = _get_driver_or_raise(driver_id)
    driver.is_active = False
    db.session.commit()
    record(actor_id, actions.DRIVER_DEACTIVATE, "User", driver.id)

def get_user_by_id(user_id:int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"No user with id {user_id}")
    return user

def get_manager_phone(truck_id:int | None=None, driver_id: int | None=None) -> str:
    """
     Resolves the phone number to notify for a given truck/driver context. Called by
     trips.service (truck_id), documents.service (driver_id), and communications' own
     create_issue route (truck_id).

     MVP: truck_id and driver_id are accepted now, purely so every call site is already
     written against the final signature, but both are IGNORED — this returns the phone
     of the earliest-created manager (lowest id), the deterministic stand-in now that
     multiple managers can exist, until truck/driver -> manager assignment exists.
    """

    manager = User.query.filter_by(role="manager").order_by(User.id.asc()).first()
    if manager is None:
        raise NoManagerFoundError("No manager exists to notify")
    return manager.phone


# -------------- Internals --------------------------------

def _find_user(normalized_identifier: str) -> User | None:
    return User.query.filter(
        (User.phone == normalized_identifier) | (User.email == normalized_identifier)
    ).first()

def _credential_failure_reason(user:User | None, password:str) -> str | None:
    if user is None:
        burn_password_check(password)
        return "unknown_account"
    if not user.is_active:
        burn_password_check(password)
        return "inactive_account"
    if not verify_password(password, user.password_hash):
        return "bad_password"
    if _temp_password_expired(user):
        # Only reached with the RIGHT password, so this never tells a stranger anything.
        return "temp_password_expired"
    return None

def _temp_password_expired(user: User) -> bool:
    return (
        user.must_change_password
        and user.temp_password_expires_at is not None
        and user.temp_password_expires_at < utcnow()
    )

def _get_driver_or_raise(driver_id:int) -> User:
    driver = get_user_by_id(driver_id)
    if driver.role != "driver":
        raise NotADriverError(f"User {driver_id} is a '{driver.role}', not a driver")
    return driver

def _ensure_unique_contact(phone:str, email:str | None=None) -> None:
    """
     Shared duplicate check used by onboard_driver / bootstrap_first_manager /
     invite_manager. Raises DuplicateUserError naming whichever field collided first.
    """
    if User.query.filter_by(phone=phone).first() is not None:
        raise DuplicateUserError(f"A user with phone '{phone}' already exists")

    if email is not None and User.query.filter_by(email=normalize_email(email)).first() is not None:
        raise DuplicateUserError(f"A user with email '{email}' already exists")
    
def _generate_invite_token(user_id: int) -> str:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps({"user_id": user_id}, salt=_INVITE_TOKEN_SALT)

def _verify_invite_token(token:str) -> int:
    """
     Verify, decode and extracts user.id from a time limited invite token
    """
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        payload = serializer.loads(
            token, salt=_INVITE_TOKEN_SALT, max_age=_INVITE_TOKEN_MAX_AGE_SECONDS
        )
    except BadData:
        raise ValueError("Invalid or expired invite token")
    return payload["user_id"]

def _deliver(function_name:str, recipient:str, *args) -> bool:
    """
     Calls a communications.service function as a soft dependency: account creation
     doesn't fail because message couldn't go through
     Returns True if it appears to be sent
     Communications functions swallow provider errors themselves and return True/False
     Logs carry a hashed recipient and the exception TYPE only, never the message, phone, email, password or link.
    """
    try:
        #use dynamic importing ie "importlib"
        service = importlib.import_module("app.communications.service")
        result = getattr(service, function_name) (*args)
    except ImportError:
        logger.warning(
            "communications_unavailable: %s not sent (recipient_hash=%s)",
            function_name, hash_identifier(recipient)
        )
        return False
    except Exception as exc:
        logger.error(
           "communications_send_failed: %s (recipient_hash=%s, error_type=%s)",
           function_name, hash_identifier(recipient), type(exc).__name__
        )
        return False
    return result is not False

def _send_onboarding_sms(phone:str, temp_password: str) -> bool:
    return _deliver("send_onboarding_sms", phone, phone, temp_password)

def _send_password_reset_sms(phone:str, temp_password:str) -> bool:
    return _deliver("send_password_reset_sms", phone, phone, temp_password)

def _send_manager_invite_email(user: User, invite_link: str) -> bool:
    return _deliver("send_manager_invite_email", user.email, user, invite_link)

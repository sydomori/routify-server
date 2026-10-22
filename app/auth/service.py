import importlib
import logging
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadData

from app.audit import actions
from app.audit.service import hash_identifier, record
from app.audit import lockout
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
    user: User | None
    locked: bool = False
    retry_after : int = 0
    reason : str | None = None

# --------- Account creation ---------------

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
        user = get_user_by_id(user.id)
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
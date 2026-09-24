import logging
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadData

from app.extensions import db
from app.auth.models import User, ROLES, DRIVER_STATUSES
from app.auth.utils import hash_password, verify_password, generate_temp_password, normalize_phone
from app.auth.exceptions import(
    UserNotFoundError,
    DuplicateUserError,
    NotADriverError,
    InvalidDriverStatusError,
    NoManagerFoundError,
)

#control panel for tracking and logging auth service operations
logger = logging.getLogger(__name__)

_INVITE_TOKEN_SALT = "manager-invite"
_INVITE_TOKEN_MAX_AGE_SECONDS = 48 * 60 * 60

def onboard_driver(
    name:str,
    phone:str
) -> User:
   """
    Create a driver User with a generated temp password, and driver_status='pending documents'
    Calls communications.service.send_onboarding_sms()
   """

   normalized_phone = normalize_phone(phone)

   if User.query.filter_by(phone=normalized_phone).first() is not None:
       raise DuplicateUserError(f"User with phone {normalized_phone} already exists")
 

   temp_password = generate_temp_password()

   driver = User(
       name=name.strip(),
       phone=normalized_phone,
       role="driver",
       password_hash=hash_password(temp_password),
       must_change_password=True,
       driver_status="pending_documents",
       is_active=True         
   )
   db.session.add(driver)
   db.session.commit()

   _send_onboarding_sms(normalized_phone, temp_password)

   return driver

def _send_onboarding_sms(phone:str, temp_password:str):
    """
     makes sure onboard_driver() doesn't fail if communications service doesn't exist or is down 
     the driver will still be created, but they won't receive the onboarding SMS
     manager can relay the temp password manually if needed
     will call communications.service.send_onboarding_sms(phone, temp_password) once it exists
    """

    try:
        from app.communications.service import send_onboarding_sms
        send_onboarding_sms(phone, temp_password)
    except ImportError:
        logger.warning(
            "Communications module not available yet- temp password for %s was Not sent via sms ",
            phone
        )
    except Exception:
        logger.exception(
            "sending onboarding sms failed for %s ", 
            phone
        )

def bootstrap_first_manager(
    name:str,
    phone:str,
    email:str,
    password:str
) -> User:
    """
     only callable when no manager exists
     sets must_change_password to false since no one exists to invite them normally
     closes permanently the instance one manager exists
    """

    if User.query.filter_by(role="manager").first() is not None:
        raise PermissionError("A manager already exists")

    normalized_phone = normalize_phone(phone)
    _ensure_unique_contact(phone=normalized_phone, email=email)

    manager = User (
        name=name.strip(),
        phone=normalized_phone,
        email=email.strip().lower(),
        role="manager",
        password_hash=hash_password(password),
        must_change_password=False,
        driver_status=None,
        is_active=True
    )
    db.session.add(manager)
    db.session.commit()
    return manager

def invite_manager(
    name:str,
    phone:str,
    email:str,
    requesting_user:User
) -> User:
    """
     requesting_user must have a role="manager" otherwise PermissionError is raised
     Creates a User(role="manager,must_change_password=True) with a random password
     Temp password never sent directly, only the invite link matters
    """

    if requesting_user.role != "manager":
        raise PermissionError("Only managers can invite new managers")

    normalized_phone = normalize_phone(phone)
    _ensure_unique_contact(phone=normalized_phone, email=email)

    throwaway_password = generate_temp_password()

    invitee = User(
        name=name.strip(),
        phone=normalized_phone,
        email=email.strip().lower(),
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
    _send_manager_invite_email(invitee,invite_link)

    return invitee

def accept_invite(
    token:str,
    new_password:str
) -> User:
    """
     Verifies signed invite token
     Raises ValueError if expired/used/invalid
     sets password_hash from new_password, and must_change_password to False
     calls auth/login after if successful
    """

    user_id = _verify_invite_token(token)

    try:
        user= get_user_by_id(user_id)
    except UserNotFoundError:
        raise ValueError("Invalid or expired invite token")

    if user.role != "manager":
        raise ValueError("Invite or expired invite token")

    if not user.must_change_password:
        raise ValueError("Invite token has already been used")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.session.commit()

    return user

def _generate_invite_token(
    user_id:int
) -> str:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps({"user_id":user_id}, salt=_INVITE_TOKEN_SALT)


def _verify_invite_token(
    token:str
) -> int:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        payload = serializer.loads(
            token,salt=_INVITE_TOKEN_SALT,max_age=_INVITE_TOKEN_MAX_AGE_SECONDS
        )
    except BadData:
        raise ValueError("Invalid or expired invite token")

    return payload["user_id"]

def _send_manager_invite_email(
    user:User,
    invite_link:str
) -> None:
    """
     same soft dependency pattern as _send_onboarding_sms
     manager is created even if communications.send_email() fails or doesn't exist
     manager can send invite link manually
    """

    try:
        from app.communications.service import send_manager_invite_email
        send_manager_invite_email(user, invite_link)
    except ImportError:
        logger.warning(
            "Communications module not available yet- invite link for %s was Not sent via email ",
            user.email
        )
    except Exception:
        logger.exception(
            "sending manager invite email failed for %s ", 
            user.email
        )

def _ensure_unique_contact(
    phone: str,
    email:str | None = None
) -> None:
    """Shared duplicate check"""
    if User.query.filter_by(phone=phone).first() is not None:
        raise DuplicateUserError(f"A user with phone '{phone}' already exists")
    if email is not None and User.query.filter_by(email=email.strip().lower()).first() is not None:
        raise DuplicateUserError(f"A user with email '{email}' already exists")

def authenticate_user(
    identifier:str,
    password:str
) -> User | None:
    """
    Authenticate a user by their identifier (phone for drivers, email for managers) and password.
    Returns the User object if authentication is successful, otherwise returns None.
    """

    user = User.query.filter(
        (User.phone == identifier) | (User.email == identifier)
    ).first()

    if user is None or not user.is_active:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user

def get_user_by_id(user_id:int) -> User:
    """
    Retrieve a user by their ID.
    Raises UserNotFoundError if the user does not exist.
    """

    user = User.query.get(user_id)
    if user is None:
        raise UserNotFoundError(f"No User with id {user_id}")
    return user

def change_password(
    user_id:int,
    new_password:str
) -> None:
    """
    Sets must_change_password to False and updates the user's password hash.
    """

    user = get_user_by_id(user_id)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.session.commit()

def _get_driver_or_raise(
    driver_id:int
) -> User:
    driver = get_user_by_id(driver_id)
    if driver.role != "driver":
        raise NotADriverError(f"User with id {driver_id} is a '{driver.role}' ")
    return driver

   
def get_driver_status(
    driver_id:int
) -> str:
    """Called by trips.service and trucks.service as a guard check. MUST exist — other
    modules depend on this exact function."""
    driver = _get_driver_or_raise(driver_id)
    return driver.driver_status

def set_driver_status(
    driver_id:int,
    status:str
) -> None:
    """Called by documents.service when review outcomes change"""
    if status not in DRIVER_STATUSES:
        raise InvalidDriverStatusError(
            f"'{status}' is not valid driver_status (expect one of {DRIVER_STATUSES} )"
        )

    driver = _get_driver_or_raise(driver_id)
    driver.driver_status = status
    db.session.commit()

def deactivate_driver(
    driver_id:int
) -> None:
    driver = _get_driver_or_raise(driver_id)
    driver.is_active = False
    db.session.commit()

def get_manager_phone(
    truck_id: int | None = None,
    driver_id:int | None = None
) -> str:
    manager = User.query.filter_by(role="manager").order_by(User.id.asc()).first()
    if manager is None:
        raise NoManagerFoundError("No manager exists to notify")
    return manager.phone
from datetime import datetime, timezone
from app.extensions import db
from app.communications.models import NotificationLog, TruckIssue, utcnow
from app.communications.providers.sms_provider import send_sms
from app.communications.providers.mail_provider import send_email

def _log_notification(recipient, channel,message,status,trip_id=None): 

    log = NotificationLog(
        trip_id=trip_id,
        recipient=recipient,
        channel=channel,
        status=status,
        message=message,
        sent_at=utcnow(),
    )
    db.session.add(log)
    db.session.commit()
    return log

def send_onboarding_sms(
    phone:str,
    temp_password:str
) -> None:
    """called by auth.service.onboard_driver()"""
    message=f"Welcome to Routify. Your temp password is: {temp_password}"
    try:
        send_sms(phone, message)
        _log_notification(phone, "sms", message, "sent")
    except Exception:
        _log_notification(phone, "sms", message, "failed")

def send_manager_invite_email(
    user,
    invite_link:str
) -> None:
    """called by auth.service.onboard_manager()"""
    subject = "You've been invited to Routify"
    body = f"Hi {user.name}, set up your manager account here: {invite_link}"

    try:
        send_email(user.email, subject, body)
        _log_notification(user.email, "email", body, "sent")
    except Exception:
        _log_notification(user.email,"email", body, "failed")


def _get_manager_phone_placeholder() -> str:
    raise NotImplementedError(
        """resolve manager phone number"""
    )

def notify_trip_started(trip) -> None:
    """called by trips.service.start_trip()"""
    manager_phone = _get_manager_phone_placeholder()
    message = f"Trip #{trip.id} started (truck #{trip.truck.id}, driver #{trip.driver.id})."
    try:
        send_sms(manager_phone, message)
        _log_notification(manager_phone, "sms", message, "sent", trip.id)
    except Exception:
        _log_notification(manager_phone, "sms", message, "failed", trip.id)


def notify_trip_ended(trip):
    """called by trips.service.end_trip"""
    manager_phone = _get_manager_phone_placeholder()
    message = f"Trip #{trip.id} ended (truck #{trip.truck.id}, driver #{trip.driver.id})."

    try:
        send_sms(manager_phone, message)
        _log_notification(manager_phone, "sms", message, "sent", trip.id)
    except Exception:
        _log_notification(manager_phone, "sms", message, "failed", trip.id)
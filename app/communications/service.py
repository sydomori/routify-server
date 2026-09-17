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
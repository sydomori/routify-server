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


def notify_trip_started(trip, manager_phone:str) -> None:
    """called by trips.service.start_trip()"""
    message = f"Trip #{trip.id} started (truck #{trip.truck.id}, driver #{trip.driver.id})."
    try:
        send_sms(manager_phone, message)
        _log_notification(manager_phone, "sms", message, "sent", trip.id)
    except Exception:
        _log_notification(manager_phone, "sms", message, "failed", trip.id)


def notify_trip_ended(trip, manager_phone:str) -> None:
    """called by trips.service.end_trip"""
    message = f"Trip #{trip.id} ended (truck #{trip.truck.id}, driver #{trip.driver.id})."

    try:
        send_sms(manager_phone, message)
        _log_notification(manager_phone, "sms", message, "sent", trip.id)
    except Exception:
        _log_notification(manager_phone, "sms", message, "failed", trip.id)


def notify_manager_documents_pending(
    driver_id:int,
    manager_phone:str
) -> None:
    """Called by documents.service.upload_document()"""
    message = f"Driver #{driver_id} has submitted pending documents for review."

    try:
        send_sms(manager_phone, message)
        _log_notification(manager_phone, "sms", message, "sent")
    except Exception:
        _log_notification(manager_phone, "sms", message, "failed")

def report_issue(
    truck_id:int,
    driver_id:int,
    type: str,
    description:str,
    manager_phone:str
) -> TruckIssue:
    """Creates the TruckIssue first — the record persists even if the SMS fails."""
    issue = TruckIssue(
        truck_id=truck_id,
        driver_id=driver_id,
        type=type,
        description=description,
        status="open",
        reported_at=utcnow(),
    )
    db.session.add(issue)
    db.session.commit()

    message = f"Truck #{truck_id} issue reported ({type}): {description}"
    try:
        send_sms(manager_phone, message)
        _log_notification(manager_phone, "sms", message, "sent")
    except Exception:
        _log_notification(manager_phone, "sms", message, "failed")

    return issue

def resolve_issue(issue_id:int) -> TruckIssue:
    issue = TruckIssue.query.get_or_404(issue_id)
    issue.status = "resolved"
    issue.resolved_at = utcnow()
    db.session.commit()
    return issue

def list_issues(
    status: str=None,
    truck_id:int=None
):
    query = TruckIssue.query

    if status is not None:
        query = query.filter_by(status=status)

    if truck_id is not None:
        query = query.filter_by(truck_id=truck_id)

    return query.order_by(TruckIssue.reported_at.desc()).all()

def list_notification_logs():
    return NotificationLog.query.order_by(NotificationLog.sent_at.desc()).all()
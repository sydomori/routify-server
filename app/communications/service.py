from datetime import datetime, timezone
from app.extensions import db
from app.communications.models import NotificationLog, TruckIssue, utcnow
from app.communications.providers.sms_provider import send_sms
from app.communications.providers.mail_provider import send_email

def log_notification(recipient, channel,message,status,trip_id=None): 

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
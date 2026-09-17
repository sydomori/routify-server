from datetime import datetime, timezone
from app.extensions import db

def utcnow():
    return datetime.now(timezone.utc)

class NotificationLog(db.Model):
    __tablename__ = "notification_logs"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=True)
    recipient = db.Column(db.String, nullable=False)
    channel = db.Column(db.String, nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String, nullable=False, default="sent")
    sent_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f"<NOtificationLog {self.id} {self.channel} -> {self.recipient} {self.status}>"
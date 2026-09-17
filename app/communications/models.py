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
        return f"<NotificationLog {self.id} {self.channel} -> {self.recipient} {self.status}>"


class TruckIssue(db.Model):
    __tablename__ = "truck_issues"

    id = db.Column(db.Integer, primary_key=True)
    truck_id = db.Column(db.Integer, db.ForeignKey("trucks.id"), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String, nullable=False)          # "fuel" | "mechanical" | "accident" | "other"
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String, nullable=False, default="open")  # "open" | "resolved"
    reported_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<TruckIssue {self.id} {self.type} {self.status}>"
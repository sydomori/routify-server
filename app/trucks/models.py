from datetime import datetime, timezone
from app.extensions import db

class Truck(db.Model):
    __tablename__ = "trucks"

    id = db.Column(db.Integer, primary_key=True)
    #inert forward-compatible column: nullable, no FK, never filtered on
    organization_id = db.Column(db.Integer,nullable=True)
    plate_number = db.Column(db.String(20), unique=True,nullable=False)
    model = db.Column(db.String(100))
    status = db.Column(db.String(10),nullable=False,default="idle") #active | idle

    #one driver per truck, one truck per driver
    driver_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True,nullable=True
    )
    created_at = db.Column(
        db.DateTime, default=lambda:datetime.now(timezone.utc)
    )
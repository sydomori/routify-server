from app.extensions import db
from app.auth.utils import utcnow


"""
 Allowed values kept as plain constants (not a db enum) so a manager relabling
 them doesn't require a migration
 Validity forced in service.py, not at schema level
"""
ROLES = ("driver", "manager")
DRIVER_STATUSES = ("pending_documents", "pending_review", "verified", "rejected")

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    """
     Forward-compatible only — no organizations table exists yet, so this is a plain
     nullable int with no FK constraint. NOT filtered or enforced on anywhere.
    """
    organization_id = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    # Null for managers — only drivers move through the document verification lifecycle.
    driver_status = db.Column(db.String(30), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    """
     Security: Only set for accounts created with a temporary password (drivers, and
     drivers after a manager reset). Managers set their own password via the invite link,
     so both stay NULL for them. All timestamps are naive UTC (see utils.utcnow).
    """
    temp_password_expires_at = db.Column(db.DateTime, nullable=True)
    temp_password_used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f"<User id={self.id} phone={self.phone} role={self.role}>"
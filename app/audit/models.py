from app.extensions import db

class AuditLog(db.Model):
    """Append only record for sensitive actions that require auditing. This is a security requirement for the system."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    #Nullable : events like a failed login for unknown phone have no actor

    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(64), nullable=False)
    entity_type = db.Column(db.String(64))
    entity_id = db.Column(db.Integer)
    outcome = db.Column(db.String(16), nullable=False) #success, denied, failure
    request_id = db.Column(db.String(64))

    """ 
     `metadata` is reserved on SQLAlchemy declarative models,
      so the Python attribute is called `meta` instead. The column name in the database is still `metadata`.
    """

    meta = db.Column("metadata", db.JSON)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.now()
    )

    """
     __table_args used to define table-level options, constraints and indexes.
     used to optimize queries to find specific log entries instantly

    """

    __table_args__ = (
        #speeds up queries that filter or sort by time
        db.Index("ix_audit_logs_created_at", "created_at"),
        #composite index for queries that filter by actor and time, e.g. "show me all actions by this user in the last 24 hours"
        db.Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        #composite index optimizing searches for actions taken on a specific object
        db.Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        #speeds up queries looking fo specific types of events over time
        db.Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    __mapper_args__ = {"eager_defaults":True} #ensures server_default values are loaded into the model after insert, so we can return the full object to the client without a second query
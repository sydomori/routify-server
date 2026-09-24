from marshmallow import Schema, fields, validate


class TruckIssueCreateSchema(Schema):
    """
    Validates the POST/communications/issues endpoint
    driver_id left out here as it comes from the JWT identity
    """
    truck_id = fields.Int(required=True)
    type = fields.Str(
        required=True,
        validate=validate.OneOf(
            ["fuel", "mechanical", "accident", "other" ]
        ),
    )
    description = fields.Str(load_default="")


class TruckIssueSchema(Schema):
    """Serializes TruckIssue for responses"""
    id = fields.Int(dump_only=True)
    truck_id = fields.Int(dump_only=True)
    driver_id = fields.Int(dump_only=True)
    type = fields.Str(dump_only=True)
    description = fields.Str(dump_only=True)
    status = fields.Str(dump_only=True)
    reported_at = fields.DateTime(dump_only=True)
    resolved_at = fields.DateTime(dump_only=True, allow_none=True)


class NotificationLogSchema(Schema):
    """Serializes a NotificationLog for the manager's logs view."""
    id = fields.Int(dump_only=True)
    trip_id = fields.Int(dump_only=True, allow_none=True)
    recipient = fields.Str(dump_only=True)
    channel = fields.Str(dump_only=True)
    status = fields.Str(dump_only=True)
    sent_at = fields.DateTime(dump_only=True)

issue_create_schema = TruckIssueCreateSchema()
issue_schema = TruckIssueSchema()
issues_schema = TruckIssueSchema(many=True)
logs_schema = NotificationLogSchema(many=True)
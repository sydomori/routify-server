from marshmallow import Schema, fields, validate

class AuditLogSchema(Schema):
    id = fields.Int()
    actor_id = fields.Int(allow_none=True)
    action = fields.Str()
    entity_type = fields.Str(allow_none=True)
    entity_id = fields.Int(allow_none=True)
    outcome = fields.Str()
    request_id = fields.Str(allow_none=True)
    meta = fields.Dict(data_key="metadata", allow_none=True)
    created_at = fields.DateTime()
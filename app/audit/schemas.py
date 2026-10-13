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

class AuditQuerySchema(Schema):
    actor_id = fields.Int(load_default=None)
    entity_type = fields.Str(load_default=None)
    action = fields.Str(load_default=None)
    start = fields.DateTime(load_default=None)
    end = fields.DateTime(load_default=None)
    limit = fields.Int(load_default=50, validate=validate.Range(min=1, max=200))
    offset = fields.Int(load_default=0, validate=validate.Range(min=0))
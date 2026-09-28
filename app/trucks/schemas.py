from marshmallow import Schema, fields, validate

class TruckCreateSchema(Schema):
    plate_number = fields.String(required=True, validate=validate.Length(min=2,max=20))
    model = fields.String(load_default=None,validate=validate.Length(max=100))

    
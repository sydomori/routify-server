from marshmallow import Schema, fields, validate

class TruckCreateSchema(Schema):
    plate_number = fields.String(required=True, validate=validate.Length(min=2,max=20))
    model = fields.String(load_default=None,validate=validate.Length(max=100))

class TruckUpdateSchema(Schema):
   # status and driver_id are deliberately absent: status is driven by trips,
   # driver changes go through the assign-driver route. 

   plate_number = fields.String(validate=validate.Length(min=2,max=20))
   model = fields.String(validate=validate.Length(max=100))

class AssignDriverSchema(Schema):
    driver_id = fields.Integer(required=True,strict=True)

class TruckSchema(Schema):
    id = fields.Integer(dump_only=True)
    plate_number = fields.String(dump_only=True)
    model = fields.String(dump_only=True)
    status = fields.String(dump_only=True)
    driver_id = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
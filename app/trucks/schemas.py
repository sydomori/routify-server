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
    driver_id = fields.String(required=True,strict=True)
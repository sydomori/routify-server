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
        description = fields.Str(load_default="")
    )
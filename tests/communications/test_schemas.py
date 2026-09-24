import pytest
from marshmallow import ValidationError
from app.communications.schemas import TruckIssueCreateSchema

def test_valid_payload_loads_cleanly():
    schema = TruckIssueCreateSchema()
    data = schema.load({"truck_id": 1, "type": "fuel", "description": "Low fuel"})
    assert data == {"truck_id": 1, "type": "fuel", "description": "Low fuel"}
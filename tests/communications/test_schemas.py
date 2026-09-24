import pytest
from marshmallow import ValidationError
from app.communications.schemas import TruckIssueCreateSchema

def test_valid_payload_loads_cleanly():
    schema = TruckIssueCreateSchema()
    data = schema.load({"truck_id": 1, "type": "fuel", "description": "Low fuel"})
    assert data == {"truck_id": 1, "type": "fuel", "description": "Low fuel"}

def test_invalid_type_is_rejected():
    schema = TruckIssueCreateSchema()
    with pytest.raises(ValidationError) as exc_info:
        schema.load({"truck_id": 1, "type": "explosion", "description": "..."})
    assert "type" in exc_info.value.messages

def test_missing_truck_id_is_rejected():
    schema = TruckIssueCreateSchema()
    with pytest.raises(ValidationError) as exc_info:
        schema.load({"type": "fuel"})
    assert "truck_id" in exc_info.value.messages
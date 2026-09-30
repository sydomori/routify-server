from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from marshmallow import ValidationError

from app.auth.decorators import role_required, password_change_required
from app.auth.exceptions import NotADriverError, UserNotFoundError
from app.trucks import service
from app.trucks.exceptions import TruckError
from app.trucks.schemas import (
    AssignDriverSchema,
    TruckCreateSchema,
    TruckSchema,
    TruckUpdateSchema,
)

trucks_bp = Blueprint("trucks",__name__)

_truck_schema = TruckSchema()
_create_schema = TruckCreateSchema
_update_schema = TruckUpdateSchema
_assign_schema = AssignDriverSchema

def _present(truck):
    data = _truck_schema.dump(truck)
    data["driver"] = service.driver_summary(truck)
    return data

def _body():
    return request.get_json(silent=True) or {}

#----Error mapping----------
"""
Error handlers catching the custom exceptions globally
"""
@trucks_bp.errorhandler(ValidationError)
def _validation(err):
    return jsonify({"error":"validation_error", "details": err.messages}), 400
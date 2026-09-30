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

"""Handles exceptions for all its children"""
@trucks_bp.errorhandler(TruckError)
def _truck_error(err):
    return jsonify({"error": str(err)}), err.status_code

@trucks_bp.errorhandler(PermissionError)
def _permission(err):
    return jsonify({"error": str(err)}), 403

@trucks_bp.errorhandler(UserNotFoundError)
def _user_not_found(err):
    return jsonify({"error": "Driver not found"}), 404

@trucks_bp.errorhandler(NotADriverError)
def _not_a_driver(err):
    return jsonify({"error": "User is not a driver"}), 400

#----Routes----------

@trucks_bp.post("/trucks")
@role_required("manager")
@password_change_required
def create_truck_route():
    data = _create_schema.load(_body())
    truck = service.create_truck(**data)
    return jsonify(_present(truck)), 201

@trucks_bp.get("/trucks")
@jwt_required()
@password_change_required
def list_trucks_route():
    return jsonify([_present(truck) for truck in service.list_trucks()]), 200
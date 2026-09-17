from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.communications import service
from marshmallow import ValidationError

from app.auth.decorators import role_required
from app.communications.schemas import(
    issue_create_schema,
    issue_schema,
    issues_schema,
    logs_schema
)

communications_bp = Blueprint("communications", __name__)

@communications_bp.post("/issues")
@jwt_required()
@role_required("driver")
def create_issue():
    try:
        data = issue_create_schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"error": err.messages}), 400

    driver_id = get_jwt_identity()

    #manager_phone = get_manager_phone(truck_id=data["truck_id"])

    issue = service.report_issue(
        truck_id=data["truck_id"],
        driver_id=driver_id,
        type=data["type"],
        description=data["description"],
        #manager_phone=manager_phone,
    )
    return jsonify(issue_schema.dump(issue)), 201


@communications_bp.get("/issues")
@jwt_required()
@role_required("manager")
def get_issues():
    status = request.args.get("status")
    truck_id = request.args.get("truck_id", type=int)
    issues = service.list_issues(status=status, truck_id=truck_id)
    return jsonify(issues_schema.dump(issues)), 200
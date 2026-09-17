from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.communications import service

from app.auth.decorators import role_required

communications_bp = Blueprint("communications", __name__)

@communications_bp.post("/issues")
@jwt_required()
@role_required("driver")
def create_issue():
    data = request.get_json()
    driver_id = get_jwt_identity() #returns user id
    issue = service.report_issue(
        truck_id=data["truck_id"],
        driver_id=driver_id,
        type=data["type"],
        description=data.get("description", "")
    )
    return jsonify({
        "id":issue.id,
        "truck_id":issue.truck_id,
        "type":issue.type,
        "status":issue.status,
        "reported_at":issue.reported_at.isoformat(),
    }), 201
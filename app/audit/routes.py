from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.decorators import manager_required
from .schemas import AuditLogSchema, AuditQuerySchema
from .service import list_audit_logs

audit_bp = Blueprint("audit", __name__)

#no write route as record() is internal only

@audit_bp.get("/logs")
@manager_required
def get_logs():
    try:
        args = AuditQuerySchema().load(request.args)
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400

    logs = list_audit_logs(
        actor_id = args["actor_id"],
        entity_type= args["entity_type"],
        action = args["action"],
        start_date = args["start"],
        end_date = args["end"],
        limit = args["limit"],
        offset = args["offset"],
    )
    return jsonify(AuditLogSchema(many=True).dump(logs)), 200
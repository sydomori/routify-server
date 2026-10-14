from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from marshmallow import ValidationError

from app.auth import service
from app.decorators import password_change_required, role_required
from app.auth.exceptions import (
    DuplicateUserError,
    InvalidDriverStatusError,
    NotADriverError,
    UserNotFoundError
)

from app.auth.schemas import (
    change_password_schema,
    login_schema,
    onboard_driver_schema,
    user_public_schema,
    accept_invite_schema,
    bootstrap_manager_schema,
    invite_manager_schema,
)

auth_bp = Blueprint("auth", __name__)

@auth_bp.post("/onboard-driver")
@role_required("manager")
@password_change_required
def onboard_driver_route():
    try:
        data = onboard_driver_schema.load(request.get_json(silent=True or {}))
    except ValidationError as err:
        return jsonify({"error": "Invalid input", "details": err.messages}), 400

    try:
        driver = service.onboard_driver(name=data["name"], phone=data["phone"])
    except DuplicateUserError as err:
        return jsonify({"error": str(err)}), 409
    except ValueError as err:
        # normalize phone can raise ValueError if the phone number is invalid
        return jsonify({"error": str(err)}), 400

    return jsonify(user_public_schema.dump(driver)), 201

@auth_bp.post("/bootstrap-manager")
def bootstrap_manager_route():
    try:
        data = bootstrap_manager_schema.load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"error":"Invalid input", "details": err.messages}), 400

    try:
        manager = service.bootstrap_first_manager(
            name=data["name"], phone=data["phone"], email=data["email"], password=data["password"]
        )
    except PermissionError as err:
        return jsonify({"error": str(err)}), 403
    except DuplicateUserError as err:
        return jsonify({"error": str(err)}), 409
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    return jsonify(user_public_schema.dump(manager)), 201

@auth_bp.post("/invite-manager")
@role_required("manager")
@password_change_required
def invite_manager_route():
    try:
        data = invite_manager_schema.load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"error": "Invalid input", "details": err.messages}), 400

    requesting_user_id = int(get_jwt_identity())

    try:
        requesting_user = service.get_user_by_id(requesting_user_id)
        invitee = service.invite_manager(
            name=data["name"],
            phone=data["phone"],
            email = data["email"],
            requesting_user=requesting_user,
        )
    except UserNotFoundError as err:
        return jsonify({"error": str(err)}), 404
    except PermissionError as err:
        return jsonify({"error": str(err)}), 403
    except DuplicateUserError as err:
        return jsonify({"error": str(err)}), 409
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    return jsonify(user_public_schema.dump(invitee)), 201


@auth_bp.post("/accept-invite")
def accept_invite_route():
    """
     Public route — security comes from the signed, time-limited token in the body,
     not from an Authorization header. Deliberately does not return a JWT; the invitee
     logs in separately via /auth/login afterward
    """

    try:
        data = accept_invite_schema.load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"error": "Invalid input", "details": err.messages}), 400

    try:
        user = service.accept_invite(data["token"],data["new_password"])
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    return jsonify({"message": "Password set successfully - you can now log in.", "user": user_public_schema.dump(user)}), 200

@auth_bp.post("/login")
def login_route():
    try:
        data = login_schema.load(request.get_json(silent=True) or {})  # request.get_json(silent=True) returns None if request body is empty
    except ValidationError as err:
        return jsonify({"error":"Invalid input", "details": err.messages}), 400

    user = service.authenticate_user(data["identifier"], data["password"])
    if user is None:
        return jsonify({"error":"Invalid credentials"}), 401

    access_token = create_access_token(identity=str(user.id))
    return jsonify(
        {
            "access_token": access_token,
            "must_change_password": user.must_change_password,
            "user": user_public_schema.dump(user),
        }
    ), 200

@auth_bp.post("/change-password")
@jwt_required()
def change_password_route():
    try:
        data = change_password_schema.load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"error": "Invalid input", "details": err.messages}), 400

    user_id = int(get_jwt_identity())
    try:
        service.change_password(user_id, data["new_password"])
    except UserNotFoundError as err:
        return jsonify({"error": str(err)}), 404

    return jsonify({"message": "Password changed successfully"}), 200

@auth_bp.patch("/drivers/<int:driver_id>/deactivate")
@role_required("manager")
@password_change_required
def deactivate_driver_route(driver_id:int):
    try:
        service.deactivate_driver(driver_id)
    except UserNotFoundError as err:
        return jsonify({"error":str(err)}),404
    except NotADriverError as err:
        return jsonify({"error":str(err)}),400

    return jsonify({"message": f"Driver {driver_id} deactivated"}), 200


@auth_bp.get("/me")
@jwt_required()
def me_route():
    user_id = int(get_jwt_identity())
    try:
        user = service.get_user_by_id(user_id)
    except UserNotFoundError as err:
        return jsonify({"error": str(err)}), 404

    return jsonify(user_public_schema.dump(user)), 200



    
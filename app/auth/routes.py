from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity
from marshmallow import ValidationError

from app.auth import service
from app.decorators import active_user_required, password_change_required, role_required
from app.auth.exceptions import (
    DuplicateUserError,
    NotADriverError,
    UserNotFoundError,
    WeakPasswordError,
    WrongCurrentPasswordError
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
        driver = service.onboard_driver(
            name=data["name"], phone=data["phone"], actor_id=int(get_jwt_identity)
        )
    except DuplicateUserError as err:
        return jsonify({"error": str(err)}), 409
    except ValueError as err:
        # normalize phone can raise ValueError if the phone number is malformed
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

    result = service.attempt_login(data['identifier'], data['password'])

    if result.locked:
        response = jsonify(
            {"error":"Too many failed attempts. Try again later","code":"account_locked"}
        )

        response.status_code = 429
        response.headers["Retry-After"] = str(result.retry_after)
        return response

    if result.user is None:
        """
         One generic answer for unknown account, bad password, deactivated account
         expired temp password
         Audit row keeps the real reason
        """
        return jsonify({"error": "Invalid credentials"}), 401

    user = result.user
    return jsonify(
        {
           "access_token": create_access_token(identity=str(user.id), additional_claims={"role": user.role}),
            "refresh_token": create_refresh_token(identity=str(user.id)),
            "must_change_password": user.must_change_password,
            "user": user_public_schema.dump(user),
        }
    ), 200

@auth_bp.post("/refresh")
@active_user_required(refresh=True)
def refresh_route():
    """
     Trades a refresh token for a new access token to keep a user logged in
     without forcing them to re-enter the credentials (tokens expire after 15 mins for security)
    """
    user = service.get_user_by_id(int(get_jwt_identity()))
    return jsonify(
        {"access_token": create_access_token(identity=str(user.id),additional_claims={"role":user.role})}
    ), 200

@auth_bp.post("/change-password")
@active_user_required()
def change_password_route():
    try:
        data = change_password_schema.load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"error": "Invalid input", "details": err.messages}), 400

    user_id = int(get_jwt_identity())
    try:
        service.change_password(user_id, data["new_password"], current_password=data.get("current_password"))
    except WeakPasswordError as err:
        return jsonify({"error":str(err), "code":"weak_password"}), 400
    except WrongCurrentPasswordError as err:
        return jsonify({"error":str(err), "code":"wrong_current_password"}), 403
    except UserNotFoundError as err:
        return jsonify({"error":str(err)}), 404

    return jsonify({"message":"Password changed successfully"}), 200

@auth_bp.patch("/drivers/<int:driver_id>/deactivate")
@role_required("manager")
@password_change_required
def deactivate_driver_route(driver_id:int):
    try:
        service.deactivate_driver(driver_id, actor_id=int(get_jwt_identity()))
    except UserNotFoundError as err:
        return jsonify({"error":str(err)}),404
    except NotADriverError as err:
        return jsonify({"error":str(err)}),400

    return jsonify({"message": f"Driver {driver_id} deactivated"}), 200

@auth_bp.post("/drivers/<int:driver_id>/reset-password")
@role_required("manager")
@password_change_required
def reset_driver_password_route(driver_id:int):
    """
    Issue a driver a new password by SMS if the last one was lost/expired
    New password is never returned in the response
    """
    try:
        requesting_user = service.get_user_by_id(int(get_jwt_identity()))
        service.reset_driver_password(driver_id, requesting_user)
    except UserNotFoundError as err:
        return jsonify({"error": str(err)}), 404
    except NotADriverError as err:
        return jsonify({"error": str(err)}), 404
    except PermissionError as err:
        return jsonify({"error": str(err)}), 403
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    return jsonify({"message":f"A new temporary password was issued to driver {driver_id}"}), 200


@auth_bp.get("/me")
@active_user_required()
def me_route():
    """
     Used by the frontend to identify the current user and check must_change_password/driver_status
     before deciding what to render
     Deliberately NOT behind @password_change_required — the frontend needs this to work
     precisely while a driver is stuck on the forced-password-change screen
    """
    user_id = int(get_jwt_identity())
    try:
        user = service.get_user_by_id(user_id)
    except UserNotFoundError as err:
        return jsonify({"error": str(err)}), 404

    return jsonify(user_public_schema.dump(user)), 200



    
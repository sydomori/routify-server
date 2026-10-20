from marshmallow import Schema, fields, validate
from app.auth.models import User
from app.auth.utils import MIN_PASSWORD_LENGTH

class UserPublicSchema(Schema):
    """
        Schema for serializing public user information.
        set dump_only as they are only used as output only (serialize a user object to JSON)
        is purely used to shape what goes out over the API
    """
    id = fields.Int(dump_only=True)
    organization_id = fields.Int(dump_only=True,allow_none=True)
    name = fields.Str(dump_only=True)
    phone = fields.Str(dump_only=True)
    email = fields.Str(dump_only=True, allow_none=True)
    role = fields.Str(dump_only=True)
    must_change_password = fields.Bool(dump_only=True)
    driver_status = fields.Str(dump_only=True, allow_none=True)
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

class OnboardDriverSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    phone = fields.Str(required=True, validate=validate.Length(min=8, max=20))

class BootstrapManagerSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    phone = fields.Str(required=True, validate=validate.Length(min=8, max=20))
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))

class InviteManagerSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    phone = fields.Str(required=True, validate=validate.Length(min=8, max=20))
    email = fields.Email(required=True)

class AcceptInviteSchema(Schema):
    token = fields.Str(required=True)
    new_password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))


class LoginSchema(Schema):
    identifier = fields.Str(required=True) # phone for drivers, email for managers
    password = fields.Str(required=True ,load_only=True)

class ChangePasswordSchema(Schema):
    """
     password length validation is done in service.py so a rejected or weak password can be audited
    """
    new_password = fields.Str(required=True, load_only=True)

    #Required for voluntary change, ignored for forced change
    current_password = fields.Str(load_only=True)


user_public_schema = UserPublicSchema()
onboard_driver_schema = OnboardDriverSchema()
bootstrap_manager_schema = BootstrapManagerSchema()
invite_manager_schema = InviteManagerSchema()
accept_invite_schema = AcceptInviteSchema()
login_schema = LoginSchema()
change_password_schema = ChangePasswordSchema()
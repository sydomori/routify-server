import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db as _db
from app.auth.models import User
from app.auth.utils import hash_password


"""
set up temporary isolated testing environment
ensures every test runs in a blank db
"""
@pytest.fixture() #tells pytest the function is a set up tool
def app():
    """Fresh app + in-memory DB per test function"""
    application = create_app("testing") #app factory function from app/__init__.py used to create a testing environment
    with application.app_context():
        _db.create_all()
        yield application #run the test
        _db.session.remove() #close the db session. Clears out leftover database transactions
        _db.drop_all() #deletes tables & data created from the test leaving the db empty

@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def make_user(db):
    """
    factory function to create a user in the db
    bypasses the api and directly creates a user in the db
    """
    counter = {"n": 0}
    def _make_user(role="driver", password="Pass1234", **overrides):
        counter["n"] += 1
        n = counter["n"]
        defaults = {
            "name": f"Test {role.title()} {n}",
            "phone": f"+25470000{n:04d}",
            "email": f"{role}{n}@routify.test" if role == "manager" else None,
            "role": role,
            "password_hash": hash_password(password),
            "must_change_password": False,
            "driver_status": "pending_documents" if role == "driver" else None,
            "is_active": True,
        }
        defaults.update(overrides)
        user = User(**defaults)
        db.session.add(user)
        db.session.commit()
        return user

    return _make_user


@pytest.fixture()
def manager(make_user):
    return make_user(role="manager", password="ManagerPass123")

@pytest.fixture()
def driver(make_user):
    return make_user(role="driver", password="DriverPass123")

@pytest.fixture()
def auth_headers(app):
    """ 
    dynamically creates jwt headers for authenticated users passed during tests
    allows you to test endpoints that require authentication or specific roles without manually writing token-generation logic in every test
    """
    def _auth_headers(user):# takes User object (id, role) and uses them to create a unique token
        token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers
"""
deleted once trucks and trips tables are created
minimal stand in tables for testing
"""
if "trucks" not in _db.metadata.tables:
    _db.Table("trucks", _db.metadata, _db.Column("id", _db.Integer, primary_key=True))

if "trips" not in _db.metadata.tables:
    _db.Table("trips", _db.metadata, _db.Column("id", _db.Integer, primary_key=True))
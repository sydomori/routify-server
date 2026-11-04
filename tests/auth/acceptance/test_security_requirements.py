"""
Acceptance tests for the security requirements (end to end through HTTP) of the application. 
The tests ensure that the application adheres to the defined security standards and practices, 
ie. deactivated users loses access, refresh endpoint, temp password expiration, must-change-password restrictions
login lockout & redis failures.
"""

from datetime import timedelta

import pytest

from app.audit import actions
from app.auth.models import User
from app.auth.utils import utcnow
from app.extensions import db
from tests.auth.helpers import bearer, login

def tokens(client, identifier, password):
    """
     Helper function to obtain access and refresh tokens for a given user.
    """
    response = login(client, identifier, password)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    return data["access_token"], data["refresh_token"]

def onboard_a_driver(client, manager, auth_headers, comms, phone="+254711111111"):
    """
     Mimics the real onboarding flow
     Returns (driver_id, the temp password the SMS carried)
    """
    response = client.post(
        "/api/auth/onboard-driver", json={"name": "Sam Driver", "phone": phone}, headers=auth_headers(manager)
    )
    assert response.status_code == 201
    [(_, temp_password)] = comms.sent("send_onboarding_sms")
    return response.get_json()["id"], temp_password 
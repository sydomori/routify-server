"""
 Small shared helpers for the auth tests: plain functions and classes not fixtures
"""
import json

class FakeClock:
    """
     Controllable stand in for time.time() - real system clock
     Allows us to manipulate time so that a 15 minute lockout can now be tested instantly
    """

    #sets up clock with starting timestamp
    def __init__(self, now=1_000_000.0):
        self.now = now

    #turns the class instance into a callable function
    #returns the current timestamp
    def __call__(self):
        return self.now

    #lets us advance the clock forward by a number of seconds
    def advance(self, seconds):
        self.now += seconds

def meta_text(row):
    """
     Converts an audit rows metadata as one string
     For 'this secret never appears' assertions
    """
    return json.dumps(row.meta or {})

def login (client, identifier,password):
    """
     Helper to make a login request
     Takes a test client object, hits and endpoint, packages 
     the identifier and password into a json payload
     Returns the response with the status code
    """
    return client.post(
        "/api/auth/login",
        json={"identifier": identifier, "password": password},
    )

def bearer(token):
    """
     Creates a http header used for authentication
     Takes a token string and formats it into a standard dictionary format
    """
    return {"Authorization": f"Bearer {token}"}


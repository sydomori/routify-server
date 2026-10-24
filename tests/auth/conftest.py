import sys
import types
from unittest.mock import MagicMock

import pytest

from app.auth import lockout
from tests.auth.helpers import FakeClock

@pytest.fixture(autouse=True)
def comms(monkeypatch):
   """
     A fake app.communications.service for every auth test, so no test ever reaches a real
     SMS/email provider and tests can see exactly what auth handed to communications.

     comms.results[name] = False       -> that function reports failure (returns False)
     comms.results[name] = SomeError() -> that function raises it
     comms.sent(name)                  -> list of argument tuples it was called with
   """ 

   fake = types.ModulesTypes("app.communications.service")
   fake.calls = []
   fake.results = {}

   def make(name):
      def send(*args):
         fake.calls.append((name,args))
         outcome = fake.results.get(name, True)
         if isinstance(outcome, Exception):
            raise outcome
         return outcome
      return send

   for fn_name in ("send_onboarding_sms", "send_passwords_reset_sms", "send_manager_invite_email"):
       setattr(fake, fn_name, make(fn_name))

   fake.sent = lambda name: [args for args in fake.calls if args[0] == name]
   monkeypatch.setitem(sys.modules, "app.communications.service", fake)
   return fake

@pytest.fixture()
def lockout_clock(app):
   """wire a controllable clock into the (in-memory) lockout store of this test's app"""
   clock = FakeClock()
   lockout.get_store().clock = clock
   return clock

@pytest.fixture()
def redis_down(app, monkeypatch):
   """
     Make Redis unreachable: the app is told to use Redis, but the client it gets back
     raises ConnectionError on every call, exactly as it would with the server stopped

     The returned mock lets a test Prove Redis was really attempted 
     A fail-open test that never touched Redis would pass for the wrong reason.
   """

   import redis

   broken = MagicMock(name="redis_client")
   refused = redis.exceptions.ConnectionError("Error 111 connecting to localhost:6379. Connection refused")

   for method in ("ttl", "set", "delete", "pipeline", "ping"):
      getattr(broken, method).side_effect = refused

   app.config["LOCKOUT_BACKEND"] = "redis"
   monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: broken)
   return broken
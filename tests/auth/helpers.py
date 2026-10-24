"""
 Small shared helpers for the auth tests: plain functions and classes not fixtures
"""
import json

class FakeClock:
    """
     Controllable stand in for time.time()
     15 minute lockout can now be tested instantly
    """

    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
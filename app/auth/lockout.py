"""
 Per identifier login lockout: % failed logins in a rolling 15
 minutes lock the identifier for 15 minutes

 Counters live in Redis (production and dev via wsl) or in process
 memory(tests, or dev, without Redis running) 

 Keys use hash_identifier(...) of the NORMALIZED identifier, so no
 phone number or email is ever a Redis key

 '0711...' / '+254711...' share one counter

 if the store is unreachable, logins are allowed and the problem is logged at
 ERROR with the fixed message 'lockout_store_unavailable' (search for it, alert on it).
 Trade-off, accepted: whoever can take Redis down also switches the lockout off.
"""

import logging
import time
import uuid

from flask import current_app

logger = logging.getLogger(__name__)

STORE_KEY = "routify_lockout"



class MemoryLockoutStore:
    """
     Is the in memory storage engine
     Used as a fallback storage mechanism when redis isn't running
     ie local development or isolated testing
    """
    def __init__(self, clock=time.time): #allow unit tests to inject a fake clock to simulate the passage of time
        self.clock = clock
        self._failures = {} #A dictionary where keys are hashed user identifiers, and values are lists of timestamps representing when each login failure occurred.
        self._locks = {} #A dictionary tracking locked accounts, mapping hashed identifiers to the exact timestamp when they should be unlocked.


    def retry_after(self, h):
        """
         Checks if hashed identifier h is locked out
         Calculates the remaining seconds of a lockout for the hashed identifier h
         If the time has passes, it deletes the lock from memory and returns 0 (not locked)
         If the lock has not expired, it returns the rounded up seconds left on the lock penalty
        """
        remaining = self._locks.get(h, 0) - self.clock()
        if remaining <= 0:
            self._locks.pop(h, None)
            return 0
        return int(remaining) + 1

    def add_failure(self, h, window): 
        """
         Registers a new failed attempt
         Cleans up memory on the fly filtering out old failure timestamps that
         happened outside the 15 minute window
         Appends the timestamp of the new failure
         Returns the total number of failures recorded within the active window
        """
        now = self.clock()
        recent = [t for t in self._failures.get(h,[]) if t > now - window]
        recent.append(now)
        self._failures[h] = recent
        return len(recent)

    def lock(self, h, seconds):
        """Calculates expiration timestamp and stores it in _locks"""
        self._locks[h] = self.clock() + seconds

    def clear(self, h):
        """Deletes failure history of an identifier"""
        self._failures.pop(h, None)
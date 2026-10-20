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


# ----------------- In Memory Storage Engine --------------
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

#------------ Redis Production Storage Engine ------------
class RedisLockoutStore:
    """
     High performance redis production class
     Relies on Redis data structures to track time windows instead of
     writing to a persistent disk database
    """

    def __init__(self, client): #accepts a pre configured active Redis client connection instance
        self.client=client

    def retry_after(self, h):
        """
        Checks if an account is locked out by querying the Time-To-Live
        (TTL) of the lock key in Redis
        If Redis returns a positive TTL, that is the number of seconds left
        If the key does not exist, it returns O (not locked)    
        """
        ttl = self.client.ttl(f"login:lock:{h}")
        return int(ttl) if ttl and ttl > 0 else 0

    def add_failure(self,h,window):
        key = f"login:fails:{h}"
        now = time.time()
        pipe = self.client.pipeline() #Initialize redis pipeline. Redis commands are batched and sent to the server at once
        pipe.zadd(key, {f"{now}: {uuid.uuid4().hex[:8]}": now}) # Adds the failure to a Redis Sorted Set (ZADD). Combines current timestamp & random string fragment ensuring uniqueness
        pipe.zremrangebyscore(key, 0, now - window) #Delete older entries with timestamp older than the rolling 15 min window
        pipe.zcard(key) #counts how many failure elements are in the sorted set
        pipe.expire(key, window) #Sets the expiration time for the sorted set
        return int(pipe.execute()[2]) #Executes all four commands at once. [2] extracts the output of the 3rd command (zcard), returning the exact failure count.

    def lock(self, h, seconds):
        self.client.set(f"login:lock:{h}", "1", ex=seconds)

    def clear(self, h):
        self.client.delete(f"login:fails:{h}")


# --------------- Store Initialization & Resilience Management ------------

def get_store():
    """
     Implements a single factory pattern
     Checks if a store engine instance already exists in Flask's global extensions
     context dict and returns it immediately to avoid recreating connections
    """
    extensions = current_app.extensions
    store = extensions.get(STORE_KEY)
    if store is not None:
        return store

    try:
        if current_app.config.get("LOCKOUT_BACKEND", "memory") == "redis":
            import redis
            client = redis.Redis.from_url(
                current_app.config["REDIS_URL"],
                socket_connect_timeout=0.5, #Dos protection constraint. If the Redis server is unreachable for more than 0.5 seconds, the lockout is disabled
                socket_timeout=0.5,
                decode_responses=True,
            )
            store = RedisLockoutStore(client)
        else:
            store = MemoryLockoutStore()
    except Exception as exc:
        _log_unavailable(exc)
        return None
    extensions[STORE_KEY] = store
    return store

def _log_unavailable(exc):
    logger.error(
        "lockout_store_unavailable: login lockout is NOT being enforced (error_type=%s)",
        type(exc).__name__,
    )

# ----------- Configuration Helpers ------------
"""
 Read settings dynamically from Flask's configuration, defaulting to 5 attempts and 900 seconds (15 minutes) if unspecified.
"""

def max_attempts():
    return current_app.config.get("LOCKOUT_MAX_ATTEMPTS", 5)

def window_seconds():
    return current_app.config.get("LOCKOUT_WINDOW_SECONDS", 900)

#------------ Public API functions ----------------

"""Functions called by the primary auth views"""

def seconds_until_unlocked(h):
    """
     Used at the beginning of a login endpoint.
     If it returns a num higher than 0, the view immediately blocks the request
     before running any expensive password hashing process
    """
    try:
        store = get_store()
        return store.retry_after(h) if store else 0 #Fail-Open pattern: If the store fails, it returns 0, bypassing the restriction so legitimate traffic isn't blocked
    except Exception as exc:
        _log_unavailable(exc)
        return 0

def register_failure(h):
    """called when a user provides an incorrect password"""
    try:
        store = get_store()
        if store is None:
            return 0, False
        count = store.add_failure(h, window_seconds()) #logs failure and checks the volume within the active timeframe window
        if count >= max_attempts():
            #if count > 5, trigger store.lock() for 15 mins and return True to signal fresh lock initialization
            store.lock(h, window_seconds())
            return count, True
        return count, False
    except Exception as exc:
        _log_unavailable(exc)
        return 0, False

def clear_failures(h):
    """
     Called immediately after a successful login to reset the rolling window counter to 0
    """
    try:
        store = get_store()
        if store:
            store.clear(h)
    except Exception as exc:
        _log_unavailable(exc)

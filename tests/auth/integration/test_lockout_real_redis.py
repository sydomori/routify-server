"""
 INTEGRATION TESTS: the lockout against the real redis sever 
 fakeredis in unit tests is a useful stand in but only the real server proves the 
 key expiry and lockout works as expected. This test suite is skipped unless the
 environment variable TEST_REAL_REDIS is set to a truthy value so the normal suite still passes with
 WSL switched off.

  run them: sudo service redis server start (WSL) then pytest -m integration
  skip them: pytest -m "not integration"
"""

import os
import time
import uuid

import pytest
import redis

from app.audit.service import hash_identifier
from app.auth import service
from app.auth.lockout import RedisLockoutStore
from app.auth.utils import normalize_identifier

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

def _connect():
    try:
        client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=0.5,decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None

pytest = [
    pytest.mark.integration,
    pytest.mark.skipif(_connect() is None, reason="no Redis reachable at REDIS_URL (in WSL: sudo service redis-server start)"),
]


@pytest.fixture()
def client():
    return _connect()

@pytest.fixture()
def key(client):
    value = uuid.uuid4().hex
    yield value
    client.delete(f"login:fails:{value}", f"login:lock:{value}")

def test_failures_expire_out_of_the_window_and_the_lock_expires_by_itself(client, key):
    store = RedisLockoutStore(client)
    store.add_failure(key, 1)
    store.add_failure(key, 1)
    time.sleep(1.2)
    assert store.add_failure(key, 1) == 1          # the old failures slid out

    store.lock(key, 1)
    assert 0 < store.retry_after(key) <= 1
    time.sleep(1.3)
    assert store.retry_after(key) == 0              # Redis removed the lock key itself


def test_login_locks_against_real_redis_and_only_hashed_keys_are_stored(app, client, manager):
    app.config["LOCKOUT_BACKEND"] = "redis"
    app.config["REDIS_URL"] = REDIS_URL
    hashed = hash_identifier(normalize_identifier(manager.email))
    try:
        service.attempt_login(manager.email, "wrong")
        names = client.keys("login:*")
        assert f"login:fails:{hashed}" in names
        assert not any(manager.email in name or manager.phone in name for name in names)

        for _ in range(4):
            service.attempt_login(manager.email, "wrong")
        result = service.attempt_login(manager.email, "ManagerPass123")
        assert result.locked is True and 0 < result.retry_after <= 900
    finally:
        client.delete(f"login:fails:{hashed}", f"login:lock:{hashed}")


def test_a_successful_login_clears_the_counter_in_redis(app, client, manager):
    app.config["LOCKOUT_BACKEND"] = "redis"
    app.config["REDIS_URL"] = REDIS_URL
    hashed = hash_identifier(normalize_identifier(manager.email))
    try:
        for _ in range(3):
            service.attempt_login(manager.email, "wrong")
        assert client.exists(f"login:fails:{hashed}") == 1
        assert service.attempt_login(manager.email, "ManagerPass123").user is not None
        assert client.exists(f"login:fails:{hashed}") == 0
    finally:
        client.delete(f"login:fails:{hashed}", f"login:lock:{hashed}")


def test_a_dead_redis_fails_open_quickly_using_the_real_client_timeouts(app, manager, caplog):
    app.config["LOCKOUT_BACKEND"] = "redis"
    app.config["REDIS_URL"] = "redis://127.0.0.1:1/0"     # nothing listens here
    started = time.monotonic()
    with caplog.at_level("ERROR"):
        for _ in range(6):
            assert service.attempt_login(manager.email, "wrong").locked is False
    assert "lockout_store_unavailable" in caplog.text
    assert time.monotonic() - started < 15            # bounded by the 0.5s timeouts, never hanging
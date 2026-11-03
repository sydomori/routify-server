"""
 Unit tests for the two lockout storage backends run against both, 
 (in-memory and Redis) to ensure they behave the same way. 
 The tests speak to fake Redis, so they don't need a real Redis server to run.
 Whether the real server is running is checked in tests/auth/integration/
"""

import fakeredis
import pytest

from app.auth.lockout import MemoryLockoutStore, RedisLockoutStore, get_store
from tests.auth.helpers import FakeClock

@pytest.fixture(params=["memory", "redis"])
def store(request):
    if request.param == "memory":
        return MemoryLockoutStore(clock=FakeClock())
    return RedisLockoutStore(fakeredis.FakeRedis(decode_responses=True))

class TestEitherBackend:
    def test_a_new_identifier_is_not_locked(self, store):
        assert store.retry_after("abc") == 0

    def test_failures_are_counted_per_identifier(self, store):
        assert [store.add_failure("abc", 900) for _ in range(3)] == [1, 2, 3]
        assert store.add_failure("someone-else", 900) == 1

    def test_clearing_resets_the_count(self, store):
        store.add_failure("abc", 900)
        store.add_failure("abc", 900)
        store.clear("abc")
        assert store.add_failure("abc", 900) == 1

    def test_a_lock_reports_how_long_is_left(self, store):
        store.lock("abc", 900)
        assert 0 < store.retry_after("abc") <= 901

class TestMemoryBackendTime:
    """Time-dependent rules, tested instantly by moving a fake clock."""

    def test_failures_slide_out_of_the_rolling_window(self):
        clock = FakeClock()
        store = MemoryLockoutStore(clock=clock)
        store.add_failure("abc", 900)
        store.add_failure("abc", 900)
        clock.advance(901)
        assert store.add_failure("abc", 900) == 1

    def test_a_lock_expires_by_itself(self):
        clock = FakeClock()
        store = MemoryLockoutStore(clock=clock)
        store.lock("abc", 900)
        clock.advance(899)
        assert store.retry_after("abc") > 0
        clock.advance(2)
        assert store.retry_after("abc") == 0
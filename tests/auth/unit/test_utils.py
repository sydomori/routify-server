"""
UNIT tests: pure functions. No database, no flask app, no HTTP
"""

import pytest

from app.auth.exceptions import WeakPasswordError
from app.auth.utils import (
    generate_temp_password,
    hash_password,
    normalize_email,
    normalize_identifier,
    normalize_phone,
    utcnow,
    validate_password_policy,
    verify_password,
)

class TestPasswordHashing:
    def test_right_password_verifies_wrong_one_does_not_and_nothing_is_stored_in_plaintext(self):
        hashed = hash_password("CorrectHorse1")
        assert hashed != "CorrectHorse1"
        assert verify_password("CorrectHorse1", hashed) is True
        assert verify_password("WrongPassword", hashed) is False

    @pytest.mark.parametrize("bad_hash", ["", "not-a-bcrypt-hash", None])
    def test_a_malformed_stored_hash_is_a_failed_check_not_a_crash(self, bad_hash):
        assert verify_password("anything", bad_hash) is False
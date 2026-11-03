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

class TestPasswordPolicy:
    """
     NRF-SEC-12: at least 12 characters
    """

    def test_exactly_twelve_is_accepted(self):
        validate_password_policy("a" * 12)

    @pytest.mark.parametrize("weak", ["a" * 11, "", None])
    def test_shorter_or_missing_is_rejected(self, weak):
        with pytest.raises(WeakPasswordError):
            validate_password_policy(weak)

class TestTempPasswords:
    def test_default_length_is_eight(self):
        assert len(generate_temp_password()) == 8

    def test_never_uses_characters_that_are_hard_to_read_off_an_sms(self):
        sample = "".join(generate_temp_password(length=64) for _ in range(20))
        assert not (set(sample) & set("0O1lI"))
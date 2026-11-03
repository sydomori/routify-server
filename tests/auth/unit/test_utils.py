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

class TestPhoneNormalization:
    """Every way of writing a Kenyan number must become ONE identity. The lockout counter
    and the duplicate check both depend on it."""

    @pytest.mark.parametrize(
        "raw",
        ["+254711111111", "254711111111", "0711111111", "711111111",
         "00254711111111", "+254 711 111 111", "0711-111-111", "(0711) 111 111"],
    )
    def test_all_spellings_become_one_canonical_number(self, raw):
        assert normalize_phone(raw) == "+254711111111"

    def test_other_countries_keep_their_own_code(self):
        assert normalize_phone("+14155552671") == "+14155552671"

    @pytest.mark.parametrize("invalid", ["not-a-phone", "12345", "", "+0123456789", "+254abc", None])
    def test_junk_is_rejected(self, invalid):
        with pytest.raises(ValueError):
            normalize_phone(invalid)

class TestIdentifierNormalization:
    def test_emails_are_trimmed_and_lowercased(self):
        assert normalize_email("  Jane@Routify.TEST ") == "jane@routify.test"
        assert normalize_identifier("Jane@Routify.test") == "jane@routify.test"

    def test_phone_spellings_converge(self):
        assert normalize_identifier("0711111111") == normalize_identifier("+254 711 111 111")

    def test_junk_gets_a_stable_form_instead_of_raising(self):
        # so it can still be hashed and counted by the lockout like any wrong credential
        assert normalize_identifier("  Some Junk ") == "some junk"
        assert normalize_identifier(None) == ""
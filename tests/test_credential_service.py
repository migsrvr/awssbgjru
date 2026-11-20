import datetime
import re
import pytest

from backend.services.credential_service import (
    hash_password,
    verify_password,
    generate_default_password,
    split_full_name,
    generate_randomized_username,
    generate_org_id,
    generate_api_key,
    hash_api_key,
)


def test_password_hashing_and_verification():
    pw = generate_default_password(12)
    assert len(pw) == 12
    # Must not contain ambiguous chars 0, O, 1, l, I
    for ch in ("0", "O", "1", "l", "I"):
        assert ch not in pw

    hashed = hash_password(pw)
    assert hashed.startswith("pbkdf2_sha256$")
    assert pw not in hashed
    assert verify_password(pw, hashed) is True
    assert verify_password(pw + "x", hashed) is False
    assert verify_password("wrong", "malformed_hash") is False


def test_split_full_name():
    assert split_full_name("Juan Dela Cruz") == ("Juan", "Dela Cruz")
    assert split_full_name("Maria   Clara") == ("Maria", "Clara")
    assert split_full_name("Cher") == ("Cher", "Member")


def test_generate_randomized_username_uniqueness_and_normalization():
    existing = set()
    u1 = generate_randomized_username("Juan", "Dela Cruz", existing)
    assert re.match(r"^j\.delacruz\d{3,4}$", u1)
    assert u1 in existing

    # Accented / special characters
    u2 = generate_randomized_username("José-María", "Ñuñez O'Connor", existing)
    assert re.match(r"^j\.nunezoconnor\d{3,4}$", u2)
    assert u2 != u1


def test_generate_org_id_format_and_sequence():
    existing = set()
    d = datetime.date(2026, 11, 20)
    id1 = generate_org_id(d, existing)
    assert id1 == "AWSSBG-1120-001"
    assert id1 in existing

    id2 = generate_org_id(d, existing)
    assert id2 == "AWSSBG-1120-002"

    # Single digit month and day
    d_jan = datetime.date(2026, 1, 5)
    id_jan = generate_org_id(d_jan, existing)
    assert id_jan == "AWSSBG-0105-001"


def test_generate_api_key():
    raw_key, prefix, key_hash = generate_api_key()
    assert raw_key.startswith("sbg_live_")
    assert len(raw_key) > 30
    assert raw_key.startswith(prefix)
    assert len(prefix) == 15
    assert hash_api_key(raw_key) == key_hash
    assert raw_key != key_hash

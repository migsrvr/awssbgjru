import datetime
import hashlib
import hmac
import re
import secrets
import unicodedata
from typing import Set, Tuple

PBKDF2_ITERATIONS = 260_000
_UNAMBIGUOUS_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_UNAMBIGUOUS_LOWER = "abcdefghijkmnopqrstuvwxyz"
_UNAMBIGUOUS_DIGITS = "23456789"
_UNAMBIGUOUS_SYMBOLS = "!@#$%&*"
_ALL_PASSWORD_CHARS = (
    _UNAMBIGUOUS_UPPER + _UNAMBIGUOUS_LOWER + _UNAMBIGUOUS_DIGITS + _UNAMBIGUOUS_SYMBOLS
)


def hash_password(plaintext: str) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with a random 16-byte salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plaintext.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Constant-time verification of a plaintext password against a stored PBKDF2 hash."""
    if not plaintext or not stored_hash or not stored_hash.startswith("pbkdf2_sha256$"):
        return False
    parts = stored_hash.split("$")
    if len(parts) != 4:
        return False
    try:
        iterations = int(parts[1])
        salt = parts[2]
        expected_hex = parts[3]
    except ValueError:
        return False

    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plaintext.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(dk.hex(), expected_hex)


def generate_default_password(length: int = 12) -> str:
    """
    Generates a cryptographically random temporary password excluding ambiguous
    characters (0, O, 1, l, I) and guaranteed to include upper, lower, digit, and symbol.
    """
    if length < 8:
        length = 8
    chars = [
        secrets.choice(_UNAMBIGUOUS_UPPER),
        secrets.choice(_UNAMBIGUOUS_LOWER),
        secrets.choice(_UNAMBIGUOUS_DIGITS),
        secrets.choice(_UNAMBIGUOUS_SYMBOLS),
    ]
    for _ in range(length - 4):
        chars.append(secrets.choice(_ALL_PASSWORD_CHARS))

    # Cryptographic shuffle using secrets.randbelow
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)


def _ascii_slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", ascii_only)


def split_full_name(full_name: str) -> Tuple[str, str]:
    """Splits a full name into (first_name, last_name)."""
    cleaned = " ".join((full_name or "").strip().split())
    if not cleaned:
        return ("Member", "User")
    parts = cleaned.split(" ", 1)
    if len(parts) == 1:
        return (parts[0], "Member")
    return (parts[0], parts[1])


def generate_randomized_username(
    first_name: str,
    last_name: str,
    existing_usernames: Set[str],
) -> str:
    """
    Generates a randomized, collision-safe lowercase username based on first & last name,
    e.g., 'j.delacruz482'. Mutates `existing_usernames` by adding the newly reserved username.
    """
    first_slug = _ascii_slug(first_name) or "m"
    last_slug = _ascii_slug(last_name) or "member"
    base = f"{first_slug[0]}.{last_slug[:18]}"

    for attempt in range(50):
        digits = (
            f"{secrets.randbelow(900) + 100}"
            if attempt < 25
            else f"{secrets.randbelow(9000) + 1000}"
        )
        candidate = f"{base}{digits}"
        if candidate not in existing_usernames:
            existing_usernames.add(candidate)
            return candidate

    fallback = f"{base}{secrets.token_hex(2)}"
    existing_usernames.add(fallback)
    return fallback


def generate_org_id(
    accepted_date: datetime.date,
    existing_org_ids: Set[str],
) -> str:
    """
    Generates a unique Org ID in the format AWSSBG-MMDD-NNN based on the acceptance Month & Day.
    Automatically increments NNN for that MMDD and adds the new ID to `existing_org_ids`.
    """
    mmdd = accepted_date.strftime("%m%d")
    prefix = f"AWSSBG-{mmdd}-"

    max_seq = 0
    for oid in existing_org_ids:
        if oid.startswith(prefix):
            suffix = oid[len(prefix):]
            if suffix.isdigit():
                seq = int(suffix)
                if seq > max_seq:
                    max_seq = seq

    next_seq = max_seq + 1
    while True:
        candidate = f"{prefix}{next_seq:03d}"
        if candidate not in existing_org_ids:
            existing_org_ids.add(candidate)
            return candidate
        next_seq += 1


def hash_api_key(raw_key: str) -> str:
    """Returns the SHA-256 hex digest of an external API key."""
    return hashlib.sha256((raw_key or "").strip().encode("utf-8")).hexdigest()


def generate_api_key() -> Tuple[str, str, str]:
    """
    Generates a new external API key.
    Returns (raw_key, key_prefix, key_hash).
    """
    token = secrets.token_urlsafe(28).replace("-", "").replace("_", "")[:32]
    raw_key = f"sbg_live_{token}"
    key_prefix = raw_key[:15]
    key_hash = hash_api_key(raw_key)
    return raw_key, key_prefix, key_hash

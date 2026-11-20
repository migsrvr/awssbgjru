import base64
import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple, cast
from dataclasses import dataclass
from fastapi import Header, HTTPException, status, Depends
from backend.database import get_supabase_admin, supabase
from backend.api import config as api_config
from backend.api.config import SUPABASE_URL

AUTH_CACHE_TTL_SECONDS = 60.0
AUTH_CACHE_MAX_ENTRIES = 256
_AUTH_CACHE: Dict[str, Tuple[float, "OfficerUser"]] = {}
_AUTH_CACHE_LOCK = threading.Lock()


def _get_cached_officer(token: str) -> Optional["OfficerUser"]:
    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _AUTH_CACHE_LOCK:
        entry = _AUTH_CACHE.get(key)
        if not entry:
            return None
        expires_at, officer = entry
        if now >= expires_at:
            _AUTH_CACHE.pop(key, None)
            return None
        return officer


def _cache_officer(token: str, officer: "OfficerUser") -> None:
    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _AUTH_CACHE_LOCK:
        if len(_AUTH_CACHE) >= AUTH_CACHE_MAX_ENTRIES:
            expired = [k for k, (exp, _) in _AUTH_CACHE.items() if now >= exp]
            for k in expired:
                _AUTH_CACHE.pop(k, None)
            if len(_AUTH_CACHE) >= AUTH_CACHE_MAX_ENTRIES:
                _AUTH_CACHE.clear()
        _AUTH_CACHE[key] = (now + AUTH_CACHE_TTL_SECONDS, officer)


@dataclass
class OfficerUser:
    id: str
    email: str
    full_name: str
    role: str  # 'reviewer', 'administrator', or 'executive'


def _resolve_dev_role(token_or_header: str) -> Optional[str]:
    if token_or_header in ("dev-executive-token", "executive"):
        return "executive"
    if token_or_header in ("dev-admin-token", "administrator"):
        return "administrator"
    if token_or_header in ("dev-token", "reviewer"):
        return "reviewer"
    return None


def _get_executive_signing_key() -> bytes:
    """Derives the HMAC signing key for built-in Executive tokens."""
    secret = api_config.EXECUTIVE_SECRET or (
        f"{api_config.EXECUTIVE_PASSWORD}:{api_config.SUPABASE_SERVICE_ROLE_KEY or 'awssbg-exec'}"
    )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def authenticate_builtin_executive(raw_login: str, password: str) -> Optional[OfficerUser]:
    """
    Authenticates against the server .env-configured built-in Executive account.
    Returns None if EXECUTIVE_USERNAME or EXECUTIVE_PASSWORD is not configured or credentials do not match.
    """
    configured_user = (api_config.EXECUTIVE_USERNAME or "").strip()
    configured_pass = api_config.EXECUTIVE_PASSWORD or ""
    if not configured_user or not configured_pass:
        return None

    submitted_login = (raw_login or "").strip().lower()
    expected_user = configured_user.lower()
    expected_email = expected_user if "@" in expected_user else f"{expected_user}@awssbgjru.me"

    user_match = hmac.compare_digest(submitted_login, expected_user) or hmac.compare_digest(
        submitted_login, expected_email
    )
    pass_match = hmac.compare_digest(password or "", configured_pass)
    if not (user_match and pass_match):
        return None

    return OfficerUser(
        id="builtin-executive-001",
        email=expected_email,
        full_name=api_config.EXECUTIVE_FULL_NAME or "AWS SBG Executive",
        role="executive",
    )


def create_executive_token(officer: OfficerUser) -> str:
    """Creates a stateless HMAC-SHA256 signed session token (`exec_v1.<payload>.<sig>`)."""
    now = int(time.time())
    ttl_seconds = max(300, int(api_config.EXECUTIVE_SESSION_TTL_HOURS or 12) * 3600)
    payload: Dict[str, Any] = {
        "sub": officer.id,
        "email": officer.email,
        "full_name": officer.full_name,
        "role": "executive",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(_get_executive_signing_key(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"exec_v1.{b64_payload}.{sig}"


def verify_executive_token(token: str) -> Optional[OfficerUser]:
    """Verifies an `exec_v1.<payload>.<sig>` token in constant time and checks expiration."""
    if not token or not token.startswith("exec_v1."):
        return None
    if not api_config.EXECUTIVE_USERNAME or not api_config.EXECUTIVE_PASSWORD:
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None
    _, b64_payload, sig = parts

    expected_sig = hmac.new(
        _get_executive_signing_key(), b64_payload.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        padding = "=" * (-len(b64_payload) % 4)
        payload: Dict[str, Any] = json.loads(base64.urlsafe_b64decode(b64_payload + padding).decode("utf-8"))
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if payload.get("role") != "executive":
            return None
        return OfficerUser(
            id=str(payload.get("sub") or "builtin-executive-001"),
            email=str(payload.get("email") or ""),
            full_name=str(payload.get("full_name") or "AWS SBG Executive"),
            role="executive",
        )
    except Exception:
        return None


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_dev_officer: Optional[str] = Header(None),
) -> OfficerUser:
    """
    Validates Supabase Auth token from Authorization header (Bearer <token>).
    Fetches officer role from `admin_users` table.
    Provides local dev fallback if Supabase is not configured or in dev mode.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()

    # Development fallback if Supabase Auth is not set up or dev tokens are used
    is_dev = not SUPABASE_URL or "localhost" in os.getenv("APP_BASE_URL", "")
    if is_dev and token:
        dev_role = _resolve_dev_role(token)
        if dev_role:
            return OfficerUser(
                id="dev-officer-001",
                email="dev.officer@awssbgjru.local",
                full_name=f"Dev Officer ({dev_role.title()})",
                role=dev_role,
            )

    if not token:
        if is_dev and x_dev_officer:
            role = _resolve_dev_role(x_dev_officer) or "reviewer"
            return OfficerUser(
                id="dev-officer-001",
                email="dev.officer@awssbgjru.local",
                full_name=f"Dev Officer ({role.title()})",
                role=role,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token.startswith("exec_v1."):
        exec_user = verify_executive_token(token)
        if exec_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired executive session token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return exec_user

    cached = _get_cached_officer(token)
    if cached is not None:
        return cached

    # Validate with Supabase
    try:
        client = get_supabase_admin()
        user_res = client.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session token",
            )
        auth_user = user_res.user
        user_id = str(auth_user.id)
        email = str(auth_user.email or "")
        metadata: Dict[str, Any] = cast(Dict[str, Any], auth_user.user_metadata or {})
        full_name = str(metadata.get("full_name") or metadata.get("name") or email.split("@")[0])

        # Check role in admin_users table
        admin_res = (
            client.table("admin_users")
            .select("*")
            .or_(f"id.eq.{user_id},email.eq.{email}")
            .execute()
        )

        if admin_res.data and len(admin_res.data) > 0:
            row = cast(Dict[str, Any], admin_res.data[0])
            officer = OfficerUser(
                id=str(row.get("id") or user_id),
                email=str(row.get("email") or email),
                full_name=str(row.get("full_name") or full_name),
                role=str(row.get("role") or "reviewer"),
            )
            _cache_officer(token, officer)
            return officer

        # Bootstrap support: If admin_users table is empty, first user becomes administrator
        count_res = client.table("admin_users").select("id", count=cast(Any, "exact")).limit(1).execute()
        if getattr(count_res, "count", None) == 0:
            insert_admin: Dict[str, Any] = {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "role": "administrator",
            }
            client.table("admin_users").insert(insert_admin).execute()
            officer = OfficerUser(
                id=user_id,
                email=email,
                full_name=full_name,
                role="administrator",
            )
            _cache_officer(token, officer)
            return officer

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not authorized as an AWS SBG JRU reviewer.",
        )

    except HTTPException:
        raise
    except Exception as e:
        # If in local dev environment and dev token provided, allow dev officer
        if is_dev and token:
            dev_role = _resolve_dev_role(token)
            if dev_role:
                return OfficerUser(
                    id="dev-officer-001",
                    email="dev.officer@awssbgjru.local",
                    full_name=f"Dev Officer ({dev_role.title()})",
                    role=dev_role,
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )


def require_reviewer(user: OfficerUser = Depends(get_current_user)) -> OfficerUser:
    if user.role not in ("reviewer", "administrator", "executive"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer privileges required.",
        )
    return user


def require_admin(user: OfficerUser = Depends(get_current_user)) -> OfficerUser:
    if user.role not in ("administrator", "executive"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )
    return user


def require_executive(user: OfficerUser = Depends(get_current_user)) -> OfficerUser:
    if user.role != "executive":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Executive privileges required.",
        )
    return user

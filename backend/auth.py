import os
from typing import Optional
from dataclasses import dataclass
from fastapi import Header, HTTPException, status, Depends
from backend.database import get_supabase_admin, supabase
from backend.api.config import SUPABASE_URL


@dataclass
class OfficerUser:
    id: str
    email: str
    full_name: str
    role: str  # 'reviewer' or 'administrator'


async def get_current_user(
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

    # Development fallback if Supabase Auth is not set up
    is_dev = not SUPABASE_URL or "localhost" in os.getenv("APP_BASE_URL", "")
    if not token:
        if is_dev and x_dev_officer:
            role = "administrator" if x_dev_officer == "administrator" else "reviewer"
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
        email = auth_user.email or ""
        metadata = auth_user.user_metadata or {}
        full_name = metadata.get("full_name") or metadata.get("name") or email.split("@")[0]

        # Check role in admin_users table
        admin_res = (
            client.table("admin_users")
            .select("*")
            .or_(f"id.eq.{user_id},email.eq.{email}")
            .execute()
        )

        if admin_res.data and len(admin_res.data) > 0:
            row = admin_res.data[0]
            return OfficerUser(
                id=str(row.get("id") or user_id),
                email=row.get("email") or email,
                full_name=row.get("full_name") or full_name,
                role=row.get("role") or "reviewer",
            )

        # Bootstrap support: If admin_users table is empty, first user becomes administrator
        count_res = client.table("admin_users").select("id", count="exact").limit(1).execute()
        if hasattr(count_res, "count") and count_res.count == 0:
            client.table("admin_users").insert({
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "role": "administrator",
            }).execute()
            return OfficerUser(
                id=user_id,
                email=email,
                full_name=full_name,
                role="administrator",
            )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not authorized as an AWS SBG JRU reviewer.",
        )

    except HTTPException:
        raise
    except Exception as e:
        # If in local dev environment and token provided is 'dev-token', allow dev officer
        if is_dev and token in ("dev-token", "dev-admin-token"):
            dev_role = "administrator" if token == "dev-admin-token" else "reviewer"
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
    if user.role not in ("reviewer", "administrator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer privileges required.",
        )
    return user


def require_admin(user: OfficerUser = Depends(get_current_user)) -> OfficerUser:
    if user.role != "administrator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )
    return user

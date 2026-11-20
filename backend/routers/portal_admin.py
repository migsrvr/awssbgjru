from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from backend.auth import OfficerUser, require_executive
from backend.schemas.portal_members import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyItem,
    BulkCsvGenerateRequest,
    BulkFromApprovedRequest,
    BulkGenerationResponse,
    MemberStatusUpdateRequest,
    OrgMemberItem,
    OrgMemberListResponse,
    PasswordResetResponse,
    UnprovisionedApplicantItem,
    ValidationLogItem,
)
from backend.services.member_portal_service import (
    bulk_generate_from_approved,
    bulk_generate_from_csv,
    create_api_key,
    list_api_keys,
    list_org_members,
    list_unprovisioned_approved,
    list_validation_logs,
    reset_and_email_member_password,
    revoke_api_key,
    update_member_status,
)
from backend.services.sync_service import bump_sync_version

router = APIRouter(prefix="/api/v1/admin/portal", tags=["admin-portal"])


@router.get("/unprovisioned-approved", response_model=List[UnprovisionedApplicantItem])
def get_unprovisioned_approved_endpoint(
    user: OfficerUser = Depends(require_executive),
):
    """Lists approved applicants from `registrations` who do not yet have portal credentials."""
    return list_unprovisioned_approved()


@router.post("/members/generate-from-approved", response_model=BulkGenerationResponse)
def generate_from_approved_endpoint(
    payload: BulkFromApprovedRequest,
    user: OfficerUser = Depends(require_executive),
):
    """Bulk generates credentials for approved applicants and emails them directly (Executive only)."""
    res = bulk_generate_from_approved(
        registration_ids=payload.registration_ids,
        officer_id=user.id,
        officer_name=user.full_name,
    )
    bump_sync_version("portal_members", event="bulk_generate_approved")
    return res


@router.post("/members/generate-from-csv", response_model=BulkGenerationResponse)
def generate_from_csv_endpoint(
    payload: BulkCsvGenerateRequest,
    user: OfficerUser = Depends(require_executive),
):
    """Bulk generates credentials from CSV rows and emails students directly (Executive only)."""
    res = bulk_generate_from_csv(
        rows=payload.members,
        officer_id=user.id,
        officer_name=user.full_name,
    )
    bump_sync_version("portal_members", event="bulk_generate_csv")
    return res


@router.get("/members", response_model=OrgMemberListResponse)
def list_members_endpoint(
    search: Optional[str] = Query(None, description="Search by name, Org ID, username, or email"),
    status: Optional[str] = Query(None, description="Filter by active, suspended, or revoked"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: OfficerUser = Depends(require_executive),
):
    """Lists provisioned centralized org members (Executive only)."""
    return list_org_members(
        search=search,
        status_filter=status,
        page=page,
        page_size=page_size,
    )


@router.post("/members/{member_id}/reset-password", response_model=PasswordResetResponse)
def reset_member_password_endpoint(
    member_id: str,
    user: OfficerUser = Depends(require_executive),
):
    """Rotates a member's password hash and emails a fresh temporary password to the student."""
    res = reset_and_email_member_password(
        member_id=member_id,
        officer_id=user.id,
        officer_name=user.full_name,
    )
    bump_sync_version("portal_members", event="reset_member_password")
    return res


@router.patch("/members/{member_id}/status", response_model=OrgMemberItem)
def update_member_status_endpoint(
    member_id: str,
    payload: MemberStatusUpdateRequest,
    user: OfficerUser = Depends(require_executive),
):
    """Updates a member's status between active, suspended, and revoked."""
    res = update_member_status(
        member_id=member_id,
        new_status=payload.status,
        officer_id=user.id,
        officer_name=user.full_name,
    )
    bump_sync_version("portal_members", event=f"member_status_{payload.status}")
    return res


@router.get("/api-keys", response_model=List[ApiKeyItem])
def get_api_keys_endpoint(
    user: OfficerUser = Depends(require_executive),
):
    """Lists all external system API keys (Executive only)."""
    return list_api_keys()


@router.post("/api-keys", response_model=ApiKeyCreatedResponse)
def create_api_key_endpoint(
    payload: ApiKeyCreateRequest,
    user: OfficerUser = Depends(require_executive),
):
    """Creates a new external system API key and returns the raw key once (Executive only)."""
    res = create_api_key(
        name=payload.name,
        rate_limit_per_min=payload.rate_limit_per_min,
        officer_id=user.id,
        officer_name=user.full_name,
    )
    bump_sync_version("portal_api_keys", event="api_key_created")
    return res


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyItem)
def revoke_api_key_endpoint(
    key_id: str,
    user: OfficerUser = Depends(require_executive),
):
    """Revokes an external system API key immediately (Executive only)."""
    res = revoke_api_key(
        key_id=key_id,
        officer_id=user.id,
        officer_name=user.full_name,
    )
    bump_sync_version("portal_api_keys", event="api_key_revoked")
    return res


@router.get("/validation-logs", response_model=List[ValidationLogItem])
def get_validation_logs_endpoint(
    limit: int = Query(50, ge=1, le=200),
    user: OfficerUser = Depends(require_executive),
):
    """Lists recent external credential validation events (Executive only)."""
    return list_validation_logs(limit=limit)

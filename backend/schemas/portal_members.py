from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class UnprovisionedApplicantItem(BaseModel):
    registration_id: int
    full_name: str
    student_id: Optional[str] = None
    email: str
    year: Optional[str] = None
    program: Optional[str] = None
    division_type: Optional[str] = None
    division_name: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: Optional[str] = None


class BulkFromApprovedRequest(BaseModel):
    registration_ids: List[int] = Field(..., min_length=1, max_length=200)


class CsvMemberInput(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    email: str = Field(..., min_length=3, max_length=150)
    student_id: Optional[str] = None
    year: Optional[str] = None
    program: Optional[str] = None
    division_type: Optional[str] = None
    division_name: Optional[str] = None
    accepted_date: Optional[str] = None  # YYYY-MM-DD optional


class BulkCsvGenerateRequest(BaseModel):
    members: List[CsvMemberInput] = Field(..., min_length=1, max_length=500)


class GeneratedMemberSummary(BaseModel):
    """Safe generation result summary — NEVER exposes plaintext password or password_hash."""
    id: str
    org_id: str
    username: str
    full_name: str
    email: str
    division_name: Optional[str] = None
    accepted_date: str
    email_status: Literal["sent", "failed", "dry_run"]
    email_error: Optional[str] = None


class BulkRowError(BaseModel):
    row_index: int
    identifier: str
    error: str


class BulkGenerationResponse(BaseModel):
    generated_count: int
    emailed_count: int
    failed_count: int
    members: List[GeneratedMemberSummary]
    errors: List[BulkRowError] = Field(default_factory=list)


class OrgMemberItem(BaseModel):
    """Safe directory representation — excludes password_hash."""
    id: str
    registration_id: Optional[int] = None
    org_id: str
    username: str
    first_name: str
    last_name: str
    full_name: str
    email: str
    student_id: Optional[str] = None
    year: Optional[str] = None
    program: Optional[str] = None
    division_type: Optional[str] = None
    division_name: Optional[str] = None
    accepted_date: str
    status: Literal["active", "suspended", "revoked"]
    must_change_password: bool = True
    credentials_emailed_at: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class OrgMemberListResponse(BaseModel):
    members: List[OrgMemberItem]
    total: int
    page: int
    page_size: int


class MemberStatusUpdateRequest(BaseModel):
    status: Literal["active", "suspended", "revoked"]


class PasswordResetResponse(BaseModel):
    member_id: str
    org_id: str
    username: str
    email: str
    email_status: Literal["sent", "failed", "dry_run"]
    email_error: Optional[str] = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    rate_limit_per_min: int = Field(default=60, ge=1, le=10000)


class ApiKeyItem(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: List[str]
    rate_limit_per_min: int
    is_active: bool
    last_used_at: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    revoked_at: Optional[str] = None


class ApiKeyCreatedResponse(ApiKeyItem):
    """Returned ONCE at creation time so the Executive can configure the external system."""
    api_key: str


class ValidationLogItem(BaseModel):
    id: str
    api_key_id: Optional[str] = None
    api_key_name: Optional[str] = None
    org_id_attempted: Optional[str] = None
    username_attempted: Optional[str] = None
    outcome: str
    client_ip: Optional[str] = None
    created_at: Optional[str] = None


class ExternalValidateRequest(BaseModel):
    org_id: str = Field(..., min_length=3, max_length=40)
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class ExternalMemberProfile(BaseModel):
    org_id: str
    username: str
    first_name: str
    last_name: str
    full_name: str
    email: str
    student_id: Optional[str] = None
    year: Optional[str] = None
    program: Optional[str] = None
    division_type: Optional[str] = None
    division_name: Optional[str] = None
    status: str
    must_change_password: bool = True


class ExternalValidateResponse(BaseModel):
    valid: bool
    reason: Optional[Literal["invalid_credentials", "inactive_member"]] = None
    member: Optional[ExternalMemberProfile] = None

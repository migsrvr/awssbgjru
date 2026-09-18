from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class OfficerResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: OfficerResponse



class ApplicationReviewItem(BaseModel):
    id: str
    reviewer_id: str
    reviewer_name: str
    decision: str
    reason_code: Optional[str] = None
    internal_notes: Optional[str] = None
    rubric_scores: Dict[str, bool] = Field(default_factory=dict)
    created_at: str


class EmailLogItem(BaseModel):
    id: str
    template_id: Optional[str] = None
    recipient_email: str
    subject: str
    delivery_status: str
    error_message: Optional[str] = None
    sent_at: str


class ApplicationSummary(BaseModel):
    id: int
    full_name: str
    student_id: str
    email: str
    year: str
    program: str
    division_type: str
    division_name: str
    application_status: str
    created_at: str
    assigned_reviewer_id: Optional[str] = None
    assigned_reviewer_name: Optional[str] = None
    claimed_at: Optional[str] = None


class ApplicationDetail(ApplicationSummary):
    dob: Optional[str] = None
    photo_base64: Optional[str] = None
    explanation: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    decision_reason_code: Optional[str] = None
    revision_token: Optional[str] = None
    revision_deadline: Optional[str] = None
    revision_notes: Optional[str] = None
    reviews: List[ApplicationReviewItem] = Field(default_factory=list)
    email_logs: List[EmailLogItem] = Field(default_factory=list)


class QueueResponse(BaseModel):
    applications: List[ApplicationSummary]
    total: int
    page: int
    page_size: int
    status_counts: Dict[str, int]


class ApplicationClaimRequest(BaseModel):
    pass


class InternalNotesRequest(BaseModel):
    notes: str


class ApplicationDecisionRequest(BaseModel):
    decision: Literal["approved", "declined", "revision_requested", "pending"]
    reason_code: Optional[str] = None
    internal_notes: Optional[str] = None
    rubric_scores: Dict[str, bool] = Field(default_factory=dict)
    # Email options
    send_email: bool = True
    next_steps: Optional[str] = None
    revision_notes: Optional[str] = None
    revision_deadline: Optional[str] = None
    decline_reason: Optional[str] = None
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None
    # Banner and QR customization
    header_banner_url: Optional[str] = None
    footer_banner_url: Optional[str] = None
    general_chat_link: Optional[str] = None
    general_qr_base64: Optional[str] = None
    division_chat_link: Optional[str] = None
    division_qr_base64: Optional[str] = None


class EmailPreviewRequest(BaseModel):
    template_id: str
    next_steps: Optional[str] = None
    revision_notes: Optional[str] = None
    revision_deadline: Optional[str] = None
    decline_reason: Optional[str] = None
    header_banner_url: Optional[str] = None
    footer_banner_url: Optional[str] = None
    general_chat_link: Optional[str] = None
    general_qr_base64: Optional[str] = None
    division_chat_link: Optional[str] = None
    division_qr_base64: Optional[str] = None


class EmailPreviewResponse(BaseModel):
    template_id: str
    subject: str
    body: str
    recipient_email: str
    variables: Dict[str, str]
    html_preview: Optional[str] = None


class EmailSendRequest(BaseModel):
    template_id: Optional[str] = None
    subject: str
    body: str
    html_body: Optional[str] = None
    header_banner_url: Optional[str] = None
    footer_banner_url: Optional[str] = None
    general_qr_base64: Optional[str] = None
    division_qr_base64: Optional[str] = None


class EmailTemplateItem(BaseModel):
    id: str
    name: str
    subject: str
    body: str
    variables: List[str]
    version: int
    is_active: bool
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class EmailTemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    subject: str
    body: str
    is_active: Optional[bool] = True


class SystemSettingsResponse(BaseModel):
    registration_open: bool
    closed_message: str
    qualification_rubric: List[Dict[str, Any]]


class SystemSettingsUpdateRequest(BaseModel):
    registration_open: Optional[bool] = None
    closed_message: Optional[str] = None
    qualification_rubric: Optional[List[Dict[str, Any]]] = None


class RevisionViewResponse(BaseModel):
    full_name: str
    student_id: str
    email: str
    year: str
    program: str
    division_type: str
    division_name: str
    explanation: str
    revision_notes: str
    revision_deadline: Optional[str] = None
    photo_base64: Optional[str] = None


class RevisionSubmitRequest(BaseModel):
    explanation: Optional[str] = None
    photo_base64: Optional[str] = None
    division_type: Optional[str] = None
    division_name: Optional[str] = None

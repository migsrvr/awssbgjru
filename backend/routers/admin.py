import io
import csv
import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.auth import OfficerUser, require_reviewer, require_admin
from backend.database import get_supabase_admin
from backend.schemas.admin import (
    OfficerResponse,
    QueueResponse,
    ApplicationDetail,
    ApplicationDecisionRequest,
    InternalNotesRequest,
    EmailPreviewRequest,
    EmailPreviewResponse,
    EmailSendRequest,
    EmailTemplateItem,
    EmailTemplateUpdateRequest,
    SystemSettingsResponse,
    SystemSettingsUpdateRequest,
)
from backend.services.application_service import (
    get_application_queue,
    get_application_detail,
    claim_application,
    release_application,
    add_internal_note,
    record_decision,
    get_system_settings,
    update_system_settings,
)
from backend.services.email_service import (
    get_template,
    preview_email,
    send_email,
    DEFAULT_TEMPLATES,
)
from backend.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/me", response_model=OfficerResponse)
async def get_me(user: OfficerUser = Depends(require_reviewer)):
    """Returns the authenticated officer's identity and role."""
    return OfficerResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


@router.get("/applications", response_model=QueueResponse)
async def list_applications(
    status: Optional[str] = Query(None, description="Filter by status (new, under_review, approved, etc.)"),
    search: Optional[str] = Query(None, description="Search by name, student ID, or email"),
    year: Optional[str] = Query(None, description="Filter by school year"),
    program: Optional[str] = Query(None, description="Filter by program"),
    division_type: Optional[str] = Query(None, description="Filter by division type (office or skillbuilder)"),
    reviewer_id: Optional[str] = Query(None, description="Filter by assigned reviewer ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: OfficerUser = Depends(require_reviewer),
):
    """Lists applications with multi-attribute filtering, search, and queue counts."""
    data = get_application_queue(
        status_filter=status,
        search=search,
        year=year,
        program=program,
        division_type=division_type,
        reviewer_id=reviewer_id,
        page=page,
        page_size=page_size,
    )
    return data


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
async def get_application(
    application_id: int,
    user: OfficerUser = Depends(require_reviewer),
):
    """Retrieves full application details, responses, review history, and email logs."""
    return get_application_detail(application_id)


@router.post("/applications/{application_id}/claim")
async def claim(
    application_id: int,
    user: OfficerUser = Depends(require_reviewer),
):
    """Assigns the application to the requesting reviewer with a 30-minute lock."""
    res = claim_application(application_id, user.id, user.full_name)
    return {"success": True, "message": "Application claimed successfully", "application": res}


@router.post("/applications/{application_id}/release")
async def release(
    application_id: int,
    user: OfficerUser = Depends(require_reviewer),
):
    """Releases the application claim back to the unassigned queue."""
    res = release_application(application_id, user.id, user.full_name)
    return {"success": True, "message": "Application released", "application": res}


@router.post("/applications/{application_id}/notes")
async def add_notes(
    application_id: int,
    payload: InternalNotesRequest,
    user: OfficerUser = Depends(require_reviewer),
):
    """Adds an internal reviewer note to the application."""
    if not payload.notes.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty")
    res = add_internal_note(application_id, payload.notes.strip(), user.id, user.full_name)
    return {"success": True, "review": res}


@router.post("/applications/{application_id}/decision")
async def submit_decision(
    application_id: int,
    payload: ApplicationDecisionRequest,
    user: OfficerUser = Depends(require_reviewer),
):
    """Records an approved, declined, revision-requested, or pending decision."""
    res = record_decision(
        application_id=application_id,
        decision=payload.decision,
        officer_id=user.id,
        officer_name=user.full_name,
        reason_code=payload.reason_code,
        internal_notes=payload.internal_notes,
        rubric_scores=payload.rubric_scores,
        send_email_now=payload.send_email,
        next_steps=payload.next_steps,
        revision_notes=payload.revision_notes,
        revision_deadline=payload.revision_deadline,
        decline_reason=payload.decline_reason,
        custom_subject=payload.custom_subject,
        custom_body=payload.custom_body,
    )
    return res


@router.post("/applications/{application_id}/email/preview", response_model=EmailPreviewResponse)
async def preview_application_email(
    application_id: int,
    payload: EmailPreviewRequest,
    user: OfficerUser = Depends(require_reviewer),
):
    """Generates a populated preview of an email using the applicant's record and selected template."""
    app = get_application_detail(application_id)
    subject, body, variables = preview_email(
        applicant=app,
        template_id=payload.template_id,
        next_steps=payload.next_steps,
        revision_notes=payload.revision_notes,
        revision_deadline=payload.revision_deadline,
        decline_reason=payload.decline_reason,
    )
    return EmailPreviewResponse(
        template_id=payload.template_id,
        subject=subject,
        body=body,
        recipient_email=app["email"],
        variables=variables,
    )


@router.post("/applications/{application_id}/email/send")
async def send_application_email(
    application_id: int,
    payload: EmailSendRequest,
    user: OfficerUser = Depends(require_reviewer),
):
    """Sends a reviewed email draft to the applicant."""
    app = get_application_detail(application_id)
    res = send_email(
        recipient_email=app["email"],
        subject=payload.subject,
        body=payload.body,
        registration_id=application_id,
        template_id=payload.template_id,
        sender_id=user.id,
    )
    log_action(
        actor_id=user.id,
        actor_name=user.full_name,
        action="send_custom_email",
        target_type="registration",
        target_id=str(application_id),
        details={"subject": payload.subject, "result": res},
    )
    return res


@router.get("/templates", response_model=List[EmailTemplateItem])
async def list_templates(user: OfficerUser = Depends(require_reviewer)):
    """Lists all active email templates."""
    client = get_supabase_admin()
    templates = []
    try:
        res = client.table("email_templates").select("*").order("name").execute()
        for row in res.data or []:
            templates.append(EmailTemplateItem(
                id=row["id"],
                name=row["name"],
                subject=row["subject"],
                body=row["body"],
                variables=row.get("variables", []),
                version=row.get("version", 1),
                is_active=row.get("is_active", True),
                updated_at=row.get("updated_at"),
                updated_by=row.get("updated_by"),
            ))
    except Exception:
        pass

    if not templates:
        for tid, tval in DEFAULT_TEMPLATES.items():
            templates.append(EmailTemplateItem(
                id=tid,
                name=tval["name"],
                subject=tval["subject"],
                body=tval["body"],
                variables=tval["variables"],
                version=tval.get("version", 1),
                is_active=True,
            ))
    return templates


@router.put("/templates/{template_id}")
async def update_template_endpoint(
    template_id: str,
    payload: EmailTemplateUpdateRequest,
    user: OfficerUser = Depends(require_admin),
):
    """Updates an email template (Administrator only)."""
    client = get_supabase_admin()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    update_data = {
        "id": template_id,
        "name": payload.name or template_id.title(),
        "subject": payload.subject,
        "body": payload.body,
        "is_active": payload.is_active,
        "updated_at": now,
        "updated_by": user.full_name,
    }
    res = client.table("email_templates").upsert(update_data).execute()
    log_action(
        actor_id=user.id,
        actor_name=user.full_name,
        action="update_template",
        target_type="email_template",
        target_id=template_id,
    )
    return {"success": True, "template": res.data[0] if res.data else update_data}


@router.get("/settings", response_model=SystemSettingsResponse)
async def get_settings_endpoint(user: OfficerUser = Depends(require_reviewer)):
    """Fetches system-wide operational settings."""
    return get_system_settings()


@router.put("/settings", response_model=SystemSettingsResponse)
async def update_settings_endpoint(
    payload: SystemSettingsUpdateRequest,
    user: OfficerUser = Depends(require_admin),
):
    """Updates system settings (Administrator only)."""
    updated = update_system_settings(
        registration_open=payload.registration_open,
        closed_message=payload.closed_message,
        qualification_rubric=payload.qualification_rubric,
        officer_name=user.full_name,
    )
    log_action(
        actor_id=user.id,
        actor_name=user.full_name,
        action="update_settings",
        target_type="system_settings",
        details={
            "registration_open": payload.registration_open,
            "rubric_updated": payload.qualification_rubric is not None,
        },
    )
    return updated


@router.get("/metrics")
async def get_metrics(user: OfficerUser = Depends(require_reviewer)):
    """Computes dashboard metrics: review turnaround time, decisions by reviewer, status totals."""
    client = get_supabase_admin()
    res = client.table("registrations").select("id, application_status, created_at, reviewed_at, reviewed_by, division_type, division_name").execute()
    rows = res.data or []

    total_submitted = len(rows)
    turnaround_minutes = []

    status_breakdown = {}
    division_breakdown = {}
    reviewer_activity = {}

    for r in rows:
        st = r.get("application_status", "new")
        status_breakdown[st] = status_breakdown.get(st, 0) + 1

        div = r.get("division_name") or "Unassigned"
        division_breakdown[div] = division_breakdown.get(div, 0) + 1

        rev_by = r.get("reviewed_by")
        if rev_by:
            reviewer_activity[rev_by] = reviewer_activity.get(rev_by, 0) + 1

        c_at = r.get("created_at")
        r_at = r.get("reviewed_at")
        if c_at and r_at:
            try:
                t1 = datetime.datetime.fromisoformat(c_at.replace("Z", "+00:00"))
                t2 = datetime.datetime.fromisoformat(r_at.replace("Z", "+00:00"))
                diff = (t2 - t1).total_seconds() / 60.0
                if diff >= 0:
                    turnaround_minutes.append(diff)
            except Exception:
                pass

    median_turnaround_hours = 0.0
    if turnaround_minutes:
        turnaround_minutes.sort()
        mid = len(turnaround_minutes) // 2
        median_min = turnaround_minutes[mid] if len(turnaround_minutes) % 2 != 0 else (turnaround_minutes[mid - 1] + turnaround_minutes[mid]) / 2.0
        median_turnaround_hours = round(median_min / 60.0, 1)

    return {
        "total_applications": total_submitted,
        "median_turnaround_hours": median_turnaround_hours,
        "status_breakdown": status_breakdown,
        "division_breakdown": division_breakdown,
        "reviewer_activity": reviewer_activity,
    }


@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    user: OfficerUser = Depends(require_reviewer),
):
    """Lists chronological audit log events."""
    client = get_supabase_admin()
    try:
        res = (
            client.table("audit_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        return []


@router.get("/export")
async def export_applications(
    status: Optional[str] = Query(None),
    user: OfficerUser = Depends(require_admin),
):
    """Exports application records to CSV format (Administrator only)."""
    client = get_supabase_admin()
    query = client.table("registrations").select(
        "id, full_name, student_id, email, year, program, dob, division_type, division_name, application_status, reviewed_by, reviewed_at, decision_reason_code, created_at"
    )
    if status and status != "all":
        query = query.eq("application_status", status)

    res = query.order("created_at", desc=True).execute()
    rows = res.data or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Full Name", "Student ID", "Email", "Year", "Program", "DOB",
        "Division Type", "Division Name", "Status", "Reviewed By", "Reviewed At",
        "Reason Code", "Submitted At"
    ])

    for r in rows:
        writer.writerow([
            r.get("id"),
            r.get("full_name"),
            r.get("student_id"),
            r.get("email"),
            r.get("year"),
            r.get("program"),
            r.get("dob"),
            r.get("division_type"),
            r.get("division_name"),
            r.get("application_status"),
            r.get("reviewed_by"),
            r.get("reviewed_at"),
            r.get("decision_reason_code"),
            r.get("created_at"),
        ])

    csv_data = output.getvalue()
    filename = f"aws_sbg_jru_applications_{datetime.date.today().isoformat()}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

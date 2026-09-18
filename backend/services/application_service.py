import secrets
import datetime
from typing import Dict, Any, List, Optional, Tuple
from fastapi import HTTPException, status

from backend.database import get_supabase_admin
from backend.services.audit_service import log_action
from backend.services.email_service import (
    preview_email,
    send_email,
    build_html_email,
    get_template,
)

CLAIM_LOCK_TIMEOUT_MINUTES = 30


def _parse_timestamp(ts: Any) -> Optional[datetime.datetime]:
    if not ts:
        return None
    if isinstance(ts, datetime.datetime):
        return ts
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def get_application_queue(
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    year: Optional[str] = None,
    program: Optional[str] = None,
    division_type: Optional[str] = None,
    reviewer_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """Retrieves paginated applications with search, multi-field filters, and status counters."""
    client = get_supabase_admin()

    # Query all applications for status breakdown
    # In Supabase, we can select application_status and count
    all_res = client.table("registrations").select("id, application_status").execute()
    all_rows = all_res.data or []

    status_counts = {
        "all": len(all_rows),
        "new": 0,
        "under_review": 0,
        "approved": 0,
        "revision_requested": 0,
        "resubmitted": 0,
        "declined": 0,
        "closed": 0,
    }
    for r in all_rows:
        s = r.get("application_status", "new")
        if s in status_counts:
            status_counts[s] += 1
        else:
            status_counts["new"] += 1

    # Filtered query
    query = client.table("registrations").select(
        "id, full_name, student_id, email, year, program, division_type, division_name, "
        "application_status, created_at, assigned_reviewer_id, assigned_reviewer_name, claimed_at",
        count="exact"
    )

    if status_filter and status_filter != "all":
        query = query.eq("application_status", status_filter)
    if year:
        query = query.eq("year", year)
    if program:
        query = query.eq("program", program)
    if division_type:
        query = query.eq("division_type", division_type)
    if reviewer_id:
        query = query.eq("assigned_reviewer_id", reviewer_id)

    if search:
        s_term = f"%{search.strip()}%"
        query = query.or_(
            f"full_name.ilike.{s_term},student_id.ilike.{s_term},email.ilike.{s_term}"
        )

    # Ordering & Pagination
    offset = (page - 1) * page_size
    query = query.order("created_at", desc=True).range(offset, offset + page_size - 1)

    result = query.execute()
    applications = result.data or []
    total = result.count if hasattr(result, "count") and result.count is not None else len(applications)

    # Check for expired claims and clear them display-wise
    now = datetime.datetime.now(datetime.timezone.utc)
    for app in applications:
        claimed_at = _parse_timestamp(app.get("claimed_at"))
        if claimed_at and (now - claimed_at).total_seconds() > (CLAIM_LOCK_TIMEOUT_MINUTES * 60):
            app["assigned_reviewer_id"] = None
            app["assigned_reviewer_name"] = None
            app["claimed_at"] = None

    return {
        "applications": applications,
        "total": total,
        "page": page,
        "page_size": page_size,
        "status_counts": status_counts,
    }


def get_application_detail(application_id: int) -> Dict[str, Any]:
    """Retrieves full application profile, reviews history, and email logs."""
    client = get_supabase_admin()

    res = client.table("registrations").select("*").eq("id", application_id).execute()
    if not res.data or len(res.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application #{application_id} not found",
        )
    app = res.data[0]

    # Check expired claim
    now = datetime.datetime.now(datetime.timezone.utc)
    claimed_at = _parse_timestamp(app.get("claimed_at"))
    if claimed_at and (now - claimed_at).total_seconds() > (CLAIM_LOCK_TIMEOUT_MINUTES * 60):
        app["assigned_reviewer_id"] = None
        app["assigned_reviewer_name"] = None
        app["claimed_at"] = None

    # Reviews
    rev_res = (
        client.table("application_reviews")
        .select("*")
        .eq("registration_id", application_id)
        .order("created_at", desc=True)
        .execute()
    )
    app["reviews"] = rev_res.data or []

    # Email logs
    email_res = (
        client.table("email_logs")
        .select("*")
        .eq("registration_id", application_id)
        .order("sent_at", desc=True)
        .execute()
    )
    app["email_logs"] = email_res.data or []

    return app


def claim_application(
    application_id: int,
    officer_id: str,
    officer_name: str,
) -> Dict[str, Any]:
    """Claims application for an officer. Enforces 30-min lock preventing duplicate reviews."""
    client = get_supabase_admin()
    app = get_application_detail(application_id)

    now = datetime.datetime.now(datetime.timezone.utc)
    current_claimed_at = _parse_timestamp(app.get("claimed_at"))
    current_reviewer_id = app.get("assigned_reviewer_id")

    # If claimed by another officer and still active (< 30 min)
    if (
        current_reviewer_id
        and current_reviewer_id != officer_id
        and current_claimed_at
        and (now - current_claimed_at).total_seconds() <= (CLAIM_LOCK_TIMEOUT_MINUTES * 60)
    ):
        claimed_by_name = app.get("assigned_reviewer_name") or "another officer"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application is already being reviewed by {claimed_by_name}.",
        )

    updates = {
        "assigned_reviewer_id": officer_id,
        "assigned_reviewer_name": officer_name,
        "claimed_at": now.isoformat(),
    }
    if app.get("application_status") == "new":
        updates["application_status"] = "under_review"

    res = client.table("registrations").update(updates).eq("id", application_id).execute()
    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="claim_application",
        target_type="registration",
        target_id=str(application_id),
        details={"status": updates.get("application_status", app.get("application_status"))},
    )
    return res.data[0] if res.data else updates


def release_application(
    application_id: int,
    officer_id: str,
    officer_name: str,
) -> Dict[str, Any]:
    """Releases claimed application back to queue."""
    client = get_supabase_admin()
    updates = {
        "assigned_reviewer_id": None,
        "assigned_reviewer_name": None,
        "claimed_at": None,
    }
    res = client.table("registrations").update(updates).eq("id", application_id).execute()
    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="release_application",
        target_type="registration",
        target_id=str(application_id),
    )
    return res.data[0] if res.data else updates


def add_internal_note(
    application_id: int,
    notes: str,
    officer_id: str,
    officer_name: str,
) -> Dict[str, Any]:
    """Adds internal reviewer note without modifying application status."""
    client = get_supabase_admin()
    app = get_application_detail(application_id)

    row = {
        "registration_id": application_id,
        "reviewer_id": officer_id,
        "reviewer_name": officer_name,
        "decision": "pending",
        "internal_notes": notes,
        "rubric_scores": {},
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    res = client.table("application_reviews").insert(row).execute()
    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="add_internal_note",
        target_type="registration",
        target_id=str(application_id),
        details={"notes_length": len(notes)},
    )
    return res.data[0] if res.data else row


def record_decision(
    application_id: int,
    decision: str,  # 'approved', 'declined', 'revision_requested', 'pending'
    officer_id: str,
    officer_name: str,
    reason_code: Optional[str] = None,
    internal_notes: Optional[str] = None,
    rubric_scores: Optional[Dict[str, bool]] = None,
    send_email_now: bool = True,
    next_steps: Optional[str] = None,
    revision_notes: Optional[str] = None,
    revision_deadline: Optional[str] = None,
    decline_reason: Optional[str] = None,
    custom_subject: Optional[str] = None,
    custom_body: Optional[str] = None,
    header_banner_url: Optional[str] = None,
    footer_banner_url: Optional[str] = None,
    general_chat_link: Optional[str] = None,
    general_qr_base64: Optional[str] = None,
    division_chat_link: Optional[str] = None,
    division_qr_base64: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Records a final or pending membership decision, updates application status,
    inserts audit and review history, and dispatches the corresponding templated email.
    """
    client = get_supabase_admin()
    app = get_application_detail(application_id)
    now = datetime.datetime.now(datetime.timezone.utc)

    reg_updates = {
        "reviewed_by": officer_name,
        "reviewed_at": now.isoformat(),
        "decision_reason_code": reason_code,
    }

    if decision != "pending":
        reg_updates["application_status"] = decision

    revision_token = None
    if decision == "revision_requested":
        revision_token = secrets.token_urlsafe(32)
        reg_updates["revision_token"] = revision_token
        reg_updates["revision_notes"] = revision_notes or "Please review and revise your answers."

        # Default deadline: 3 days from now
        if revision_deadline:
            reg_updates["revision_deadline"] = revision_deadline
        else:
            default_deadline = now + datetime.timedelta(days=3)
            reg_updates["revision_deadline"] = default_deadline.strftime("%Y-%m-%d %H:%M UTC")

    # Update registration record
    client.table("registrations").update(reg_updates).eq("id", application_id).execute()

    # Record review log
    review_row = {
        "registration_id": application_id,
        "reviewer_id": officer_id,
        "reviewer_name": officer_name,
        "decision": decision,
        "reason_code": reason_code,
        "internal_notes": internal_notes or "",
        "rubric_scores": rubric_scores or {},
        "created_at": now.isoformat(),
    }
    client.table("application_reviews").insert(review_row).execute()

    # Dispatch email if requested and decision maps to a template
    email_result = None
    if send_email_now and decision in ("approved", "declined", "revision_requested"):
        template_id = decision
        if custom_subject and custom_body:
            subj = custom_subject
            body = custom_body
        else:
            # Generate from template
            subj, body, _, _ = preview_email(
                applicant=app,
                template_id=template_id,
                next_steps=next_steps,
                revision_notes=revision_notes,
                revision_deadline=reg_updates.get("revision_deadline"),
                decline_reason=decline_reason or reason_code,
                revision_token=revision_token,
                header_banner_url=header_banner_url,
                footer_banner_url=footer_banner_url,
                general_chat_link=general_chat_link,
                general_qr_base64=general_qr_base64,
                division_chat_link=division_chat_link,
                division_qr_base64=division_qr_base64,
            )

        html_body = build_html_email(
            subject=subj,
            body_text=body,
            header_banner_url=header_banner_url,
            footer_banner_url=footer_banner_url,
            general_chat_link=general_chat_link,
            general_qr_base64=general_qr_base64,
            division_chat_link=division_chat_link,
            division_qr_base64=division_qr_base64,
            division_name=app.get("division_name"),
        )

        email_result = send_email(
            recipient_email=app["email"],
            subject=subj,
            body=body,
            html_body=html_body,
            registration_id=application_id,
            template_id=template_id,
            sender_id=officer_id,
        )

    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="record_decision",
        target_type="registration",
        target_id=str(application_id),
        details={
            "decision": decision,
            "reason_code": reason_code,
            "email_sent": send_email_now,
            "email_result": email_result,
        },
    )

    return {
        "success": True,
        "decision": decision,
        "application_id": application_id,
        "email_result": email_result,
    }


def get_system_settings() -> Dict[str, Any]:
    """Fetches system settings (registration_status, qualification_rubric)."""
    client = get_supabase_admin()
    settings = {
        "registration_open": True,
        "closed_message": "Membership registration is currently closed. Follow our official channels for the next recruitment cycle.",
        "qualification_rubric": [
            {"id": "jru_enrolled", "label": "Currently enrolled JRU student", "required": True},
            {"id": "complete_info", "label": "All required identity and contact fields complete and valid", "required": True},
            {"id": "genuine_interest", "label": "Explanation demonstrates genuine interest in cloud learning & community", "required": True},
            {"id": "code_of_conduct", "label": "Agrees to club code of conduct and student policies", "required": True},
            {"id": "quality_submission", "label": "Submitted information is authentic and non-abusive", "required": True},
        ],
    }

    try:
        res = client.table("system_settings").select("*").execute()
        for row in res.data or []:
            key = row.get("key")
            val = row.get("value")
            if key == "registration_status" and isinstance(val, dict):
                settings["registration_open"] = val.get("is_open", True)
                settings["closed_message"] = val.get("closed_message", settings["closed_message"])
            elif key == "qualification_rubric" and isinstance(val, list):
                settings["qualification_rubric"] = val
    except Exception as e:
        print(f"Notice: Using default system settings: {e}")

    return settings


def update_system_settings(
    registration_open: Optional[bool] = None,
    closed_message: Optional[str] = None,
    qualification_rubric: Optional[List[Dict[str, Any]]] = None,
    officer_name: str = "Officer",
) -> Dict[str, Any]:
    """Updates registration status or rubric settings."""
    client = get_supabase_admin()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if registration_open is not None or closed_message is not None:
        current = get_system_settings()
        reg_val = {
            "is_open": registration_open if registration_open is not None else current["registration_open"],
            "closed_message": closed_message if closed_message is not None else current["closed_message"],
        }
        client.table("system_settings").upsert({
            "key": "registration_status",
            "value": reg_val,
            "updated_at": now,
            "updated_by": officer_name,
        }).execute()

    if qualification_rubric is not None:
        client.table("system_settings").upsert({
            "key": "qualification_rubric",
            "value": qualification_rubric,
            "updated_at": now,
            "updated_by": officer_name,
        }).execute()

    return get_system_settings()

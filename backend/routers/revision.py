import datetime
from fastapi import APIRouter, HTTPException, status

from backend.database import get_supabase_admin
from backend.schemas.admin import (
    RevisionViewResponse,
    RevisionSubmitRequest,
)
from backend.services.application_service import get_system_settings
from backend.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/revision", tags=["revision"])


@router.get("/status/registration")
async def get_registration_status():
    """Public endpoint to check whether membership registration is active."""
    settings = get_system_settings()
    return {
        "is_open": settings.get("registration_open", True),
        "message": settings.get("closed_message", "Registration is currently closed."),
    }


@router.get("/{token}", response_model=RevisionViewResponse)
async def get_revision_data(token: str):
    """
    Validates a student's secure single-use revision link and returns
    the requested revision instructions and current answers.
    """
    if not token or len(token) < 16:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid revision token.",
        )

    client = get_supabase_admin()
    res = client.table("registrations").select("*").eq("revision_token", token).execute()

    if not res.data or len(res.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revision link not found or has already been used.",
        )

    app = res.data[0]
    if app.get("application_status") != "revision_requested":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This application has already been revised or decided upon.",
        )

    return RevisionViewResponse(
        full_name=app.get("full_name", ""),
        student_id=app.get("student_id", ""),
        email=app.get("email", ""),
        year=app.get("year", ""),
        program=app.get("program", ""),
        division_type=app.get("division_type", ""),
        division_name=app.get("division_name", ""),
        explanation=app.get("explanation", ""),
        revision_notes=app.get("revision_notes") or "Please revise your response as requested.",
        revision_deadline=app.get("revision_deadline"),
        photo_base64=app.get("photo_base64"),
    )


@router.post("/{token}")
async def submit_revision(token: str, payload: RevisionSubmitRequest):
    """
    Applies the applicant's updated fields, marks status as 'resubmitted',
    and invalidates the revision token to prevent duplicate edits.
    """
    if not token or len(token) < 16:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid revision token.",
        )

    client = get_supabase_admin()
    res = client.table("registrations").select("*").eq("revision_token", token).execute()

    if not res.data or len(res.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revision link not found or has already been used.",
        )

    app = res.data[0]
    app_id = app["id"]

    updates = {
        "application_status": "resubmitted",
        "revision_token": None,  # Invalidate single-use token
    }

    if payload.explanation is not None and payload.explanation.strip():
        updates["explanation"] = payload.explanation.strip()
    if payload.photo_base64 is not None and payload.photo_base64.strip():
        updates["photo_base64"] = payload.photo_base64.strip()
    if payload.division_type is not None:
        updates["division_type"] = payload.division_type
    if payload.division_name is not None:
        updates["division_name"] = payload.division_name

    client.table("registrations").update(updates).eq("id", app_id).execute()

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    client.table("application_reviews").insert({
        "registration_id": app_id,
        "reviewer_id": "applicant",
        "reviewer_name": app.get("full_name") or "Applicant",
        "decision": "pending",
        "internal_notes": "Applicant submitted requested revisions.",
        "rubric_scores": {},
        "created_at": now,
    }).execute()

    log_action(
        actor_id=str(app_id),
        actor_name=app.get("full_name") or "Applicant",
        action="submit_revision",
        target_type="registration",
        target_id=str(app_id),
    )

    return {
        "success": True,
        "message": "Your revision has been successfully submitted! Our team will review your updated response.",
    }

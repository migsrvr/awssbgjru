import smtplib
import base64
import re
from email.message import EmailMessage
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.database import get_supabase_admin
from backend.schemas.registration import RegistrationRequest
from backend.api.config import (
    EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS, NOTIFY_EMAIL, VALID_DIVISIONS,
)
from backend.api.rate_limiter import RateLimiter
from backend.registration_availability import (
    DivisionAvailabilityError,
    validate_division_availability,
    validate_division_eligibility,
)
from backend.services.application_service import get_system_settings

router = APIRouter(prefix="/api", tags=["registration"])
register_limiter = RateLimiter(requests=5, window=60)


@router.post("/register")
async def register(request: Request, data: RegistrationRequest):
    client_ip = request.client.host if request.client else "unknown"
    if not register_limiter.is_allowed(client_ip):
        return JSONResponse(
            {"error": "Rate limit exceeded. Please wait before submitting again."},
            status_code=429,
        )

    # Check master registration status
    settings = get_system_settings()
    if not settings.get("registration_open", True):
        return JSONResponse(
            {"error": settings.get("closed_message", "Registration is currently closed.")},
            status_code=403,
        )

    if data.website:
        return JSONResponse({"error": "Bot detected"}, status_code=422)

    try:
        validate_division_availability(data.division_type, data.division_name)
    except DivisionAvailabilityError as exc:
        return JSONResponse(
            {"error": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )

    print(f"Registration data received: full_name={data.full_name}, student_id={data.student_id}, year={data.year}, program={data.program}, dob={data.dob}, division_type={data.division_type}")

    if not re.match(r"^\d{2}-\d{6}$", data.student_id):
        return JSONResponse({"error": "Invalid student ID format (expecting ##-######)"}, status_code=422)

    valid_years = {"First Year", "Second Year", "Third Year", "Fourth Year"}
    if data.year not in valid_years:
        return JSONResponse({"error": "Invalid school year selection"}, status_code=422)

    try:
        validate_division_eligibility(data.division_type, data.division_name, data.year)
    except DivisionAvailabilityError as exc:
        return JSONResponse(
            {"error": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )

    valid_programs = {
        "BS Computer Engineering", "BS Electronics Engineering",
        "BS Information Technology", "BSIT Business Analytics",
        "BS Entertainment and Multimedia Computing", "BSBA",
        "BS Digital Animation Technology", "BS Game Development"
    }
    if data.program not in valid_programs:
        return JSONResponse({"error": "Invalid program selection"}, status_code=422)

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", data.dob):
        return JSONResponse({"error": "Invalid date of birth format (expecting YYYY-MM-DD)"}, status_code=422)

    if data.photo_base64:
        base64_data = data.photo_base64.split(",")[-1] if "," in data.photo_base64 else data.photo_base64
        try:
            decoded_len = len(base64.b64decode(base64_data))
            if decoded_len > 512000:
                return JSONResponse({"error": "Photo exceeds maximum size of 500KB"}, status_code=422)
        except Exception:
            return JSONResponse({"error": "Invalid photo data"}, status_code=422)

    if data.division_name not in VALID_DIVISIONS.get(data.division_type, set()):
        return JSONResponse({"error": "Invalid division selection"}, status_code=422)

    row = {
        "full_name": data.full_name,
        "student_id": data.student_id,
        "email": data.email,
        "year": data.year,
        "program": data.program,
        "dob": data.dob,
        "photo_base64": data.photo_base64,
        "explanation": data.explanation,
        "division_type": data.division_type,
        "division_name": data.division_name,
        "application_status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    client = get_supabase_admin()
    result = client.table("registrations").insert(row).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to insert registration")

    inserted_id = result.data[0]["id"]

    try:
        _send_notification(data)
    except Exception as e:
        print(f"Email notification failed: {e}")

    return JSONResponse({"success": True, "id": inserted_id}, status_code=201)


def _send_notification(data: RegistrationRequest):
    if not EMAIL_USER or not EMAIL_PASS or not NOTIFY_EMAIL:
        return

    msg = EmailMessage()
    msg["Subject"] = f"New Registration — {data.full_name}"
    msg["From"] = EMAIL_USER
    msg["To"] = NOTIFY_EMAIL

    body = f"""
New member registration:

  Name:            {data.full_name}
  Student ID:      {data.student_id}
  Email:           {data.email}
  Year:            {data.year}
  Program:         {data.program}
  DOB:             {data.dob}
  Division Type:   {data.division_type}
  Division Name:   {data.division_name}

Explanation:
{data.explanation}
"""
    msg.set_content(body.strip())

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.send_message(msg)

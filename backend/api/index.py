import sys
import json
import os
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

_api_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.join(_api_dir, "..", "..")

sys.path.insert(0, _api_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.registration_availability import (
    DivisionAvailabilityError,
    validate_division_availability,
)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from backend.routers.admin import router as admin_router
from backend.routers.revision import router as revision_router
from backend.services.application_service import get_system_settings

import chatbot
import config
import rate_limiter
import cache

app = FastAPI(title="Cumulus Helm Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://awslearningclub.jru", "http://localhost:8000", "http://localhost:8080", "http://localhost:8081"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(revision_router)


limiter = rate_limiter.RateLimiter()
register_limiter = rate_limiter.RateLimiter(requests=5, window=60)
response_cache = cache.TTLCache()


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()

    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"

    if not limiter.is_allowed(client_ip):
        return JSONResponse(
            {"error": "Rate limit exceeded. Please wait before sending another message."},
            status_code=429,
        )

    cache_key = message.lower().strip()
    cached = response_cache.get(cache_key)
    if cached is not None:

        async def cached_stream():
            yield f"data: {json.dumps({'token': cached})}\n\n"
            yield f"data: {json.dumps({'token': '[DONE]'})}\n\n"

        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    async def stream():
        full_response = ""
        for chunk in chatbot.generate(message):
            if "error" in chunk:
                yield f"data: {json.dumps(chunk)}\n\n"
                return
            token = chunk.get("token", "")
            if token == "[DONE]":
                response_cache.set(cache_key, full_response)
                yield f"data: {json.dumps(chunk)}\n\n"
                return
            full_response += token
            yield f"data: {json.dumps({'token': token})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": config.GROQ_MODEL}


def _get_supabase():
    if not hasattr(_get_supabase, "_client"):
        from supabase import create_client
        _get_supabase._client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _get_supabase._client


@app.post("/api/register")
async def register(request: Request):
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

    website = data.get("website", "")
    if website:
        return JSONResponse({"error": "Bot detected"}, status_code=422)

    full_name = data.get("full_name", "").strip()
    if not full_name or len(full_name) < 2 or len(full_name) > 100:
        return JSONResponse({"error": "Full name must be between 2 and 100 characters"}, status_code=422)

    student_id = data.get("student_id", "").strip()
    if not student_id or not re.match(r"^\d{2}-\d{6}$", student_id):
        return JSONResponse({"error": "Invalid student ID format (expecting ##-######)"}, status_code=422)

    email = data.get("email", "")
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return JSONResponse({"error": "Invalid email address"}, status_code=422)

    valid_years = {"First Year", "Second Year", "Third Year", "Fourth Year"}
    year = data.get("year", "")
    if year not in valid_years:
        return JSONResponse({"error": "Invalid school year selection"}, status_code=422)

    valid_programs = {
        "BS Computer Engineering", "BS Electronics Engineering",
        "BS Information Technology", "BSIT Business Analytics",
        "BS Entertainment and Multimedia Computing", "BSBA",
        "BS Digital Animation Technology", "BS Game Development"
    }
    program = data.get("program", "")
    if program not in valid_programs:
        return JSONResponse({"error": "Invalid program selection"}, status_code=422)

    dob = data.get("dob", "").strip()
    if not dob or not re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
        return JSONResponse({"error": "Invalid date of birth format (expecting YYYY-MM-DD)"}, status_code=422)

    division_type = data.get("division_type", "")
    division_name = data.get("division_name", "")
    try:
        validate_division_availability(division_type, division_name)
    except DivisionAvailabilityError as exc:
        return JSONResponse(
            {"error": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )

    photo_base64 = data.get("photo_base64", "")
    if photo_base64 and not photo_base64.startswith("data:image/"):
        return JSONResponse({"error": "photo_base64 must be a valid data URL"}, status_code=422)
    if photo_base64:
        base64_data = photo_base64.split(",")[-1] if "," in photo_base64 else photo_base64
        import base64
        try:
            decoded_len = len(base64.b64decode(base64_data))
            if decoded_len > 512000:
                return JSONResponse({"error": "Photo exceeds maximum size of 500KB"}, status_code=422)
        except Exception:
            return JSONResponse({"error": "Invalid photo data"}, status_code=422)

    row = {
        "full_name": full_name,
        "student_id": student_id,
        "email": email,
        "year": year,
        "program": program,
        "dob": dob,
        "photo_base64": photo_base64,
        "explanation": data.get("explanation", ""),
        "division_type": division_type,
        "division_name": division_name,
        "application_status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        sb = _get_supabase()
        result = sb.table("registrations").insert(row).execute()
    except Exception as e:
        return JSONResponse({"error": f"Database error: {str(e)}"}, status_code=500)

    if not result.data:
        return JSONResponse({"error": "Failed to insert registration"}, status_code=500)

    inserted_id = result.data[0]["id"]

    try:
        _send_notification(data)
    except Exception as e:
        print(f"Email notification failed: {e}")

    return JSONResponse({"success": True, "id": inserted_id}, status_code=201)


def _send_notification(data: dict):
    if not config.EMAIL_USER or not config.EMAIL_PASS or not config.NOTIFY_EMAIL:
        return

    msg = EmailMessage()
    msg["Subject"] = f"New Registration — {data.get('full_name', '')}"
    msg["From"] = config.EMAIL_USER
    msg["To"] = config.NOTIFY_EMAIL

    body = f"""
New member registration:

  Name:            {data.get('full_name', '')}
  Student ID:      {data.get('student_id', '')}
  Email:           {data.get('email', '')}
  Year:            {data.get('year', '')}
  Program:         {data.get('program', '')}
  DOB:             {data.get('dob', '')}
  Division Type:   {data.get('division_type', '')}
  Division Name:   {data.get('division_name', '')}

Explanation:
{data.get('explanation', '')}
"""
    msg.set_content(body.strip())

    with smtplib.SMTP(config.EMAIL_HOST, config.EMAIL_PORT) as smtp:
        smtp.starttls()
        smtp.login(config.EMAIL_USER, config.EMAIL_PASS)
        smtp.send_message(msg)


@app.get("/api/_debug")
async def debug():
    info = {
        "python": sys.version,
        "has_supabase_url": bool(config.SUPABASE_URL),
        "has_supabase_key": bool(config.SUPABASE_KEY),
        "has_groq_key": bool(config.GROQ_API_KEY),
        "has_email_user": bool(config.EMAIL_USER),
        "has_email_pass": bool(config.EMAIL_PASS),
        "has_notify_email": bool(config.NOTIFY_EMAIL),
    }
    try:
        sb = _get_supabase()
        r = sb.table("registrations").select("id").limit(1).execute()
        info["supabase_ok"] = True
    except Exception as e:
        info["supabase_ok"] = False
        info["supabase_error"] = str(e)
    return info


frontend_path = os.path.join(_project_root, "frontend")
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

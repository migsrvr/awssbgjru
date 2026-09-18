import re
import smtplib
import datetime
from email.message import EmailMessage
from typing import Dict, Any, Optional, Tuple

from backend.api.config import (
    EMAIL_HOST,
    EMAIL_PORT,
    EMAIL_USER,
    EMAIL_PASS,
    APP_BASE_URL,
)
from backend.database import get_supabase_admin

DEFAULT_TEMPLATES = {
    "application_received": {
        "name": "Application Received",
        "subject": "We received your AWS SBG JRU application",
        "body": (
            "Hi {{Applicant Name}},\n\n"
            "Thank you for applying to join AWS SBG JRU. We have received your application and "
            "our team will review your responses. We will contact you through this email once there is an update.\n\n"
            "Regards,\nAWS SBG JRU Team"
        ),
        "variables": ["Applicant Name"],
        "version": 1,
    },
    "approved": {
        "name": "Welcome / Approved",
        "subject": "Welcome to AWS SBG JRU",
        "body": (
            "Hi {{Applicant Name}},\n\n"
            "Congratulations! Your application to join AWS SBG JRU has been approved.\n\n"
            "{{Next Steps}}\n\n"
            "We look forward to learning and building with you.\n\n"
            "Regards,\nAWS SBG JRU Team"
        ),
        "variables": ["Applicant Name", "Next Steps"],
        "version": 1,
    },
    "revision_requested": {
        "name": "Revision Requested",
        "subject": "Please revise your AWS SBG JRU application",
        "body": (
            "Hi {{Applicant Name}},\n\n"
            "Thank you for your interest in AWS SBG JRU. Before we can complete our review, "
            "please revise the following part of your application:\n\n"
            "{{Revision Notes}}\n\n"
            "You may update your response using this secure link:\n{{Revision Link}}\n\n"
            "Please submit your revision by {{Revision Deadline}}.\n\n"
            "Regards,\nAWS SBG JRU Team"
        ),
        "variables": ["Applicant Name", "Revision Notes", "Revision Link", "Revision Deadline"],
        "version": 1,
    },
    "declined": {
        "name": "Application Update / Declined",
        "subject": "Update on your AWS SBG JRU application",
        "body": (
            "Hi {{Applicant Name}},\n\n"
            "Thank you for taking the time to apply to AWS SBG JRU. After reviewing your application, "
            "we are unable to approve it at this time.\n\n"
            "{{Optional General Reason}}\n\n"
            "We appreciate your interest and encourage you to participate in future public AWS SBG JRU activities "
            "or apply again during a future recruitment period if eligible.\n\n"
            "Regards,\nAWS SBG JRU Team"
        ),
        "variables": ["Applicant Name", "Optional General Reason"],
        "version": 1,
    },
    "registration_closed": {
        "name": "Registration Closed",
        "subject": "AWS SBG JRU registration is currently closed",
        "body": (
            "Hi {{Applicant Name}},\n\n"
            "Thank you for your interest in AWS SBG JRU. Membership registration is currently closed, "
            "so we are unable to process a new application at this time.\n\n"
            "Please follow our official channels for announcements about the next recruitment period.\n\n"
            "Regards,\nAWS SBG JRU Team"
        ),
        "variables": ["Applicant Name"],
        "version": 1,
    },
}


def get_template(template_id: str) -> Dict[str, Any]:
    """Fetches template from DB or fallback default."""
    try:
        client = get_supabase_admin()
        res = client.table("email_templates").select("*").eq("id", template_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception as e:
        print(f"Notice: Using default email template fallback for '{template_id}': {e}")

    default = DEFAULT_TEMPLATES.get(template_id)
    if default:
        return {
            "id": template_id,
            "name": default["name"],
            "subject": default["subject"],
            "body": default["body"],
            "variables": default["variables"],
            "version": default.get("version", 1),
            "is_active": True,
        }
    raise ValueError(f"Template with id '{template_id}' not found.")


def interpolate_template(
    template: Dict[str, Any],
    variables: Dict[str, str],
) -> Tuple[str, str]:
    """
    Substitutes {{Placeholder}} tags in subject and body.
    Removes unused optional placeholder lines if empty.
    """
    subject = template.get("subject", "")
    body = template.get("body", "")

    for key, val in variables.items():
        clean_val = val if val is not None else ""
        pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", re.IGNORECASE)
        subject = pattern.sub(clean_val, subject)
        body = pattern.sub(clean_val, body)

    # Clean up empty optional placeholder lines
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    subject = subject.strip()

    return subject, body


def build_variables_map(
    applicant: Dict[str, Any],
    next_steps: Optional[str] = None,
    revision_notes: Optional[str] = None,
    revision_deadline: Optional[str] = None,
    decline_reason: Optional[str] = None,
    revision_token: Optional[str] = None,
) -> Dict[str, str]:
    """Prepares variable dictionary for email templates."""
    base_url = APP_BASE_URL.rstrip("/")
    rev_token = revision_token or applicant.get("revision_token") or ""
    revision_link = f"{base_url}/revision?token={rev_token}" if rev_token else f"{base_url}/revision"

    default_next_steps = (
        "Please watch for an invitation to our official Discord server and orientation session. "
        "We will reach out with the schedule and welcome pack soon."
    )

    return {
        "Applicant Name": applicant.get("full_name") or "Applicant",
        "Next Steps": next_steps or default_next_steps,
        "Revision Notes": revision_notes or applicant.get("revision_notes") or "Please update your submission.",
        "Revision Link": revision_link,
        "Revision Deadline": revision_deadline or applicant.get("revision_deadline") or "within 3 days",
        "Optional General Reason": decline_reason or applicant.get("decision_reason_code") or "",
    }


def preview_email(
    applicant: Dict[str, Any],
    template_id: str,
    next_steps: Optional[str] = None,
    revision_notes: Optional[str] = None,
    revision_deadline: Optional[str] = None,
    decline_reason: Optional[str] = None,
    revision_token: Optional[str] = None,
) -> Tuple[str, str, Dict[str, str]]:
    """Generates preview of subject and body."""
    tmpl = get_template(template_id)
    vars_map = build_variables_map(
        applicant,
        next_steps=next_steps,
        revision_notes=revision_notes,
        revision_deadline=revision_deadline,
        decline_reason=decline_reason,
        revision_token=revision_token,
    )
    subject, body = interpolate_template(tmpl, vars_map)
    return subject, body, vars_map


def send_email(
    recipient_email: str,
    subject: str,
    body: str,
    registration_id: Optional[int] = None,
    template_id: Optional[str] = None,
    template_version: int = 1,
    sender_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends email via SMTP. Falls back to dry_run logging if SMTP credentials are missing.
    Records delivery status in `email_logs` table.
    """
    delivery_status = "sent"
    error_message = None

    # Check if SMTP credentials exist
    if not EMAIL_USER or not EMAIL_PASS:
        delivery_status = "dry_run"
        print(f"[EMAIL DRY RUN] To: {recipient_email}\nSubject: {subject}\n\n{body}\n")
    else:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = EMAIL_USER
            msg["To"] = recipient_email
            msg.set_content(body)

            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
            print(f"[EMAIL SENT] Successfully sent email to {recipient_email}")
        except Exception as e:
            delivery_status = "failed"
            error_message = str(e)
            print(f"[EMAIL FAILED] Failed sending to {recipient_email}: {e}")

    # Persist log in Supabase email_logs
    try:
        client = get_supabase_admin()
        client.table("email_logs").insert({
            "registration_id": registration_id,
            "template_id": template_id,
            "template_version": template_version,
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "sender_id": sender_id,
            "delivery_status": delivery_status,
            "error_message": error_message,
            "sent_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print(f"Warning: Failed to persist email log to Supabase: {e}")

    return {
        "success": delivery_status in ("sent", "dry_run"),
        "delivery_status": delivery_status,
        "error": error_message,
    }

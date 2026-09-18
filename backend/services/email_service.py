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
        "subject": "Welcome to AWS Student Builder Group - JRU",
        "body": (
            "*Dear {{Applicant First Name}},*\n\n"
            "Congratulations!\n\n"
            "We are pleased to inform you that you have been accepted as a *{{Role Title}}* under the *{{Division Name}}* of the *AWS Student Builder Group – JRU Chapter*.\n\n"
            "Please join the group chats below to stay updated and coordinate with the organization:\n\n"
            "Our organization is dedicated to helping students develop their knowledge and practical skills in cloud computing through Amazon Web Services (AWS), technical workshops, collaborative projects, certification preparation, and community-driven activities.\n\n"
            "As a member, you will have opportunities to learn, collaborate with fellow students, participate in organizational initiatives, and contribute to the growth of the cloud computing community at Jose Rizal University.\n\n"
            "We look forward to welcoming you to the *AWS Student Builder Group – JRU Chapter*."
        ),
        "variables": ["Applicant Name", "Applicant First Name", "Role Title", "Division Name"],
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

    full_name = applicant.get("full_name") or "Applicant"
    parts = full_name.strip().split()
    first_name = parts[0] if parts else "Applicant"

    div_name = applicant.get("division_name") or "AWS SBG JRU"
    role_title = f"{div_name} Member" if not div_name.lower().endswith("member") else div_name

    return {
        "Applicant Name": full_name,
        "Applicant First Name": first_name,
        "Role Title": role_title,
        "Division Name": div_name,
        "Next Steps": next_steps or default_next_steps,
        "Revision Notes": revision_notes or applicant.get("revision_notes") or "Please update your submission.",
        "Revision Link": revision_link,
        "Revision Deadline": revision_deadline or applicant.get("revision_deadline") or "within 3 days",
        "Optional General Reason": decline_reason or applicant.get("decision_reason_code") or "",
    }


def resolve_image_url(url_or_path: Optional[str]) -> Optional[str]:
    """Resolves relative asset paths to absolute URLs using APP_BASE_URL if needed."""
    if not url_or_path:
        return None
    url_or_path = url_or_path.strip()
    if url_or_path.startswith("data:") or url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        return url_or_path
    base_url = APP_BASE_URL.rstrip("/")
    clean_path = url_or_path.lstrip("/")
    import urllib.parse
    clean_path = urllib.parse.quote(clean_path, safe="/:")
    return f"{base_url}/{clean_path}"


def _format_inline_markdown(text: str) -> str:
    """
    Converts *text* into the official AWS SBG JRU navy bold-italic styling:
    <span style="color: #0c356a; font-weight: bold; font-style: italic;">text</span>
    """
    return re.sub(
        r"\*([^*]+)\*",
        r'<span style="color: #0c356a; font-weight: bold; font-style: italic;">\1</span>',
        text,
    )


def build_html_email(
    subject: str,
    body_text: str,
    header_banner_url: Optional[str] = None,
    footer_banner_url: Optional[str] = None,
    general_chat_link: Optional[str] = None,
    general_qr_base64: Optional[str] = None,
    division_chat_link: Optional[str] = None,
    division_qr_base64: Optional[str] = None,
    division_name: Optional[str] = None,
    division_chat_label: Optional[str] = None,
) -> str:
    """
    Constructs a responsive, table-based HTML email compatible with Gmail, Apple Mail, and Outlook.
    Incorporates header banner, formatted paragraphs, group chat links with QR codes, and footer banner.
    Accurately mimics Arial styling with official deep-navy bold italic highlights (#0c356a).
    """
    resolved_header = resolve_image_url(header_banner_url or "/assets/email-banners/AWS-Banner.png")
    resolved_footer = resolve_image_url(footer_banner_url)

    group_chats_html = ""
    if general_chat_link or division_chat_link or general_qr_base64 or division_qr_base64:
        gc_items = []
        if general_chat_link or general_qr_base64:
            item = '<div style="margin: 16px 0 20px 0;">'
            if general_chat_link:
                item += (
                    f'<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; color: #222222; line-height: 1.55;">'
                    f'<span style="color: #0c356a; font-weight: bold; font-style: italic;">General Group Chat:</span> '
                    f'<a href="{general_chat_link}" style="color: #0066cc; text-decoration: underline;" target="_blank">{general_chat_link}</a>'
                    f'</p>'
                )
            else:
                item += '<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; line-height: 1.55;"><span style="color: #0c356a; font-weight: bold; font-style: italic;">General Group Chat:</span></p>'
            if general_qr_base64:
                item += f'<img src="{general_qr_base64}" alt="General Group Chat QR Code" width="170" style="width: 170px; max-width: 100%; height: auto; object-fit: contain; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: #ffffff; display: block; margin-top: 8px; margin-bottom: 8px;" />'
            item += '</div>'
            gc_items.append(item)

        if division_chat_label and division_chat_label.strip():
            div_label = division_chat_label.strip().rstrip(":")
        else:
            raw_div = division_name or "Division"
            div_clean = raw_div.replace(" Office", "").replace(" Department", "")
            if any(w in raw_div.lower() for w in ["data", "tech", "cloud", "developer", "software"]):
                div_label = "Technology Group Chat"
            else:
                div_label = f"{div_clean} Group Chat"

        if division_chat_link or division_qr_base64:
            item = '<div style="margin: 16px 0 20px 0;">'
            if division_chat_link:
                item += (
                    f'<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; color: #222222; line-height: 1.55;">'
                    f'<span style="color: #0c356a; font-weight: bold; font-style: italic;">{div_label}:</span> '
                    f'<a href="{division_chat_link}" style="color: #0066cc; text-decoration: underline;" target="_blank">{division_chat_link}</a>'
                    f'</p>'
                )
            else:
                item += f'<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; line-height: 1.55;"><span style="color: #0c356a; font-weight: bold; font-style: italic;">{div_label}:</span></p>'
            if division_qr_base64:
                item += f'<img src="{division_qr_base64}" alt="{div_label} QR Code" width="170" style="width: 170px; max-width: 100%; height: auto; object-fit: contain; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: #ffffff; display: block; margin-top: 8px; margin-bottom: 8px;" />'
            item += '</div>'
            gc_items.append(item)

        group_chats_html = "".join(gc_items)

    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    content_blocks = []
    chats_inserted = False

    for p in paragraphs:
        p_formatted = _format_inline_markdown(p)
        p_html = p_formatted.replace("\n", "<br />")
        content_blocks.append(
            f'<p style="margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; color: #222222; line-height: 1.55;">{p_html}</p>'
        )

        if "group chats below" in p.lower() and group_chats_html and not chats_inserted:
            content_blocks.append(group_chats_html)
            chats_inserted = True

    if group_chats_html and not chats_inserted:
        content_blocks.append(group_chats_html)

    body_html_content = "\n".join(content_blocks)

    header_img_html = ""
    if resolved_header:
        header_img_html = f'''
        <tr>
          <td align="center" style="padding: 0;">
            <img src="{resolved_header}" alt="AWS Student Builder Group JRU Chapter" width="600" style="width: 100%; max-width: 600px; height: auto; display: block; border-top-left-radius: 8px; border-top-right-radius: 8px;" />
          </td>
        </tr>
        '''

    footer_img_html = ""
    if resolved_footer:
        footer_img_html = f'''
        <tr>
          <td align="center" style="padding: 0;">
            <img src="{resolved_footer}" alt="Officer Sign-off" width="600" style="width: 100%; max-width: 600px; height: auto; display: block; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;" />
          </td>
        </tr>
        '''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 20px 0; background-color: #f7fafc; font-family: Arial, Helvetica, sans-serif; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f7fafc;">
    <tr>
      <td align="center" style="padding: 10px;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
          {header_img_html}
          <tr>
            <td style="padding: 28px 30px 24px 30px; color: #222222; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; line-height: 1.55;">
              {body_html_content}
            </td>
          </tr>
          {footer_img_html}
        </table>
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; width: 100%; margin-top: 16px;">
          <tr>
            <td align="center" style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #a0aec0; padding: 10px 20px; line-height: 1.4;">
              AWS Student Builder Group &bull; Jose Rizal University Chapter<br>
              <span style="font-size: 11px;">This is an official administrative communication from AWS SBG JRU.</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def preview_email(
    applicant: Dict[str, Any],
    template_id: str,
    next_steps: Optional[str] = None,
    revision_notes: Optional[str] = None,
    revision_deadline: Optional[str] = None,
    decline_reason: Optional[str] = None,
    revision_token: Optional[str] = None,
    header_banner_url: Optional[str] = None,
    footer_banner_url: Optional[str] = None,
    general_chat_link: Optional[str] = None,
    general_qr_base64: Optional[str] = None,
    division_chat_link: Optional[str] = None,
    division_qr_base64: Optional[str] = None,
    division_chat_label: Optional[str] = None,
) -> Tuple[str, str, Dict[str, str], str]:
    """Generates preview of subject, body, variables, and full HTML rendering."""
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

    # Build HTML preview
    html_preview = build_html_email(
        subject=subject,
        body_text=body,
        header_banner_url=header_banner_url,
        footer_banner_url=footer_banner_url,
        general_chat_link=general_chat_link,
        general_qr_base64=general_qr_base64,
        division_chat_link=division_chat_link,
        division_qr_base64=division_qr_base64,
        division_name=applicant.get("division_name"),
        division_chat_label=division_chat_label,
    )

    return subject, body, vars_map, html_preview


def send_email(
    recipient_email: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    registration_id: Optional[int] = None,
    template_id: Optional[str] = None,
    template_version: int = 1,
    sender_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends email via SMTP using MIME multipart (plain-text + HTML).
    Falls back to dry_run logging if SMTP credentials are missing.
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
            msg["From"] = f"AWS Student Builder Group JRU Chapter <{EMAIL_USER}>"
            msg["To"] = recipient_email
            msg.set_content(body)  # Plain-text alternative

            if html_body:
                msg.add_alternative(html_body, subtype="html")

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

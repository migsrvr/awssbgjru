import datetime
import re
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, cast
from fastapi import HTTPException

from backend.database import get_supabase_admin
from backend.schemas.portal_members import (
    ApiKeyCreatedResponse,
    ApiKeyItem,
    BulkGenerationResponse,
    BulkRowError,
    CsvMemberInput,
    ExternalMemberProfile,
    ExternalValidateResponse,
    GeneratedMemberSummary,
    OrgMemberItem,
    OrgMemberListResponse,
    PasswordResetResponse,
    UnprovisionedApplicantItem,
    ValidationLogItem,
)
from backend.services.audit_service import log_action
from backend.services.credential_service import (
    generate_api_key,
    generate_default_password,
    generate_org_id,
    generate_randomized_username,
    hash_api_key,
    hash_password,
    split_full_name,
    verify_password,
)
from backend.services.email_service import get_template, interpolate_template, send_email

_EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _as_rows(data: Any) -> List[Dict[str, Any]]:
    """Narrows Supabase `execute().data` JSON union list to typed dict rows for Pyright."""
    if not data or not isinstance(data, list):
        return []
    return cast(List[Dict[str, Any]], data)


def _parse_accepted_date(raw_str: Optional[str]) -> datetime.date:
    manila_tz = datetime.timezone(datetime.timedelta(hours=8))
    if raw_str:
        clean = raw_str.strip()
        try:
            if "T" in clean:
                dt = datetime.datetime.fromisoformat(clean.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(manila_tz)
                return dt.date()
            return datetime.date.fromisoformat(clean[:10])
        except Exception:
            pass
    # Fallback to current date in UTC+8 (Asia/Manila)
    return datetime.datetime.now(manila_tz).date()


def _load_existing_identifiers(client) -> Tuple[Set[str], Set[str], Set[int]]:
    """Loads existing org_ids, usernames, and provisioned registration_ids from org_members."""
    res = client.table("org_members").select("org_id, username, registration_id").execute()
    rows = _as_rows(res.data)
    org_ids = {str(r["org_id"]) for r in rows if r.get("org_id")}
    usernames = {str(r["username"]).lower() for r in rows if r.get("username")}
    reg_ids = {int(r["registration_id"]) for r in rows if r.get("registration_id") is not None}
    return org_ids, usernames, reg_ids


def _dispatch_credential_email(
    recipient_email: str,
    full_name: str,
    org_id: str,
    username: str,
    plaintext_password: str,
    sender_id: str,
    registration_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Sends the member's credentials via SMTP and logs a REDACTED body (`[REDACTED]`)
    to `email_logs` so plaintext passwords never persist in database logs.
    """
    template = get_template("portal_credentials")
    base_vars = {
        "Applicant Name": full_name,
        "Org ID": org_id,
        "Username": username,
    }

    real_subject, real_body = interpolate_template(
        template,
        {**base_vars, "Default Password": plaintext_password},
    )
    _, redacted_body = interpolate_template(
        template,
        {**base_vars, "Default Password": "[REDACTED]"},
    )

    return send_email(
        recipient_email=recipient_email,
        subject=real_subject,
        body=real_body,
        registration_id=registration_id,
        template_id="portal_credentials",
        template_version=template.get("version", 1),
        sender_id=sender_id,
        log_body=redacted_body,
    )


def list_unprovisioned_approved() -> List[UnprovisionedApplicantItem]:
    """Returns approved applications in `registrations` that do not yet have an `org_members` record."""
    client = get_supabase_admin()
    _, _, provisioned_reg_ids = _load_existing_identifiers(client)

    res = (
        client.table("registrations")
        .select(
            "id, full_name, student_id, email, year, program, division_type, division_name, reviewed_at, created_at"
        )
        .eq("application_status", "approved")
        .order("reviewed_at", desc=True)
        .execute()
    )
    rows = _as_rows(res.data)
    items: List[UnprovisionedApplicantItem] = []
    for r in rows:
        reg_id = int(r["id"])
        if reg_id in provisioned_reg_ids:
            continue
        items.append(
            UnprovisionedApplicantItem(
                registration_id=reg_id,
                full_name=r.get("full_name") or "",
                student_id=r.get("student_id"),
                email=r.get("email") or "",
                year=r.get("year"),
                program=r.get("program"),
                division_type=r.get("division_type"),
                division_name=r.get("division_name"),
                reviewed_at=r.get("reviewed_at"),
                created_at=r.get("created_at"),
            )
        )
    return items


def bulk_generate_from_approved(
    registration_ids: List[int],
    officer_id: str,
    officer_name: str,
) -> BulkGenerationResponse:
    """
    Generates Org IDs, randomized usernames, and hashed default passwords for selected
    approved registrations, emailing each student individually with zero plaintext exposure.
    """
    client = get_supabase_admin()
    existing_org_ids, existing_usernames, provisioned_reg_ids = _load_existing_identifiers(client)

    res = (
        client.table("registrations")
        .select("*")
        .in_("id", registration_ids)
        .execute()
    )
    reg_map = {int(r["id"]): r for r in _as_rows(res.data)}

    generated: List[GeneratedMemberSummary] = []
    errors: List[BulkRowError] = []
    emailed_count = 0
    failed_count = 0

    for idx, reg_id in enumerate(registration_ids):
        if reg_id in provisioned_reg_ids:
            errors.append(
                BulkRowError(
                    row_index=idx,
                    identifier=f"registration_id={reg_id}",
                    error="Already provisioned in org_members.",
                )
            )
            failed_count += 1
            continue

        reg = reg_map.get(reg_id)
        if not reg:
            errors.append(
                BulkRowError(
                    row_index=idx,
                    identifier=f"registration_id={reg_id}",
                    error="Registration record not found.",
                )
            )
            failed_count += 1
            continue

        if reg.get("application_status") != "approved":
            errors.append(
                BulkRowError(
                    row_index=idx,
                    identifier=reg.get("full_name") or f"registration_id={reg_id}",
                    error=f"Application status is '{reg.get('application_status')}', must be 'approved'.",
                )
            )
            failed_count += 1
            continue

        email = (reg.get("email") or "").strip()
        if not _EMAIL_REGEX.match(email):
            errors.append(
                BulkRowError(
                    row_index=idx,
                    identifier=reg.get("full_name") or f"registration_id={reg_id}",
                    error="Missing or invalid email address.",
                )
            )
            failed_count += 1
            continue

        full_name = (reg.get("full_name") or "").strip()
        first_name, last_name = split_full_name(full_name)
        accepted_date = _parse_accepted_date(reg.get("reviewed_at") or reg.get("created_at"))

        org_id = generate_org_id(accepted_date, existing_org_ids)
        username = generate_randomized_username(first_name, last_name, existing_usernames)
        temp_password = generate_default_password(12)
        pw_hash = hash_password(temp_password)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        insert_row: Dict[str, Any] = {
            "registration_id": reg_id,
            "org_id": org_id,
            "username": username,
            "password_hash": pw_hash,
            "must_change_password": True,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": email,
            "student_id": reg.get("student_id"),
            "year": reg.get("year"),
            "program": reg.get("program"),
            "division_type": reg.get("division_type"),
            "division_name": reg.get("division_name"),
            "accepted_date": accepted_date.isoformat(),
            "status": "active",
            "credentials_emailed_at": now_iso,
            "created_by": officer_name,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        ins_res = client.table("org_members").insert(insert_row).execute()
        ins_rows = _as_rows(ins_res.data)
        saved_row: Dict[str, Any] = ins_rows[0] if ins_rows else insert_row
        provisioned_reg_ids.add(reg_id)

        mail_res = _dispatch_credential_email(
            recipient_email=email,
            full_name=full_name,
            org_id=org_id,
            username=username,
            plaintext_password=temp_password,
            sender_id=officer_id,
            registration_id=reg_id,
        )
        # Clear transient plaintext reference immediately
        del temp_password

        delivery_status = cast(
            Literal["sent", "failed", "dry_run"],
            mail_res.get("delivery_status", "sent"),
        )
        if delivery_status in ("sent", "dry_run"):
            emailed_count += 1

        generated.append(
            GeneratedMemberSummary(
                id=str(saved_row.get("id")),
                org_id=org_id,
                username=username,
                full_name=full_name,
                email=email,
                division_name=reg.get("division_name"),
                accepted_date=accepted_date.isoformat(),
                email_status=delivery_status,
                email_error=mail_res.get("error"),
            )
        )

    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="bulk_generate_members_from_approved",
        target_type="org_members",
        target_id="batch",
        details={
            "requested_count": len(registration_ids),
            "generated_count": len(generated),
            "emailed_count": emailed_count,
            "failed_count": failed_count,
        },
    )

    return BulkGenerationResponse(
        generated_count=len(generated),
        emailed_count=emailed_count,
        failed_count=failed_count,
        members=generated,
        errors=errors,
    )


def bulk_generate_from_csv(
    rows: List[CsvMemberInput],
    officer_id: str,
    officer_name: str,
) -> BulkGenerationResponse:
    """
    Generates Org IDs, randomized usernames, and hashed default passwords for CSV-uploaded
    students not in the registrations table, emailing each student individually.
    """
    client = get_supabase_admin()
    existing_org_ids, existing_usernames, _ = _load_existing_identifiers(client)

    generated: List[GeneratedMemberSummary] = []
    errors: List[BulkRowError] = []
    emailed_count = 0
    failed_count = 0

    for idx, item in enumerate(rows):
        first_name = " ".join(item.first_name.strip().split())
        last_name = " ".join(item.last_name.strip().split())
        full_name = f"{first_name} {last_name}".strip()
        email = item.email.strip()

        if not first_name or not last_name:
            errors.append(
                BulkRowError(
                    row_index=idx + 1,
                    identifier=email or f"Row {idx + 1}",
                    error="First name and last name are required.",
                )
            )
            failed_count += 1
            continue

        if not _EMAIL_REGEX.match(email):
            errors.append(
                BulkRowError(
                    row_index=idx + 1,
                    identifier=full_name or f"Row {idx + 1}",
                    error=f"Invalid email address '{email}'.",
                )
            )
            failed_count += 1
            continue

        accepted_date = _parse_accepted_date(item.accepted_date)
        org_id = generate_org_id(accepted_date, existing_org_ids)
        username = generate_randomized_username(first_name, last_name, existing_usernames)
        temp_password = generate_default_password(12)
        pw_hash = hash_password(temp_password)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        insert_row: Dict[str, Any] = {
            "registration_id": None,
            "org_id": org_id,
            "username": username,
            "password_hash": pw_hash,
            "must_change_password": True,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": email,
            "student_id": (item.student_id or "").strip() or None,
            "year": (item.year or "").strip() or None,
            "program": (item.program or "").strip() or None,
            "division_type": (item.division_type or "").strip() or None,
            "division_name": (item.division_name or "").strip() or None,
            "accepted_date": accepted_date.isoformat(),
            "status": "active",
            "credentials_emailed_at": now_iso,
            "created_by": officer_name,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        ins_res = client.table("org_members").insert(insert_row).execute()
        ins_rows = _as_rows(ins_res.data)
        saved_row: Dict[str, Any] = ins_rows[0] if ins_rows else insert_row

        mail_res = _dispatch_credential_email(
            recipient_email=email,
            full_name=full_name,
            org_id=org_id,
            username=username,
            plaintext_password=temp_password,
            sender_id=officer_id,
            registration_id=None,
        )
        del temp_password

        delivery_status = cast(
            Literal["sent", "failed", "dry_run"],
            mail_res.get("delivery_status", "sent"),
        )
        if delivery_status in ("sent", "dry_run"):
            emailed_count += 1

        generated.append(
            GeneratedMemberSummary(
                id=str(saved_row.get("id")),
                org_id=org_id,
                username=username,
                full_name=full_name,
                email=email,
                division_name=cast(Optional[str], insert_row.get("division_name")),
                accepted_date=accepted_date.isoformat(),
                email_status=delivery_status,
                email_error=mail_res.get("error"),
            )
        )

    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="bulk_generate_members_from_csv",
        target_type="org_members",
        target_id="csv_batch",
        details={
            "requested_count": len(rows),
            "generated_count": len(generated),
            "emailed_count": emailed_count,
            "failed_count": failed_count,
        },
    )

    return BulkGenerationResponse(
        generated_count=len(generated),
        emailed_count=emailed_count,
        failed_count=failed_count,
        members=generated,
        errors=errors,
    )


def list_org_members(
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> OrgMemberListResponse:
    """Returns a paginated list of provisioned org members (never returning password_hash)."""
    client = get_supabase_admin()
    query = client.table("org_members").select(
        "id, registration_id, org_id, username, first_name, last_name, full_name, email, "
        "student_id, year, program, division_type, division_name, accepted_date, status, "
        "must_change_password, credentials_emailed_at, created_by, created_at",
        count=cast(Any, "exact"),
    )

    if status_filter and status_filter != "all":
        query = query.eq("status", status_filter)

    if search and search.strip():
        s = search.strip()
        query = query.or_(
            f"full_name.ilike.%{s}%,org_id.ilike.%{s}%,username.ilike.%{s}%,email.ilike.%{s}%"
        )

    start = (page - 1) * page_size
    end = start + page_size - 1
    res = query.order("created_at", desc=True).range(start, end).execute()
    rows = _as_rows(res.data)
    raw_count = getattr(res, "count", None)
    total = int(raw_count) if raw_count is not None else len(rows)

    members = [
        OrgMemberItem(
            id=str(r["id"]),
            registration_id=r.get("registration_id"),
            org_id=r["org_id"],
            username=r["username"],
            first_name=r.get("first_name") or "",
            last_name=r.get("last_name") or "",
            full_name=r.get("full_name") or "",
            email=r.get("email") or "",
            student_id=r.get("student_id"),
            year=r.get("year"),
            program=r.get("program"),
            division_type=r.get("division_type"),
            division_name=r.get("division_name"),
            accepted_date=str(r.get("accepted_date") or ""),
            status=cast(Literal["active", "suspended", "revoked"], r.get("status") or "active"),
            must_change_password=bool(r.get("must_change_password", True)),
            credentials_emailed_at=r.get("credentials_emailed_at"),
            created_by=r.get("created_by"),
            created_at=r.get("created_at"),
        )
        for r in rows
    ]

    return OrgMemberListResponse(
        members=members,
        total=total,
        page=page,
        page_size=page_size,
    )


def reset_and_email_member_password(
    member_id: str,
    officer_id: str,
    officer_name: str,
) -> PasswordResetResponse:
    """Rotates a member's password hash and emails the new temporary password directly to the student."""
    client = get_supabase_admin()
    res = client.table("org_members").select("*").eq("id", member_id).execute()
    member_rows = _as_rows(res.data)
    if not member_rows:
        raise HTTPException(status_code=404, detail="Member not found.")

    member = member_rows[0]
    temp_password = generate_default_password(12)
    pw_hash = hash_password(temp_password)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    client.table("org_members").update({
        "password_hash": pw_hash,
        "must_change_password": True,
        "credentials_emailed_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", member_id).execute()

    mail_res = _dispatch_credential_email(
        recipient_email=member["email"],
        full_name=member["full_name"],
        org_id=member["org_id"],
        username=member["username"],
        plaintext_password=temp_password,
        sender_id=officer_id,
        registration_id=member.get("registration_id"),
    )
    del temp_password

    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="reset_member_password",
        target_type="org_members",
        target_id=member_id,
        details={"org_id": member["org_id"], "delivery_status": mail_res.get("delivery_status")},
    )

    return PasswordResetResponse(
        member_id=str(member["id"]),
        org_id=member["org_id"],
        username=member["username"],
        email=member["email"],
        email_status=cast(Literal["sent", "failed", "dry_run"], mail_res.get("delivery_status", "sent")),
        email_error=mail_res.get("error"),
    )


def update_member_status(
    member_id: str,
    new_status: str,
    officer_id: str,
    officer_name: str,
) -> OrgMemberItem:
    """Updates a member's status ('active', 'suspended', or 'revoked')."""
    client = get_supabase_admin()
    res = client.table("org_members").select("*").eq("id", member_id).execute()
    existing_rows = _as_rows(res.data)
    if not existing_rows:
        raise HTTPException(status_code=404, detail="Member not found.")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    upd = (
        client.table("org_members")
        .update({"status": new_status, "updated_at": now_iso})
        .eq("id", member_id)
        .execute()
    )
    upd_rows = _as_rows(upd.data)
    r = upd_rows[0] if upd_rows else existing_rows[0]

    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action=f"member_status_{new_status}",
        target_type="org_members",
        target_id=member_id,
        details={"org_id": r["org_id"], "status": new_status},
    )

    return OrgMemberItem(
        id=str(r["id"]),
        registration_id=r.get("registration_id"),
        org_id=r["org_id"],
        username=r["username"],
        first_name=r.get("first_name") or "",
        last_name=r.get("last_name") or "",
        full_name=r.get("full_name") or "",
        email=r.get("email") or "",
        student_id=r.get("student_id"),
        year=r.get("year"),
        program=r.get("program"),
        division_type=r.get("division_type"),
        division_name=r.get("division_name"),
        accepted_date=str(r.get("accepted_date") or ""),
        status=cast(Literal["active", "suspended", "revoked"], r.get("status") or new_status),
        must_change_password=bool(r.get("must_change_password", True)),
        credentials_emailed_at=r.get("credentials_emailed_at"),
        created_by=r.get("created_by"),
        created_at=r.get("created_at"),
    )


def create_api_key(
    name: str,
    rate_limit_per_min: int,
    officer_id: str,
    officer_name: str,
) -> ApiKeyCreatedResponse:
    """Generates a new external system API key and stores only its SHA-256 hash."""
    client = get_supabase_admin()
    raw_key, key_prefix, key_hash = generate_api_key()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    row: Dict[str, Any] = {
        "name": name.strip(),
        "key_prefix": key_prefix,
        "key_hash": key_hash,
        "scopes": ["members:validate"],
        "rate_limit_per_min": rate_limit_per_min,
        "is_active": True,
        "last_used_at": None,
        "created_by": officer_name,
        "created_at": now_iso,
        "revoked_at": None,
    }
    res = client.table("api_keys").insert(row).execute()
    saved_rows = _as_rows(res.data)
    saved: Dict[str, Any] = saved_rows[0] if saved_rows else row

    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="create_api_key",
        target_type="api_keys",
        target_id=str(saved.get("id")),
        details={"name": row["name"], "key_prefix": key_prefix, "rate_limit_per_min": rate_limit_per_min},
    )

    return ApiKeyCreatedResponse(
        id=str(saved.get("id")),
        name=saved["name"],
        key_prefix=saved["key_prefix"],
        scopes=saved.get("scopes") or ["members:validate"],
        rate_limit_per_min=int(saved.get("rate_limit_per_min", 60)),
        is_active=bool(saved.get("is_active", True)),
        last_used_at=saved.get("last_used_at"),
        created_by=saved.get("created_by"),
        created_at=saved.get("created_at"),
        revoked_at=saved.get("revoked_at"),
        api_key=raw_key,
    )


def list_api_keys() -> List[ApiKeyItem]:
    """Lists all API keys without exposing key_hash."""
    client = get_supabase_admin()
    res = client.table("api_keys").select("*").order("created_at", desc=True).execute()
    rows = _as_rows(res.data)
    return [
        ApiKeyItem(
            id=str(r["id"]),
            name=r["name"],
            key_prefix=r["key_prefix"],
            scopes=r.get("scopes") or ["members:validate"],
            rate_limit_per_min=int(r.get("rate_limit_per_min", 60)),
            is_active=bool(r.get("is_active", True)),
            last_used_at=r.get("last_used_at"),
            created_by=r.get("created_by"),
            created_at=r.get("created_at"),
            revoked_at=r.get("revoked_at"),
        )
        for r in rows
    ]


def revoke_api_key(key_id: str, officer_id: str, officer_name: str) -> ApiKeyItem:
    """Revokes an API key immediately."""
    client = get_supabase_admin()
    res = client.table("api_keys").select("*").eq("id", key_id).execute()
    key_rows = _as_rows(res.data)
    if not key_rows:
        raise HTTPException(status_code=404, detail="API key not found.")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    upd = (
        client.table("api_keys")
        .update({"is_active": False, "revoked_at": now_iso})
        .eq("id", key_id)
        .execute()
    )
    upd_rows = _as_rows(upd.data)
    r = upd_rows[0] if upd_rows else key_rows[0]

    log_action(
        actor_id=officer_id,
        actor_name=officer_name,
        action="revoke_api_key",
        target_type="api_keys",
        target_id=key_id,
        details={"name": r["name"], "key_prefix": r["key_prefix"]},
    )

    return ApiKeyItem(
        id=str(r["id"]),
        name=r["name"],
        key_prefix=r["key_prefix"],
        scopes=r.get("scopes") or ["members:validate"],
        rate_limit_per_min=int(r.get("rate_limit_per_min", 60)),
        is_active=bool(r.get("is_active", False)),
        last_used_at=r.get("last_used_at"),
        created_by=r.get("created_by"),
        created_at=r.get("created_at"),
        revoked_at=r.get("revoked_at"),
    )


def list_validation_logs(limit: int = 50) -> List[ValidationLogItem]:
    """Lists recent external credential validation events."""
    client = get_supabase_admin()
    res = (
        client.table("api_validation_logs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = _as_rows(res.data)
    return [
        ValidationLogItem(
            id=str(r["id"]),
            api_key_id=str(r["api_key_id"]) if r.get("api_key_id") else None,
            api_key_name=r.get("api_key_name"),
            org_id_attempted=r.get("org_id_attempted"),
            username_attempted=r.get("username_attempted"),
            outcome=r.get("outcome") or "invalid_credentials",
            client_ip=r.get("client_ip"),
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


def authenticate_api_key(raw_key: Optional[str]) -> Dict[str, Any]:
    """Authenticates an external request's X-API-Key header against active SHA-256 hashes."""
    if not raw_key or not raw_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header.",
        )

    key_hash = hash_api_key(raw_key)
    client = get_supabase_admin()
    res = client.table("api_keys").select("*").eq("key_hash", key_hash).execute()
    key_rows = _as_rows(res.data)
    if not key_rows:
        raise HTTPException(
            status_code=401,
            detail="Invalid or unrecognized API key.",
        )

    key_row = key_rows[0]
    if not key_row.get("is_active", False):
        raise HTTPException(
            status_code=401,
            detail="This API key has been revoked.",
        )

    return key_row


def _log_validation_attempt(
    client,
    api_key_row: Dict[str, Any],
    org_id: str,
    username: str,
    outcome: str,
    client_ip: str,
) -> None:
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        client.table("api_validation_logs").insert({
            "api_key_id": api_key_row.get("id"),
            "api_key_name": api_key_row.get("name"),
            "org_id_attempted": org_id,
            "username_attempted": username,
            "outcome": outcome,
            "client_ip": client_ip,
            "created_at": now_iso,
        }).execute()
        client.table("api_keys").update({"last_used_at": now_iso}).eq("id", api_key_row["id"]).execute()
    except Exception:
        pass


def record_rate_limited_attempt(
    api_key_row: Dict[str, Any],
    org_id: str,
    username: str,
    client_ip: str,
) -> None:
    client = get_supabase_admin()
    _log_validation_attempt(client, api_key_row, org_id, username, "rate_limited", client_ip)


def validate_member_credentials(
    org_id: str,
    username: str,
    password: str,
    api_key_row: Dict[str, Any],
    client_ip: str,
) -> ExternalValidateResponse:
    """
    Strictly read-only verification of (org_id, username, password) against `org_members`.
    Uses constant-time password verification and uniform mismatch responses to prevent enumeration.
    """
    client = get_supabase_admin()
    clean_org_id = org_id.strip().upper()
    clean_username = username.strip().lower()

    res = (
        client.table("org_members")
        .select("*")
        .eq("org_id", clean_org_id)
        .execute()
    )
    member_rows = _as_rows(res.data)

    if not member_rows:
        _log_validation_attempt(client, api_key_row, clean_org_id, clean_username, "invalid_credentials", client_ip)
        return ExternalValidateResponse(valid=False, reason="invalid_credentials", member=None)

    member = member_rows[0]
    stored_username = (member.get("username") or "").strip().lower()
    stored_hash = member.get("password_hash") or ""

    # Always run verify_password even if username differs to keep response timing uniform
    pw_ok = verify_password(password, stored_hash)
    user_ok = (stored_username == clean_username)

    if not (pw_ok and user_ok):
        _log_validation_attempt(client, api_key_row, clean_org_id, clean_username, "invalid_credentials", client_ip)
        return ExternalValidateResponse(valid=False, reason="invalid_credentials", member=None)

    if member.get("status") != "active":
        _log_validation_attempt(client, api_key_row, clean_org_id, clean_username, "inactive_member", client_ip)
        return ExternalValidateResponse(valid=False, reason="inactive_member", member=None)

    _log_validation_attempt(client, api_key_row, clean_org_id, clean_username, "valid", client_ip)
    return ExternalValidateResponse(
        valid=True,
        reason=None,
        member=ExternalMemberProfile(
            org_id=member["org_id"],
            username=member["username"],
            first_name=member.get("first_name") or "",
            last_name=member.get("last_name") or "",
            full_name=member.get("full_name") or "",
            email=member.get("email") or "",
            student_id=member.get("student_id"),
            year=member.get("year"),
            program=member.get("program"),
            division_type=member.get("division_type"),
            division_name=member.get("division_name"),
            status=member.get("status") or "active",
            must_change_password=bool(member.get("must_change_password", True)),
        ),
    )

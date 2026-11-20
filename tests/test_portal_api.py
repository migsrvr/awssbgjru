import datetime
from typing import Dict, Any, List
import pytest
from fastapi.testclient import TestClient

from backend.main import app


class FakeTable:
    def __init__(self, store: List[Dict[str, Any]]):
        self.store = store
        self._filters = []
        self._order_col = None
        self._order_desc = False
        self._limit = None
        self._range = None
        self._count_mode = None

    def select(self, cols="*", count=None):
        q = FakeTable(self.store)
        q._count_mode = count
        return q

    def eq(self, col, val):
        self._filters.append(lambda r: r.get(col) == val)
        return self

    def ilike(self, col, pattern):
        needle = pattern.strip("%").lower()
        self._filters.append(lambda r: needle in str(r.get(col) or "").lower())
        return self

    def in_(self, col, vals):
        val_set = set(vals)
        self._filters.append(lambda r: r.get(col) in val_set)
        return self

    def or_(self, expr: str):
        parts = expr.split(",")
        def _match(r):
            for p in parts:
                if ".ilike." in p:
                    c, pat = p.split(".ilike.", 1)
                    if pat.strip("%").lower() in str(r.get(c) or "").lower():
                        return True
                elif ".eq." in p:
                    c, val = p.split(".eq.", 1)
                    if str(r.get(c)) == val:
                        return True
            return False
        self._filters.append(_match)
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def insert(self, payload):
        q = FakeTable(self.store)
        rows = payload if isinstance(payload, list) else [payload]
        inserted = []
        for idx, r in enumerate(rows):
            copy = dict(r)
            if "id" not in copy or copy["id"] is None:
                copy["id"] = f"uuid-{len(self.store) + idx + 1}"
            if "created_at" not in copy:
                copy["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.store.append(copy)
            inserted.append(copy)
        q._inserted = inserted
        return q

    def update(self, payload):
        self._update_payload = dict(payload)
        return self

    def execute(self):
        if hasattr(self, "_inserted"):
            return type("Res", (), {"data": self._inserted, "count": len(self._inserted)})()

        matched = [r for r in self.store if all(f(r) for f in self._filters)]

        if hasattr(self, "_update_payload"):
            for r in matched:
                r.update(self._update_payload)
            return type("Res", (), {"data": matched, "count": len(matched)})()

        total_count = len(matched)
        if self._order_col:
            matched.sort(key=lambda r: str(r.get(self._order_col) or ""), reverse=self._order_desc)
        if self._range:
            s, e = self._range
            matched = matched[s : e + 1]
        elif self._limit is not None:
            matched = matched[: self._limit]

        return type("Res", (), {"data": matched, "count": total_count})()


class FakeSupabase:
    def __init__(self):
        self.tables: Dict[str, List[Dict[str, Any]]] = {
            "registrations": [
                {
                    "id": 101,
                    "full_name": "Juan Dela Cruz",
                    "student_id": "24-123456",
                    "email": "juan.delacruz@my.jru.edu",
                    "year": "Third Year",
                    "program": "BS Information Technology",
                    "division_type": "skillbuilder",
                    "division_name": "Cloud Computing",
                    "application_status": "approved",
                    "reviewed_at": "2026-11-20T09:30:00+08:00",
                    "created_at": "2026-11-18T08:00:00+08:00",
                },
                {
                    "id": 102,
                    "full_name": "Maria Clara Santos",
                    "student_id": "24-654321",
                    "email": "maria.santos@my.jru.edu",
                    "year": "Second Year",
                    "program": "BS Computer Engineering",
                    "division_type": "office",
                    "division_name": "Operations",
                    "application_status": "approved",
                    "reviewed_at": "2026-11-20T10:15:00+08:00",
                    "created_at": "2026-11-19T08:00:00+08:00",
                },
            ],
            "org_members": [],
            "api_keys": [],
            "api_validation_logs": [],
            "email_logs": [],
            "email_templates": [],
            "audit_logs": [],
        }

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = []
        return FakeTable(self.tables[name])


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeSupabase()
    monkeypatch.setattr("backend.services.member_portal_service.get_supabase_admin", lambda: db)
    monkeypatch.setattr("backend.services.email_service.get_supabase_admin", lambda: db)
    monkeypatch.setattr("backend.services.audit_service.get_supabase_admin", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    return TestClient(app)


def test_rbac_blocks_reviewer_and_administrator_from_portal_routes(client):
    # Reviewer token -> 403
    r_rev = client.get(
        "/api/v1/admin/portal/members",
        headers={"Authorization": "Bearer dev-token"},
    )
    assert r_rev.status_code == 403

    # Administrator (Relations) token -> 403
    r_adm = client.get(
        "/api/v1/admin/portal/members",
        headers={"Authorization": "Bearer dev-admin-token"},
    )
    assert r_adm.status_code == 403

    # Executive token -> 200
    r_exec = client.get(
        "/api/v1/admin/portal/members",
        headers={"Authorization": "Bearer dev-executive-token"},
    )
    assert r_exec.status_code == 200


def test_bulk_generate_from_approved_and_zero_plaintext_guarantee(client, fake_db, monkeypatch):
    sent_messages = []

    def spy_send_email(**kwargs):
        sent_messages.append(kwargs)
        # Still record to fake_db email_logs with log_body
        fake_db.table("email_logs").insert({
            "recipient_email": kwargs["recipient_email"],
            "subject": kwargs["subject"],
            "body": kwargs.get("log_body") or kwargs["body"],
            "delivery_status": "sent",
        }).execute()
        return {"success": True, "delivery_status": "sent", "error": None}

    monkeypatch.setattr("backend.services.member_portal_service.send_email", spy_send_email)

    exec_headers = {"Authorization": "Bearer dev-executive-token"}

    # 1. Check unprovisioned approved applicants
    unprov = client.get("/api/v1/admin/portal/unprovisioned-approved", headers=exec_headers)
    assert unprov.status_code == 200
    assert len(unprov.json()) == 2

    # 2. Generate credentials for both approved applicants
    gen_res = client.post(
        "/api/v1/admin/portal/members/generate-from-approved",
        json={"registration_ids": [101, 102]},
        headers=exec_headers,
    )
    assert gen_res.status_code == 200
    payload = gen_res.json()
    assert payload["generated_count"] == 2
    assert payload["emailed_count"] == 2

    # CRITICAL SECURITY CHECK: No plaintext password or password_hash in response!
    raw_response_text = gen_res.text
    assert "password_hash" not in raw_response_text
    assert "default_password" not in raw_response_text
    assert "pbkdf2_sha256" not in raw_response_text

    members = payload["members"]
    assert members[0]["org_id"] == "AWSSBG-1120-001"
    assert members[1]["org_id"] == "AWSSBG-1120-002"

    # Verify email_logs redacted the password while outgoing SMTP email had the password
    assert len(sent_messages) == 2
    assert "[REDACTED]" in fake_db.tables["email_logs"][0]["body"]
    assert "[REDACTED]" not in sent_messages[0]["body"]

    # 3. Unprovisioned list should now be empty
    unprov_after = client.get("/api/v1/admin/portal/unprovisioned-approved", headers=exec_headers)
    assert len(unprov_after.json()) == 0


def test_bulk_generate_from_csv_and_external_validation_flow(client, fake_db, monkeypatch):
    captured_passwords: Dict[str, str] = {}

    def capture_send_email(**kwargs):
        # Extract the temporary password from the email body sent to the student
        body = kwargs["body"]
        for line in body.splitlines():
            if "Temporary Password:" in line:
                pw = line.split("Temporary Password:", 1)[1].strip()
                captured_passwords[kwargs["recipient_email"]] = pw
        return {"success": True, "delivery_status": "sent", "error": None}

    monkeypatch.setattr("backend.services.member_portal_service.send_email", capture_send_email)

    exec_headers = {"Authorization": "Bearer dev-executive-token"}

    # 1. Bulk generate via CSV payload
    csv_res = client.post(
        "/api/v1/admin/portal/members/generate-from-csv",
        json={
            "members": [
                {
                    "first_name": "Miguel",
                    "last_name": "Rivera",
                    "email": "miguel.rivera@my.jru.edu",
                    "student_id": "23-111222",
                    "year": "Fourth Year",
                    "program": "BS Information Technology",
                    "division_type": "skillbuilder",
                    "division_name": "Software Development",
                    "accepted_date": "2026-09-16",
                }
            ]
        },
        headers=exec_headers,
    )
    assert csv_res.status_code == 200
    csv_data = csv_res.json()
    assert csv_data["generated_count"] == 1
    member_summary = csv_data["members"][0]
    assert member_summary["org_id"] == "AWSSBG-0916-001"
    username = member_summary["username"]
    student_pw = captured_passwords["miguel.rivera@my.jru.edu"]

    # 2. Create an External API Key
    key_res = client.post(
        "/api/v1/admin/portal/api-keys",
        json={"name": "Event Attendance System", "rate_limit_per_min": 5},
        headers=exec_headers,
    )
    assert key_res.status_code == 200
    key_data = key_res.json()
    raw_api_key = key_data["api_key"]
    key_id = key_data["id"]
    assert raw_api_key.startswith("sbg_live_")

    # 3. Validate credentials via POST /api/v1/external/validate
    val_ok = client.post(
        "/api/v1/external/validate",
        headers={"X-API-Key": raw_api_key},
        json={
            "org_id": "AWSSBG-0916-001",
            "username": username,
            "password": student_pw,
        },
    )
    assert val_ok.status_code == 200
    val_body = val_ok.json()
    assert val_body["valid"] is True
    assert val_body["member"]["full_name"] == "Miguel Rivera"
    assert val_body["member"]["division_name"] == "Software Development"
    assert "password_hash" not in val_body["member"]
    assert "password" not in val_body["member"]
    assert student_pw not in str(val_body)

    # 4. Wrong password -> valid: False, uniform reason
    val_bad_pw = client.post(
        "/api/v1/external/validate",
        headers={"X-API-Key": raw_api_key},
        json={
            "org_id": "AWSSBG-0916-001",
            "username": username,
            "password": "WrongPassword123!",
        },
    )
    assert val_bad_pw.status_code == 200
    assert val_bad_pw.json() == {
        "valid": False,
        "reason": "invalid_credentials",
        "member": None,
    }

    # 5. Suspend member -> valid: False, reason: inactive_member
    member_id = member_summary["id"]
    suspend_res = client.patch(
        f"/api/v1/admin/portal/members/{member_id}/status",
        json={"status": "suspended"},
        headers=exec_headers,
    )
    assert suspend_res.status_code == 200

    val_suspended = client.post(
        "/api/v1/external/validate",
        headers={"X-API-Key": raw_api_key},
        json={
            "org_id": "AWSSBG-0916-001",
            "username": username,
            "password": student_pw,
        },
    )
    assert val_suspended.status_code == 200
    assert val_suspended.json()["valid"] is False
    assert val_suspended.json()["reason"] == "inactive_member"

    # 6. Revoke API Key -> 401 Unauthorized
    rev_res = client.post(
        f"/api/v1/admin/portal/api-keys/{key_id}/revoke",
        headers=exec_headers,
    )
    assert rev_res.status_code == 200

    val_revoked = client.post(
        "/api/v1/external/validate",
        headers={"X-API-Key": raw_api_key},
        json={
            "org_id": "AWSSBG-0916-001",
            "username": username,
            "password": student_pw,
        },
    )
    assert val_revoked.status_code == 401

    # 7. Scoped External OpenAPI spec works and does not leak admin routes
    openapi_res = client.get("/api/v1/external/openapi.json")
    assert openapi_res.status_code == 200
    paths = openapi_res.json().get("paths", {})
    assert "/api/v1/external/validate" in paths
    assert not any("/admin" in p for p in paths)


def test_builtin_env_executive_login_and_token_verification(client, monkeypatch):
    from backend.api import config as api_config

    monkeypatch.setattr(api_config, "EXECUTIVE_USERNAME", "exec_lead")
    monkeypatch.setattr(api_config, "EXECUTIVE_PASSWORD", "SuperSecretExec!2026")
    monkeypatch.setattr(api_config, "EXECUTIVE_FULL_NAME", "AWS SBG President")
    monkeypatch.setattr(api_config, "EXECUTIVE_SECRET", "unit-test-hmac-secret-key")
    monkeypatch.setattr(api_config, "EXECUTIVE_SESSION_TTL_HOURS", 12)

    # 1. Login with bare username works without touching Supabase Auth
    login_res = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "exec_lead", "password": "SuperSecretExec!2026"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["user"]["role"] == "executive"
    assert login_data["user"]["full_name"] == "AWS SBG President"
    token = login_data["access_token"]
    assert token.startswith("exec_v1.")

    # 2. Login with full @awssbgjru.me email also works
    login_email_res = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "exec_lead@awssbgjru.me", "password": "SuperSecretExec!2026"},
    )
    assert login_email_res.status_code == 200

    # 3. Signed token authenticates /me and executive-only /portal/members
    me_res = client.get("/api/v1/admin/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "executive"

    portal_res = client.get(
        "/api/v1/admin/portal/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert portal_res.status_code == 200

    # 4. Tampered token -> 401 Unauthorized
    tampered = token[:-4] + "dead"
    bad_res = client.get(
        "/api/v1/admin/portal/members",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert bad_res.status_code == 401

    # 5. Disabled when EXECUTIVE_PASSWORD is empty -> 401
    monkeypatch.setattr(api_config, "EXECUTIVE_PASSWORD", "")
    disabled_res = client.get(
        "/api/v1/admin/portal/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disabled_res.status_code == 401

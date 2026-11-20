# Centralized Portal API & Credential Generator — Implementation Plan

**Date**: 2026-11-20

## Slice Matrix & File Ownership
1. **Contracts & Schema (Gemini Lead)**:
   - `scripts/portal_api_schema.sql`
   - `backend/schemas/portal_members.py`
   - `backend/auth.py` & `scripts/create_officer.py`
   - `backend/services/email_service.py` (redacted `log_body` support + `portal_credentials` template)
2. **Slice 1 — Cryptographic & Credential Generator Service (TDD)**:
   - Test: `tests/test_credential_service.py`
   - Code: `backend/services/credential_service.py`
3. **Slice 2 — Member Portal Service & Routers (TDD)**:
   - Test: `tests/test_portal_api.py`
   - Code: `backend/services/member_portal_service.py`, `backend/routers/portal_admin.py`, `backend/routers/external_api.py`, `backend/main.py`, `backend/api/index.py`
4. **Slice 3 — Plug-and-Play SDKs, AI Agent Specs & Docker/Caddy Wiring (TDD)**:
   - Test: `tests/test_js_sdk.mjs`, `tests/test_python_sdk.py`
   - Code: `sdk/js/awssbg-auth-sdk.js`, `sdk/js/awssbg-auth-sdk.d.ts`, `sdk/python/awssbg_auth_sdk.py`, `sdk/llms.txt`, `sdk/AGENT_SKILL.md`, `Dockerfile.web`, `deploy/Caddyfile`
5. **Slice 4 — Executive Console UI**:
   - Code: `frontend/pages/admin.html`, `frontend/js/admin-portal.js`, `frontend/js/admin.js`, `frontend/css/admin.css`

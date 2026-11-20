# Centralized Member Credential Generator, Executive RBAC & External Validation API/SDK — Design Spec

**Date**: 2026-11-20
**Status**: Approved

## 1. Overview
Provides an Executive-only bulk credential generator (`AWSSBG-MMDD-NNN` Org ID, randomized username from First & Last Name, PBKDF2-HMAC-SHA256 hashed default password emailed directly to students with zero plaintext exposure) and an isolated read-only external validation API (`POST /api/v1/external/validate`) with plug-and-play JS/TS & Python SDKs and AI-Agent discovery specs (`/sdk/llms.txt`, `/sdk/AGENT_SKILL.md`, `/api/v1/external/openapi.json`).

## 2. Domain Model & Invariants
1. **3-Tier RBAC (`admin_users.role`)**:
   - `reviewer` < `administrator` (Relations) < `executive`.
   - Invariant: Only `executive` can call `/api/v1/admin/portal/*` or view `.executive-only` UI elements. `administrator` retains access to `/settings`, `/templates`, `/export`, `/departments`, `/audit-logs` via `require_admin`.
2. **Zero-Plaintext Credential Invariant**:
   - Plaintext passwords never appear in any HTTP response, CSV export, or `email_logs` table row (`[REDACTED]`).
   - Only `pbkdf2_sha256$260000$<salt_hex>$<hash_hex>` is stored in `org_members.password_hash`.
3. **Unique Org ID (`AWSSBG-MMDD-NNN`)**:
   - `MMDD` = Month & Day accepted (`reviewed_at` for approved applications, `accepted_date` or current date for CSV).
   - `NNN` = 3-digit zero-padded sequence per `MMDD` (`001`, `002`, ...), strictly unique across `org_members`.
4. **External Validation Isolation**:
   - `POST /api/v1/external/validate` authenticates external systems via `X-API-Key` (compared against SHA-256 `api_keys.key_hash` where `is_active = TRUE`), enforces per-key rate limiting, performs constant-time PBKDF2 verification on `org_members`, logs outcome without password to `api_validation_logs`, and returns safe member metadata.

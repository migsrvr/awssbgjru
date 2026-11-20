-- ==============================================================================
-- AWS SBG JRU Centralized Member Portal, Executive RBAC & External Validation API
-- Run this script in your Supabase SQL Editor (Dashboard -> SQL Editor)
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Upgrade admin_users role constraint to 3-tier RBAC: reviewer | administrator | executive
DO $$
DECLARE
    con_name TEXT;
BEGIN
    FOR con_name IN
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'admin_users'
          AND c.contype = 'c'
          AND pg_get_constraintdef(c.oid) ILIKE '%role%'
    LOOP
        EXECUTE format('ALTER TABLE admin_users DROP CONSTRAINT IF EXISTS %I', con_name);
    END LOOP;

    ALTER TABLE admin_users
        ADD CONSTRAINT admin_users_role_check
        CHECK (role IN ('reviewer', 'administrator', 'executive'));
END $$;

-- 2. Centralized Org Members Table (stores salted PBKDF2 password hashes only — never plaintext)
CREATE TABLE IF NOT EXISTS org_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    registration_id BIGINT UNIQUE REFERENCES registrations(id) ON DELETE SET NULL,
    org_id TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    student_id TEXT DEFAULT NULL,
    year TEXT DEFAULT NULL,
    program TEXT DEFAULT NULL,
    division_type TEXT DEFAULT NULL,
    division_name TEXT DEFAULT NULL,
    accepted_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'revoked')),
    credentials_emailed_at TIMESTAMPTZ DEFAULT NULL,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_members_org_id ON org_members(org_id);
CREATE INDEX IF NOT EXISTS idx_org_members_username ON org_members(username);
CREATE INDEX IF NOT EXISTS idx_org_members_status ON org_members(status);
CREATE INDEX IF NOT EXISTS idx_org_members_accepted_date ON org_members(accepted_date);

-- 3. External System API Keys Table (Executive-managed; stores SHA-256 key_hash only)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    scopes JSONB NOT NULL DEFAULT '["members:validate"]'::jsonb,
    rate_limit_per_min INT NOT NULL DEFAULT 60 CHECK (rate_limit_per_min >= 1 AND rate_limit_per_min <= 10000),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ DEFAULT NULL,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys(is_active);

-- 4. External API Validation Audit Logs (Never logs plaintext passwords)
CREATE TABLE IF NOT EXISTS api_validation_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
    api_key_name TEXT DEFAULT NULL,
    org_id_attempted TEXT DEFAULT NULL,
    username_attempted TEXT DEFAULT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('valid', 'invalid_credentials', 'inactive_member', 'rate_limited')),
    client_ip TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_validation_logs_created_at ON api_validation_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_validation_logs_api_key_id ON api_validation_logs(api_key_id);

-- 5. Seed Portal Credentials Email Template
INSERT INTO email_templates (id, name, subject, body, variables, version, is_active)
VALUES (
    'portal_credentials',
    'Member Portal Credentials',
    'Your AWS SBG JRU Official Member Portal Credentials',
    'Hi {{Applicant Name}},

Welcome to the AWS Student Builder Group – JRU Chapter! Your official centralized member portal credentials have been generated:

• Unique Org ID: {{Org ID}}
• Username: {{Username}}
• Temporary Password: {{Default Password}}

Please keep these credentials secure. You can use them across official AWS SBG JRU portals and member systems.

Regards,
AWS SBG JRU Executive Team',
    '["Applicant Name", "Org ID", "Username", "Default Password"]'::jsonb,
    1,
    TRUE
)
ON CONFLICT (id) DO NOTHING;

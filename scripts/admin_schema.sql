-- ==============================================================================
-- AWS SBG JRU Membership Review & Admin Panel Schema Migration
-- Run this script in your Supabase SQL Editor (Dashboard -> SQL Editor)
-- ==============================================================================

-- 1. Ensure extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Enhance the existing `registrations` table with workflow states
DO $$
BEGIN
    -- application_status: new, under_review, approved, revision_requested, resubmitted, declined, closed
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='application_status') THEN
        ALTER TABLE registrations ADD COLUMN application_status TEXT NOT NULL DEFAULT 'new';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='assigned_reviewer_id') THEN
        ALTER TABLE registrations ADD COLUMN assigned_reviewer_id TEXT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='assigned_reviewer_name') THEN
        ALTER TABLE registrations ADD COLUMN assigned_reviewer_name TEXT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='claimed_at') THEN
        ALTER TABLE registrations ADD COLUMN claimed_at TIMESTAMPTZ DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='reviewed_by') THEN
        ALTER TABLE registrations ADD COLUMN reviewed_by TEXT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='reviewed_at') THEN
        ALTER TABLE registrations ADD COLUMN reviewed_at TIMESTAMPTZ DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='decision_reason_code') THEN
        ALTER TABLE registrations ADD COLUMN decision_reason_code TEXT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='revision_token') THEN
        ALTER TABLE registrations ADD COLUMN revision_token TEXT UNIQUE DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='revision_deadline') THEN
        ALTER TABLE registrations ADD COLUMN revision_deadline TIMESTAMPTZ DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='revision_notes') THEN
        ALTER TABLE registrations ADD COLUMN revision_notes TEXT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='registrations' AND column_name='revision_requested_fields') THEN
        ALTER TABLE registrations ADD COLUMN revision_requested_fields JSONB DEFAULT '[]'::jsonb;
    END IF;
END $$;

-- Indexes on registrations for rapid filtering
CREATE INDEX IF NOT EXISTS idx_registrations_status ON registrations(application_status);
CREATE INDEX IF NOT EXISTS idx_registrations_created_at ON registrations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_registrations_student_id ON registrations(student_id);
CREATE INDEX IF NOT EXISTS idx_registrations_revision_token ON registrations(revision_token);

-- 3. Admin & Reviewer Roles Table
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY, -- Can reference auth.users(id)
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('reviewer', 'administrator')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Application Reviews History (one application can have multiple reviews)
CREATE TABLE IF NOT EXISTS application_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    registration_id BIGINT REFERENCES registrations(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    reviewer_name TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'declined', 'revision_requested', 'pending')),
    reason_code TEXT,
    internal_notes TEXT,
    rubric_scores JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reviews_reg_id ON application_reviews(registration_id);

-- 5. Email Templates Table
CREATE TABLE IF NOT EXISTS email_templates (
    id TEXT PRIMARY KEY, -- Slug, e.g. 'approved', 'revision_requested'
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    variables JSONB NOT NULL DEFAULT '[]'::jsonb,
    version INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT DEFAULT 'system'
);

-- 6. Email Logs Table (tracks delivery and audit trail of all outgoing emails)
CREATE TABLE IF NOT EXISTS email_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    registration_id BIGINT REFERENCES registrations(id) ON DELETE SET NULL,
    template_id TEXT REFERENCES email_templates(id) ON DELETE SET NULL,
    template_version INT DEFAULT 1,
    recipient_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    sender_id TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'sent' CHECK (delivery_status IN ('sent', 'failed', 'queued', 'dry_run')),
    error_message TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_logs_reg_id ON email_logs(registration_id);

-- 7. System Settings Table (registration open/close, qualification rubric)
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT DEFAULT 'system'
);

-- 8. Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_id TEXT,
    actor_name TEXT,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- ==============================================================================
-- Default Seed Data
-- ==============================================================================

-- Seed standard email templates
INSERT INTO email_templates (id, name, subject, body, variables, version, is_active)
VALUES
(
    'application_received',
    'Application Received',
    'We received your AWS SBG JRU application',
    'Hi {{Applicant Name}},

Thank you for applying to join AWS SBG JRU. We have received your application and our team will review your responses. We will contact you through this email once there is an update.

Regards,
AWS SBG JRU Team',
    '["Applicant Name"]'::jsonb,
    1,
    TRUE
),
(
    'approved',
    'Welcome / Approved',
    'Welcome to AWS SBG JRU',
    'Hi {{Applicant Name}},

Congratulations! Your application to join AWS SBG JRU has been approved.

{{Next Steps}}

We look forward to learning and building with you.

Regards,
AWS SBG JRU Team',
    '["Applicant Name", "Next Steps"]'::jsonb,
    1,
    TRUE
),
(
    'revision_requested',
    'Revision Requested',
    'Please revise your AWS SBG JRU application',
    'Hi {{Applicant Name}},

Thank you for your interest in AWS SBG JRU. Before we can complete our review, please revise the following part of your application:

{{Revision Notes}}

You may update your response using this secure link:
{{Revision Link}}

Please submit your revision by {{Revision Deadline}}.

Regards,
AWS SBG JRU Team',
    '["Applicant Name", "Revision Notes", "Revision Link", "Revision Deadline"]'::jsonb,
    1,
    TRUE
),
(
    'declined',
    'Application Update / Declined',
    'Update on your AWS SBG JRU application',
    'Hi {{Applicant Name}},

Thank you for taking the time to apply to AWS SBG JRU. After reviewing your application, we are unable to approve it at this time.

{{Optional General Reason}}

We appreciate your interest and encourage you to participate in future public AWS SBG JRU activities or apply again during a future recruitment period if eligible.

Regards,
AWS SBG JRU Team',
    '["Applicant Name", "Optional General Reason"]'::jsonb,
    1,
    TRUE
),
(
    'registration_closed',
    'Registration Closed',
    'AWS SBG JRU registration is currently closed',
    'Hi {{Applicant Name}},

Thank you for your interest in AWS SBG JRU. Membership registration is currently closed, so we are unable to process a new application at this time.

Please follow our official channels for announcements about the next recruitment period.

Regards,
AWS SBG JRU Team',
    '["Applicant Name"]'::jsonb,
    1,
    TRUE
)
ON CONFLICT (id) DO NOTHING;

-- Seed system settings
INSERT INTO system_settings (key, value)
VALUES
(
    'registration_status',
    '{"is_open": true, "closed_message": "Membership registration is currently closed. Follow our official channels for the next recruitment cycle."}'::jsonb
),
(
    'qualification_rubric',
    '[
        {"id": "jru_enrolled", "label": "Currently enrolled JRU student", "required": true},
        {"id": "complete_info", "label": "All required identity and contact fields complete and valid", "required": true},
        {"id": "genuine_interest", "label": "Explanation demonstrates genuine interest in cloud learning & community", "required": true},
        {"id": "code_of_conduct", "label": "Agrees to club code of conduct and student policies", "required": true},
        {"id": "quality_submission", "label": "Submitted information is authentic and non-abusive", "required": true}
    ]'::jsonb
)
ON CONFLICT (key) DO NOTHING;

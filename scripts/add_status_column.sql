-- ==============================================================================
-- Add 'status' column and resume support to 'registrations' table
-- Run this in your Supabase SQL Editor (Dashboard -> SQL Editor)
-- ==============================================================================

DO $$
BEGIN
    -- 1. Add 'status' column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'registrations' AND column_name = 'status'
    ) THEN
        ALTER TABLE registrations ADD COLUMN status TEXT NOT NULL DEFAULT 'new';
    END IF;

    -- 2. Add 'resume_base64' column for optional resume submission
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'registrations' AND column_name = 'resume_base64'
    ) THEN
        ALTER TABLE registrations ADD COLUMN resume_base64 TEXT DEFAULT '';
    END IF;

    -- 3. Add 'resume_filename' column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'registrations' AND column_name = 'resume_filename'
    ) THEN
        ALTER TABLE registrations ADD COLUMN resume_filename TEXT DEFAULT '';
    END IF;
END $$;

-- Index on status
CREATE INDEX IF NOT EXISTS idx_registrations_status_col ON registrations(status);

-- 4. Update all applicants on or before Sept 16, 2026 to 'approved'
UPDATE registrations
SET 
    status = 'approved',
    application_status = 'approved'
WHERE created_at <= '2026-09-16T23:59:59+08:00';

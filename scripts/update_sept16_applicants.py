"""Script to approve all applicants on or before September 16, 2026 in the Supabase registrations table."""

import sys
from backend.database import get_supabase_admin

CUTOFF = "2026-09-16T23:59:59+08:00"

def main():
    print(f"Connecting to Supabase to approve applicants on or before {CUTOFF}...")
    sb = get_supabase_admin()

    # 1. Fetch eligible rows
    res = sb.table("registrations").select("id, full_name, email, created_at, application_status").lte("created_at", CUTOFF).order("created_at", desc=False).execute()
    rows = res.data or []
    print(f"Found {len(rows)} applicant(s) submitted on or before September 16, 2026.")

    if not rows:
        print("No applicants found to update.")
        return

    # Check if 'status' column exists in registrations
    has_status_col = False
    try:
        sb.table("registrations").select("id, status").limit(1).execute()
        has_status_col = True
        print("[OK] 'status' column is present in registrations table.")
    except Exception:
        print("[NOTE] 'status' column does not exist yet in Supabase table.")
        print("       Please run 'scripts/add_status_column.sql' in your Supabase SQL Editor.")

    # 2. Perform updates
    update_payload = {"application_status": "approved"}
    if has_status_col:
        update_payload["status"] = "approved"

    print(f"Updating {len(rows)} applicants with payload: {update_payload}...")
    
    updated_count = 0
    for row in rows:
        reg_id = row["id"]
        up_res = sb.table("registrations").update(update_payload).eq("id", reg_id).execute()
        if up_res.data:
            updated_count += 1

    print(f"Successfully updated {updated_count}/{len(rows)} applicants to 'approved'.")

if __name__ == "__main__":
    main()

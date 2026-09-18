import sys
from backend.database import get_supabase_admin

def main():
    print("Testing connection to Supabase database...\n")
    try:
        client = get_supabase_admin()
        
        # 1. Check system_settings
        settings = client.table("system_settings").select("*").execute()
        print(f"[OK] system_settings table found ({len(settings.data)} records)")
        for s in settings.data:
            print(f"     - Key: {s.get('key')}")
            
        # 2. Check email_templates
        templates = client.table("email_templates").select("id, name").execute()
        print(f"\n[OK] email_templates table found ({len(templates.data)} templates)")
        for t in templates.data:
            print(f"     - {t.get('id')}: {t.get('name')}")
            
        # 3. Check registrations columns
        regs = client.table("registrations").select("id, application_status").limit(1).execute()
        print(f"\n[OK] registrations table updated with 'application_status' column")

        # 4. Check admin_users
        client.table("admin_users").select("id").limit(1).execute()
        print("[OK] admin_users table found")

        # 5. Check application_reviews
        client.table("application_reviews").select("id").limit(1).execute()
        print("[OK] application_reviews table found")

        # 6. Check email_logs
        client.table("email_logs").select("id").limit(1).execute()
        print("[OK] email_logs table found")

        # 7. Check audit_logs
        client.table("audit_logs").select("id").limit(1).execute()
        print("[OK] audit_logs table found")

        print("\nSUCCESS: All schema migrations and seed data are active in Supabase!")
    except Exception as e:
        print("\n[ERROR] Verification failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()

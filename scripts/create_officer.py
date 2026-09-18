import sys
import argparse
from pathlib import Path

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.database import get_supabase_admin


def list_officers(client):
    res = client.table("admin_users").select("*").order("created_at").execute()
    rows = res.data or []
    if not rows:
        print("\nNo officers registered in 'admin_users' yet.\n")
        return
    print(f"\nRegistered Officers ({len(rows)}):")
    print("-" * 75)
    print(f"{'Role':<15} {'Full Name':<25} {'Email':<30}")
    print("-" * 75)
    for r in rows:
        role = (r.get("role") or "").upper()
        name = r.get("full_name") or "-"
        email = r.get("email") or "-"
        print(f"{role:<15} {name:<25} {email:<30}")
    print("-" * 75 + "\n")


def create_or_update_officer(email: str, password: str, name: str, role: str):
    client = get_supabase_admin()
    email = email.strip()
    name = name.strip()
    role = role.strip().lower()

    if role not in ("reviewer", "administrator"):
        print(f"Error: Invalid role '{role}'. Must be 'reviewer' or 'administrator'.")
        sys.exit(1)

    if len(password) < 6:
        print("Error: Password must be at least 6 characters.")
        sys.exit(1)

    print(f"\nCreating officer account for '{email}' ({name}) with role '{role}'...")

    user_id = None

    # 1. Try to create user in Supabase Auth via admin API
    try:
        auth_res = client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": name},
        })
        if auth_res and hasattr(auth_res, "user") and auth_res.user:
            user_id = str(auth_res.user.id)
            print(f"[OK] Created auth user in Supabase Auth (UID: {user_id})")
    except Exception as e:
        err_str = str(e)
        # If user already exists in auth.users, update password
        if "already" in err_str.lower() or "exists" in err_str.lower():
            print("Notice: Auth user already exists in Supabase. Looking up user ID...")
            try:
                users_list = client.auth.admin.list_users()
                for u in users_list:
                    if u.email and u.email.lower() == email.lower():
                        user_id = str(u.id)
                        break
                if user_id:
                    # Update password
                    client.auth.admin.update_user_by_id(user_id, {
                        "password": password,
                        "user_metadata": {"full_name": name},
                    })
                    print(f"[OK] Updated existing Auth user password and metadata (UID: {user_id})")
            except Exception as lookup_err:
                print(f"Warning: Could not update Auth user directly: {lookup_err}")
        else:
            print(f"Auth creation notice: {err_str}")

    # Fallback: if user_id not found via admin API, check if admin_users already has this email
    if not user_id:
        existing = client.table("admin_users").select("id").eq("email", email).execute()
        if existing.data and len(existing.data) > 0:
            user_id = existing.data[0]["id"]
        else:
            import uuid
            user_id = str(uuid.uuid4())

    # 2. Upsert into admin_users table
    row = {
        "id": user_id,
        "email": email,
        "full_name": name,
        "role": role,
    }

    try:
        client.table("admin_users").upsert(row).execute()
        print(f"[OK] Registered in 'admin_users' table with role '{role}'")
    except Exception as e:
        print(f"Error inserting into admin_users table: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("SUCCESS: OFFICER ACCOUNT READY!")
    print(f"   Email:    {email}")
    print(f"   Name:     {name}")
    print(f"   Role:     {role.upper()}")
    print(f"   Password: [as provided]")
    print(f"   Login at: http://localhost:8000/admin")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Create or manage AWS SBG JRU officer accounts")
    parser.add_argument("--email", help="Officer email address")
    parser.add_argument("--password", help="Officer password")
    parser.add_argument("--name", help="Officer full name")
    parser.add_argument("--role", default="administrator", choices=["reviewer", "administrator"], help="Officer role (default: administrator)")
    parser.add_argument("--list", action="store_true", help="List all registered officers")

    args = parser.parse_args()
    client = get_supabase_admin()

    if args.list:
        list_officers(client)
        return

    email = args.email
    password = args.password
    name = args.name
    role = args.role

    # Interactive mode if arguments are omitted
    if not email:
        print("=== AWS SBG JRU - Create Officer Account ===")
        email = input("Officer Email: ").strip()
        if not email:
            print("Email is required.")
            return

    if not name:
        name = input("Officer Full Name: ").strip()
        if not name:
            name = email.split("@")[0].title()

    if not password:
        password = input("Password (min 6 chars): ").strip()
        if len(password) < 6:
            print("Password must be at least 6 characters.")
            return

    if not args.email:  # only prompt role if running interactively
        role_input = input("Role (1: administrator, 2: reviewer) [default: 1]: ").strip()
        if role_input == "2":
            role = "reviewer"
        else:
            role = "administrator"

    create_or_update_officer(email, password, name, role)


if __name__ == "__main__":
    main()

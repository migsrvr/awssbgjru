from typing import Optional
from supabase import create_client, Client

from backend.api.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY

supabase: Optional[Client] = None
supabase_admin: Optional[Client] = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize standard Supabase client: {e}")

admin_key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
if SUPABASE_URL and admin_key:
    try:
        supabase_admin = create_client(SUPABASE_URL, admin_key)
    except Exception as e:
        print(f"Warning: Failed to initialize admin Supabase client: {e}")


def get_supabase_admin() -> Client:
    """Returns the privileged admin client, falling back to standard client."""
    client = supabase_admin or supabase
    if client is None:
        raise RuntimeError(
            "Supabase client not initialized. Ensure SUPABASE_URL and SUPABASE_KEY or SUPABASE_SERVICE_ROLE_KEY are set."
        )
    return client


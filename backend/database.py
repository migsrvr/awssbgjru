import threading
from typing import Optional
from supabase import create_client, Client

from backend.api.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY

supabase: Optional[Client] = None
supabase_admin: Optional[Client] = None
_admin_client_lock = threading.Lock()

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
    """Returns the cached privileged admin client initialized with the service-role key."""
    global supabase_admin
    if supabase_admin is not None:
        return supabase_admin

    with _admin_client_lock:
        if supabase_admin is not None:
            return supabase_admin
        key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
        if not SUPABASE_URL or not key:
            raise RuntimeError(
                "Supabase client not initialized. Ensure SUPABASE_URL and SUPABASE_KEY or SUPABASE_SERVICE_ROLE_KEY are set."
            )
        supabase_admin = create_client(SUPABASE_URL, key)
        return supabase_admin


def get_supabase_auth_client() -> Client:
    """Returns a client for standard user authentication operations."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase client not initialized.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)



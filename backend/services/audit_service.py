import datetime
from typing import Optional, Dict, Any
from backend.database import get_supabase_admin


def log_action(
    actor_id: Optional[str],
    actor_name: Optional[str],
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Records an operational event in the `audit_logs` table.
    Fails safely without breaking caller execution.
    """
    row = {
        "actor_id": actor_id or "system",
        "actor_name": actor_name or "System",
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id is not None else None,
        "details": details or {},
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    print(f"[AUDIT] {row['actor_name']} ({row['actor_id']}) -> {action} on {target_type}:{target_id}")
    try:
        client = get_supabase_admin()
        client.table("audit_logs").insert(row).execute()
    except Exception as e:
        print(f"Warning: Failed to persist audit log to Supabase: {e}")

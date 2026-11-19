import copy
import datetime
import threading
import time
from typing import Any, Dict, Optional

from backend.database import get_supabase_admin

SYNC_SCOPES = ("applications", "settings", "templates", "audit")
REMOTE_CHECK_INTERVAL_SECONDS = 12.0

_LOCK = threading.Lock()
_LAST_REMOTE_SYNC = 0.0
_STATE: Dict[str, Any] = {
    "version": 1,
    "scopes": {scope: 1 for scope in SYNC_SCOPES},
    "last_event": None,
    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}


def reset_sync_state_for_tests() -> None:
    global _LAST_REMOTE_SYNC
    with _LOCK:
        _LAST_REMOTE_SYNC = 0.0
        _STATE["version"] = 1
        _STATE["scopes"] = {scope: 1 for scope in SYNC_SCOPES}
        _STATE["last_event"] = None
        _STATE["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()


def _persist_state_async(snapshot: Dict[str, Any]) -> None:
    def _worker() -> None:
        try:
            client = get_supabase_admin()
            client.table("system_settings").upsert({
                "key": "sync_state",
                "value": snapshot,
                "updated_at": snapshot["updated_at"],
                "updated_by": "sync_service",
            }).execute()
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _merge_remote_if_newer(remote: Dict[str, Any]) -> None:
    if not isinstance(remote, dict):
        return
    remote_version = remote.get("version")
    remote_updated = str(remote.get("updated_at") or "")
    local_updated = str(_STATE.get("updated_at") or "")
    if not isinstance(remote_version, int):
        return

    if remote_version > _STATE["version"] or (
        remote_updated > local_updated and remote_version >= _STATE["version"]
    ):
        _STATE["version"] = max(_STATE["version"], remote_version)
        remote_scopes = remote.get("scopes")
        if isinstance(remote_scopes, dict):
            for scope in SYNC_SCOPES:
                val = remote_scopes.get(scope)
                if isinstance(val, int) and val > _STATE["scopes"][scope]:
                    _STATE["scopes"][scope] = val
        if remote.get("last_event"):
            _STATE["last_event"] = remote["last_event"]
        if remote_updated > local_updated:
            _STATE["updated_at"] = remote_updated


def _refresh_from_remote_if_stale() -> None:
    global _LAST_REMOTE_SYNC
    now = time.monotonic()
    with _LOCK:
        if now - _LAST_REMOTE_SYNC < REMOTE_CHECK_INTERVAL_SECONDS:
            return
        _LAST_REMOTE_SYNC = now

    try:
        client = get_supabase_admin()
        res = (
            client.table("system_settings")
            .select("value")
            .eq("key", "sync_state")
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            remote_val = res.data[0].get("value")
            with _LOCK:
                _merge_remote_if_newer(remote_val)
    except Exception:
        pass


def get_sync_state(sync_remote: bool = True) -> Dict[str, Any]:
    """Returns current monotonic sync version and per-scope versions."""
    if sync_remote:
        _refresh_from_remote_if_stale()
    with _LOCK:
        return copy.deepcopy(_STATE)


def bump_sync_version(
    scope: str = "all",
    event: Optional[str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Bumps global and scoped sync versions after any POST/PUT state mutation."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _LOCK:
        _STATE["version"] += 1
        if scope == "all":
            for s in SYNC_SCOPES:
                _STATE["scopes"][s] += 1
        else:
            if scope in _STATE["scopes"]:
                _STATE["scopes"][scope] += 1
            if scope != "audit":
                _STATE["scopes"]["audit"] += 1
        if event:
            _STATE["last_event"] = event
        _STATE["updated_at"] = now_iso
        snapshot = copy.deepcopy(_STATE)

    if persist:
        _persist_state_async(snapshot)
    return snapshot

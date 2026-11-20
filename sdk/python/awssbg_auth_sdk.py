"""
AWS SBG JRU — Centralized Member Validation SDK (Python 3.9+)
Zero-dependency plug-and-play client using Python standard library `urllib.request`.

Usage:
    from awssbg_auth_sdk import AwsSbgAuthClient

    client = AwsSbgAuthClient(
        base_url=os.getenv("AWSSBG_API_URL", "https://awssbgjru.me"),
        api_key=os.environ["AWSSBG_API_KEY"],
    )
    res = client.validate_member(
        org_id="AWSSBG-1120-001",
        username="j.delacruz482",
        password="member-password",
    )
    if res["valid"]:
        print("Authenticated:", res["member"]["full_name"])
"""

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional


class AwsSbgAuthError(Exception):
    def __init__(self, message: str, status_code: int = 0, payload: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AwsSbgAuthClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://awssbgjru.me",
        timeout_sec: float = 10.0,
        urlopen_impl: Optional[Callable[..., Any]] = None,
    ):
        if not api_key or not str(api_key).strip():
            raise AwsSbgAuthError("AwsSbgAuthClient requires a non-empty `api_key`.")
        self.api_key = str(api_key).strip()
        self.base_url = str(base_url or "https://awssbgjru.me").rstrip("/")
        self.timeout_sec = timeout_sec
        self._urlopen = urlopen_impl or urllib.request.urlopen

    def validate_member(self, org_id: str, username: str, password: str) -> Dict[str, Any]:
        """
        Validates a member's (org_id, username, password) against the centralized AWS SBG JRU DB.
        Returns a dict: {"valid": bool, "reason": Optional[str], "member": Optional[dict]}.
        """
        if not org_id or not username or not password:
            raise AwsSbgAuthError("org_id, username, and password are all required.")

        url = f"{self.base_url}/api/v1/external/validate"
        body_bytes = json.dumps({
            "org_id": str(org_id).strip(),
            "username": str(username).strip(),
            "password": str(password),
        }).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            data=body_bytes,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-API-Key": self.api_key,
            },
        )

        try:
            with self._urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                return {
                    "valid": bool(data.get("valid")),
                    "reason": data.get("reason"),
                    "member": data.get("member"),
                }
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
                parsed = json.loads(err_body)
            except Exception:
                parsed = {"detail": err_body or str(e)}
            detail = parsed.get("detail") if isinstance(parsed, dict) else str(parsed)
            raise AwsSbgAuthError(
                f"AWS SBG validation API error: {detail}",
                status_code=e.code,
                payload=parsed,
            ) from e

    def check_health(self) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/external/health"
        req = urllib.request.Request(url=url, method="GET", headers={"Accept": "application/json"})
        with self._urlopen(req, timeout=self.timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))

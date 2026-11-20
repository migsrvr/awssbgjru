import io
import json
import urllib.error
import pytest

from sdk.python.awssbg_auth_sdk import AwsSbgAuthClient, AwsSbgAuthError


class DummyResponse:
    def __init__(self, payload: dict):
        self._bytes = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def test_python_sdk_requires_api_key():
    with pytest.raises(AwsSbgAuthError):
        AwsSbgAuthClient(api_key="")


def test_python_sdk_validate_member_success():
    captured = {}

    def fake_urlopen(req, timeout=10.0):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return DummyResponse({
            "valid": True,
            "reason": None,
            "member": {
                "org_id": "AWSSBG-1120-001",
                "username": "j.delacruz482",
                "full_name": "Juan Dela Cruz",
            },
        })

    client = AwsSbgAuthClient(
        api_key="sbg_live_pykey",
        base_url="https://awssbgjru.me/",
        urlopen_impl=fake_urlopen,
    )
    res = client.validate_member("AWSSBG-1120-001", "j.delacruz482", "Secret!23")
    assert captured["url"] == "https://awssbgjru.me/api/v1/external/validate"
    assert captured["method"] == "POST"
    assert captured["headers"].get("X-api-key") == "sbg_live_pykey"
    assert captured["body"] == {
        "org_id": "AWSSBG-1120-001",
        "username": "j.delacruz482",
        "password": "Secret!23",
    }
    assert res["valid"] is True
    assert res["member"]["full_name"] == "Juan Dela Cruz"


def test_python_sdk_handles_http_401():
    def fake_urlopen_401(req, timeout=10.0):
        fp = io.BytesIO(json.dumps({"detail": "Invalid API key"}).encode("utf-8"))
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, fp)

    client = AwsSbgAuthClient(
        api_key="sbg_live_bad",
        urlopen_impl=fake_urlopen_401,
    )
    with pytest.raises(AwsSbgAuthError) as exc_info:
        client.validate_member("AWSSBG-1120-001", "j.delacruz482", "pw")
    assert exc_info.value.status_code == 401

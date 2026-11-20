import threading
from typing import Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Request, Response

from backend.api.rate_limiter import RateLimiter
from backend.schemas.portal_members import (
    ExternalValidateRequest,
    ExternalValidateResponse,
)
from backend.services.member_portal_service import (
    authenticate_api_key,
    record_rate_limited_attempt,
    validate_member_credentials,
)

router = APIRouter(prefix="/api/v1/external", tags=["external-validation"])

_KEY_LIMITERS: Dict[str, RateLimiter] = {}
_KEY_LIMITERS_LOCK = threading.Lock()


def _check_key_rate_limit(key_id: str, rate_limit_per_min: int) -> bool:
    with _KEY_LIMITERS_LOCK:
        limiter = _KEY_LIMITERS.get(key_id)
        if limiter is None or getattr(limiter, "requests", None) != rate_limit_per_min:
            limiter = RateLimiter(requests=rate_limit_per_min, window=60)
            _KEY_LIMITERS[key_id] = limiter
    return limiter.is_allowed(key_id)


@router.get("/health")
def external_health():
    """Public health check for external systems and SDKs."""
    return {
        "status": "ok",
        "service": "awssbgjru-centralized-member-validation-api",
        "version": "1.0.0",
    }


@router.post("/validate", response_model=ExternalValidateResponse)
def validate_member_endpoint(
    payload: ExternalValidateRequest,
    request: Request,
    response: Response,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Strictly read-only endpoint that verifies a member's (org_id, username, password)
    against the centralized AWS SBG JRU database without granting direct DB access.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    api_key_row = authenticate_api_key(x_api_key)

    client_ip = request.client.host if request.client else "unknown"
    key_id = str(api_key_row.get("id"))
    rate_limit = int(api_key_row.get("rate_limit_per_min") or 60)

    if not _check_key_rate_limit(key_id, rate_limit):
        record_rate_limited_attempt(
            api_key_row=api_key_row,
            org_id=payload.org_id,
            username=payload.username,
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({rate_limit} requests/minute). Please retry shortly.",
        )

    return validate_member_credentials(
        org_id=payload.org_id,
        username=payload.username,
        password=payload.password,
        api_key_row=api_key_row,
        client_ip=client_ip,
    )


@router.get("/openapi.json")
def external_scoped_openapi():
    """
    Scoped OpenAPI 3.1 specification containing ONLY external validation endpoints
    so AI coding agents and SDK generators can inspect the contract without exposing internal admin routes.
    """
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "AWS SBG JRU Centralized Member Validation API",
            "version": "1.0.0",
            "description": (
                "Read-only external credential validation API for official AWS Student Builder Group – "
                "JRU Chapter portals and applications. Authenticate all requests with the `X-API-Key` header."
            ),
        },
        "paths": {
            "/api/v1/external/health": {
                "get": {
                    "operationId": "externalHealth",
                    "summary": "Check External Validation API health",
                    "responses": {
                        "200": {
                            "description": "Service is healthy",
                        }
                    },
                }
            },
            "/api/v1/external/validate": {
                "post": {
                    "operationId": "validateMemberCredentials",
                    "summary": "Validate member Org ID, Username, and Password (read-only)",
                    "parameters": [
                        {
                            "name": "X-API-Key",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Executive-issued API key (e.g. sbg_live_...)",
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["org_id", "username", "password"],
                                    "properties": {
                                        "org_id": {
                                            "type": "string",
                                            "example": "AWSSBG-1120-001",
                                        },
                                        "username": {
                                            "type": "string",
                                            "example": "j.delacruz482",
                                        },
                                        "password": {
                                            "type": "string",
                                            "example": "MemberPassword123!",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Validation result (valid=true with safe member profile, or valid=false with reason)",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["valid"],
                                        "properties": {
                                            "valid": {"type": "boolean"},
                                            "reason": {
                                                "type": ["string", "null"],
                                                "enum": ["invalid_credentials", "inactive_member", None],
                                            },
                                            "member": {
                                                "type": ["object", "null"],
                                                "properties": {
                                                    "org_id": {"type": "string"},
                                                    "username": {"type": "string"},
                                                    "first_name": {"type": "string"},
                                                    "last_name": {"type": "string"},
                                                    "full_name": {"type": "string"},
                                                    "email": {"type": "string"},
                                                    "student_id": {"type": ["string", "null"]},
                                                    "year": {"type": ["string", "null"]},
                                                    "program": {"type": ["string", "null"]},
                                                    "division_type": {"type": ["string", "null"]},
                                                    "division_name": {"type": ["string", "null"]},
                                                    "status": {"type": "string"},
                                                    "must_change_password": {"type": "boolean"},
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Missing, invalid, or revoked X-API-Key"},
                        "429": {"description": "Per-key rate limit exceeded"},
                    },
                }
            },
        },
    }

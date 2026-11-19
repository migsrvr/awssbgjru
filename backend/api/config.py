import os
from pathlib import Path

from dotenv import load_dotenv

# Check both backend/api/.env and root .env
env_paths = [Path(__file__).parent / ".env", Path(__file__).parent.parent.parent / ".env"]
for p in env_paths:
    if p.exists():
        load_dotenv(p)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_EVAL_MODEL = os.getenv("GROQ_EVAL_MODEL", "openai/gpt-oss-120b")
GROQ_EVAL_FALLBACK_MODELS = (
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
)
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# App URL for emails and links
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

DEFAULT_ALLOWED_ORIGINS = (
    "https://awssbgjru.me",
    "https://www.awssbgjru.me",
    "https://awslearningclub.jru",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
)


def parse_allowed_origins(raw_origins: str = "", app_base_url: str = APP_BASE_URL) -> list[str]:
    origins: list[str] = []
    candidates = [
        *(item.strip().rstrip("/") for item in (raw_origins or "").split(",") if item.strip()),
        (app_base_url or "").strip().rstrip("/"),
        *DEFAULT_ALLOWED_ORIGINS,
    ]
    for origin in candidates:
        if origin and origin not in origins:
            origins.append(origin)
    return origins


ALLOWED_ORIGINS = parse_allowed_origins(os.getenv("ALLOWED_ORIGINS", ""), APP_BASE_URL)

# Valid registration divisions (must match frontend pill options)
VALID_DIVISIONS = {
    "office": {
        "Relations", "Operations", "Creatives", "Marketing", "Media",
    },
    "skillbuilder": {
        "Software Development", "Web Development", "UI/UX", "Data Analyst",
        "Cloud Computing", "Machine Learning & AI",
    },
}

# Email
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")


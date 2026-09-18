import os
from pathlib import Path

from dotenv import load_dotenv

# Check both backend/api/.env and root .env
env_paths = [Path(__file__).parent / ".env", Path(__file__).parent.parent.parent / ".env"]
for p in env_paths:
    if p.exists():
        load_dotenv(p)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# App URL for emails and links
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# Email
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")


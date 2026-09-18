import json
import sys
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# Ensure the api/ directory is on sys.path so relative imports (import config) resolve
_api_dir = os.path.join(os.path.dirname(__file__), "api")
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

from backend.api.chatbot import generate
from backend.api.config import GROQ_MODEL
from backend.api.rate_limiter import RateLimiter
from backend.api.cache import TTLCache
from backend.routers.registration import router as registration_router
from backend.routers.admin import router as admin_router
from backend.routers.revision import router as revision_router

app = FastAPI(title="AWS Student Builder Group - JRU API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:8001", "http://localhost:8080", "http://localhost:8081", "http://127.0.0.1:8000", "http://127.0.0.1:8001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(registration_router)
app.include_router(admin_router)
app.include_router(revision_router)


limiter = RateLimiter()
response_cache = TTLCache()


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()

    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"

    if not limiter.is_allowed(client_ip):
        return JSONResponse(
            {"error": "Rate limit exceeded. Please wait before sending another message."},
            status_code=429,
        )

    cache_key = message.lower().strip()
    cached = response_cache.get(cache_key)
    if cached is not None:

        async def cached_stream():
            yield f"data: {json.dumps({'token': cached})}\n\n"
            yield f"data: {json.dumps({'token': '[DONE]'})}\n\n"

        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    async def stream():
        full_response = ""
        for chunk in generate(message):
            if "error" in chunk:
                yield f"data: {json.dumps(chunk)}\n\n"
                return
            token = chunk.get("token", "")
            if token == "[DONE]":
                response_cache.set(cache_key, full_response)
                yield f"data: {json.dumps(chunk)}\n\n"
                return
            full_response += token
            yield f"data: {json.dumps({'token': token})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": GROQ_MODEL}

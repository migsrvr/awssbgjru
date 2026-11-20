# Design Specification: EC2 Docker Compose Migration (`awssbgjru.me`)

- **Date:** 2026-11-19
- **Status:** Approved
- **Target Domain:** `https://awssbgjru.me` (with `www.awssbgjru.me` -> `https://awssbgjru.me` 301 redirect)
- **Target Infrastructure:** AWS EC2 `t3.micro` (`ap-southeast-1`, Ubuntu 24.04 LTS, 25 GB `gp3` EBS, 2 GB swap, 1 Elastic IP)

## 1. Context & Goals
Migrate the AWS Student Builder Group — José Rizal University website and FastAPI backend from Vercel serverless functions to an AWS EC2 instance running Docker Compose, while preserving Vercel compatibility during cutover and keeping 12-month operating costs within AWS Free Tier + $300 USD credits.

## 2. Architecture & Component Boundaries
1. **`web` container (`Dockerfile.web` / `caddy:2-alpine`)**:
   - Serves static assets from `/srv/frontend`.
   - Implements all clean-URL rewrites from `vercel.json` (`/`, 17 page slugs with optional `.html`, `/sitemap.xml`, `/robots.txt`, and `404.html` fallback).
   - Terminates TLS automatically via Let's Encrypt for `awssbgjru.me` and redirects `www.awssbgjru.me`.
   - Reverse-proxies `/api/chat` with `flush_interval -1` (unbuffered SSE streaming) and `/api/*` with a `90s` read timeout (for Groq AI ATS resume evaluations).
2. **`backend` container (`Dockerfile.backend` / `python:3.12-slim`)**:
   - Uses lightweight production dependencies (`backend/requirements-docker.txt`) including `pypdf>=4.0.0` for AI ATS resume evaluation while excluding `sentence-transformers` and `faiss-cpu`.
   - Includes `frontend/assets/` at `/app/frontend/assets/` so `backend/services/email_service.py` can inline banner and QR PNGs as MIME `cid:` attachments.
   - Runs a single async Uvicorn worker (`--workers 1 --proxy-headers --forwarded-allow-ips *`) so in-memory `sync_service.py`, `RateLimiter`, and `TTLCache` remain consistent across requests.
3. **CI/CD (`.github/workflows/ci.yml` & `.github/workflows/deploy.yml`)**:
   - `ci.yml`: Runs Python unit tests, Node tests, and Docker build validation on PRs and pushes to `dev`.
   - `deploy.yml`: Builds and pushes images to `ghcr.io` (using dynamic `${{ github.repository }}` naming so transferring to a GitHub Organization requires zero workflow edits) and deploys to EC2 over SSH on merges to `main`.

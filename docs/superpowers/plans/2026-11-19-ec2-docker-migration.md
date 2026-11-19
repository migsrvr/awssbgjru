# Implementation Plan: EC2 Docker Compose Migration (`awssbgjru.me`)

- **Date:** 2026-11-19
- **Spec:** `docs/superpowers/specs/2026-11-19-ec2-docker-migration-design.md`

## Task Breakdown & Ownership Matrix

1. **Task 1 — TDD Tests (`backend/tests/test_ec2_deployment.py`)**:
   - Write failing tests covering `ALLOWED_ORIGINS` parsing, production CORS headers for `https://awssbgjru.me`, lightweight `backend/requirements-docker.txt` contents, Dockerfiles (`frontend/assets` inclusion, `--workers 1`, `--proxy-headers`), Caddyfile (`flush_interval -1`, `90s` timeout, clean URLs), Compose files, and GitHub Actions workflows.
2. **Task 2 — Backend CORS & Lightweight Dependencies**:
   - Modify `backend/api/config.py`, `backend/main.py`, `backend/api/.env.example`.
   - Create `backend/requirements-docker.txt`.
3. **Task 3 — Docker & Caddy Configuration**:
   - Create `.dockerignore`, `Dockerfile.backend`, `Dockerfile.web`, `deploy/Caddyfile`, `docker-compose.yml`, `docker-compose.prod.yml`.
4. **Task 4 — GitHub Actions CI/CD & EC2 Runbook**:
   - Create `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`, and `docs/ec2-migration-runbook.md`.
5. **Task 5 — Full Verification**:
   - Run all Python tests, Node tests, and `docker compose config` validation.

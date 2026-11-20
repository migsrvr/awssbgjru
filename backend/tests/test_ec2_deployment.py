import os
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestEC2DeploymentConfig(unittest.TestCase):
    def test_allowed_origins_includes_production_domain_by_default(self):
        import backend.api.config as config

        self.assertTrue(hasattr(config, "ALLOWED_ORIGINS"), "config.ALLOWED_ORIGINS must be defined")
        self.assertIn("https://awssbgjru.me", config.ALLOWED_ORIGINS)
        self.assertIn("https://www.awssbgjru.me", config.ALLOWED_ORIGINS)
        self.assertIn("http://localhost:8000", config.ALLOWED_ORIGINS)

    def test_parse_allowed_origins_supports_custom_env(self):
        import backend.api.config as config

        self.assertTrue(
            hasattr(config, "parse_allowed_origins"),
            "config.parse_allowed_origins helper must be defined",
        )
        origins = config.parse_allowed_origins(
            "https://staging.awssbgjru.me, https://custom.example.com ",
            app_base_url="https://awssbgjru.me",
        )
        self.assertIn("https://staging.awssbgjru.me", origins)
        self.assertIn("https://custom.example.com", origins)
        self.assertIn("https://awssbgjru.me", origins)

    def test_cors_allows_production_domain_on_main_app(self):
        from backend.main import app

        client = TestClient(app)
        res = client.options(
            "/api/health",
            headers={
                "Origin": "https://awssbgjru.me",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), "https://awssbgjru.me")

    def test_lightweight_docker_requirements_file(self):
        req_file = PROJECT_ROOT / "backend" / "requirements-docker.txt"
        self.assertTrue(req_file.exists(), "backend/requirements-docker.txt must exist")
        content = req_file.read_text(encoding="utf-8")
        for pkg in ("fastapi", "uvicorn", "groq", "python-dotenv", "httpx", "supabase", "pydantic", "pypdf"):
            self.assertIn(pkg, content, f"{pkg} must be in backend/requirements-docker.txt")
        for heavy_pkg in ("sentence-transformers", "faiss-cpu"):
            self.assertNotIn(heavy_pkg, content, f"{heavy_pkg} must not be in lightweight requirements")

    def test_dockerfile_backend_invariants(self):
        dockerfile = PROJECT_ROOT / "Dockerfile.backend"
        self.assertTrue(dockerfile.exists(), "Dockerfile.backend must exist")
        content = dockerfile.read_text(encoding="utf-8")
        self.assertIn("requirements-docker.txt", content)
        self.assertIn("frontend/assets", content, "Dockerfile.backend must copy frontend/assets for email CIDs")
        self.assertIn("--workers", content)
        self.assertIn('"1"', content, "Must use single worker for in-memory sync_service consistency")
        self.assertIn("--proxy-headers", content)
        self.assertIn("HEALTHCHECK", content)

    def test_caddyfile_routing_and_streaming_invariants(self):
        caddyfile = PROJECT_ROOT / "deploy" / "Caddyfile"
        self.assertTrue(caddyfile.exists(), "deploy/Caddyfile must exist")
        content = caddyfile.read_text(encoding="utf-8")
        self.assertIn("flush_interval -1", content, "SSE /api/chat must disable proxy buffering")
        self.assertIn("read_timeout 90s", content, "AI ATS evaluation requires 90s proxy read timeout")
        self.assertIn("/sitemap.xml", content)
        self.assertIn("/robots.txt", content)
        self.assertIn("/pages/landing-page.html", content)
        self.assertIn("404.html", content)
        for page in ("register", "explanation", "department", "office", "skillbuilder", "admin", "revision", "events"):
            self.assertIn(page, content)

    def test_compose_and_cicd_files_exist(self):
        required_files = [
            PROJECT_ROOT / "Dockerfile.web",
            PROJECT_ROOT / "docker-compose.yml",
            PROJECT_ROOT / "docker-compose.prod.yml",
            PROJECT_ROOT / ".dockerignore",
            PROJECT_ROOT / ".github" / "workflows" / "ci.yml",
            PROJECT_ROOT / ".github" / "workflows" / "deploy.yml",
            PROJECT_ROOT / "docs" / "ec2-migration-runbook.md",
        ]
        for path in required_files:
            self.assertTrue(path.exists(), f"Expected file {path.relative_to(PROJECT_ROOT)} to exist")


if __name__ == "__main__":
    unittest.main()

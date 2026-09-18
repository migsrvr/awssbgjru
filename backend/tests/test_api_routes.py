import unittest
from fastapi.testclient import TestClient

from backend.main import app


class TestAdminApiRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")

    def test_registration_status_endpoint(self):
        res = self.client.get("/api/v1/revision/status/registration")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("is_open", data)
        self.assertIn("message", data)

    def test_admin_me_requires_auth(self):
        res = self.client.get("/api/v1/admin/me")
        # Without auth header, must reject
        self.assertEqual(res.status_code, 401)

    def test_admin_me_with_dev_token(self):
        headers = {"Authorization": "Bearer dev-admin-token"}
        res = self.client.get("/api/v1/admin/me", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("role"), "administrator")
        self.assertEqual(data.get("email"), "dev.officer@awssbgjru.local")

    def test_admin_settings_endpoint(self):
        headers = {"Authorization": "Bearer dev-admin-token"}
        res = self.client.get("/api/v1/admin/settings", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("registration_open", data)
        self.assertIn("qualification_rubric", data)

    def test_admin_templates_list(self):
        headers = {"Authorization": "Bearer dev-admin-token"}
        res = self.client.get("/api/v1/admin/templates", headers=headers)
        self.assertEqual(res.status_code, 200)
        templates = res.json()
        self.assertIsInstance(templates, list)
        self.assertGreaterEqual(len(templates), 5)
        template_ids = [t["id"] for t in templates]
        self.assertIn("approved", template_ids)
        self.assertIn("revision_requested", template_ids)
        self.assertIn("declined", template_ids)


if __name__ == "__main__":
    unittest.main()

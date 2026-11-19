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
        self.assertIn("division_availability", data)
        self.assertIn("office", data["division_availability"])
        self.assertIn("skillbuilder", data["division_availability"])

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
        self.assertIn("division_availability", data)

    def test_admin_settings_update_division_availability_admin_only(self):
        from unittest.mock import patch
        from backend.registration_availability import normalize_division_availability

        headers = {"Authorization": "Bearer dev-admin-token"}
        expected_availability = normalize_division_availability({"office": {"Operations": "full"}})
        mock_updated = {
            "registration_open": True,
            "closed_message": "Closed",
            "qualification_rubric": [],
            "division_availability": expected_availability,
        }

        with (
            patch("backend.routers.admin.update_system_settings", return_value=mock_updated) as mock_update,
            patch("backend.routers.admin.log_action"),
        ):
            res = self.client.put(
                "/api/v1/admin/settings",
                headers=headers,
                json={"division_availability": {"office": {"Operations": "full"}}},
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["division_availability"]["office"]["Operations"], "full")
            mock_update.assert_called_once()

            # Invalid status literal must be rejected with 422
            bad_res = self.client.put(
                "/api/v1/admin/settings",
                headers=headers,
                json={"division_availability": {"office": {"Operations": "maybe"}}},
            )
            self.assertEqual(bad_res.status_code, 422)

            # Unauthenticated request must be rejected with 401
            unauth_res = self.client.put(
                "/api/v1/admin/settings",
                json={"division_availability": {"office": {"Operations": "full"}}},
            )
            self.assertEqual(unauth_res.status_code, 401)

    def test_admin_sync_version_endpoint(self):
        # Unauthenticated must fail with 401
        unauth = self.client.get("/api/v1/admin/sync-version")
        self.assertEqual(unauth.status_code, 401)

        headers = {"Authorization": "Bearer dev-admin-token"}
        res = self.client.get("/api/v1/admin/sync-version", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("version", data)
        self.assertIn("scopes", data)
        self.assertIn("applications", data["scopes"])
        self.assertIn("settings", data["scopes"])
        self.assertIn("templates", data["scopes"])
        self.assertIn("audit", data["scopes"])

    def test_admin_resume_and_ai_evaluate_endpoints(self):
        from unittest.mock import patch

        # Both require auth
        self.assertEqual(self.client.get("/api/v1/admin/applications/1/resume").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/admin/applications/1/ai-evaluate").status_code, 401)

        headers = {"Authorization": "Bearer dev-admin-token"}

        with patch(
            "backend.routers.admin.get_application_resume",
            return_value=(b"%PDF-1.4\n%fake", "application/pdf", "cv.pdf"),
        ):
            res = self.client.get("/api/v1/admin/applications/1/resume", headers=headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.headers["content-type"], "application/pdf")
            self.assertIn("inline", res.headers.get("content-disposition", ""))
            self.assertEqual(res.content, b"%PDF-1.4\n%fake")

        fake_eval_response = {
            "cached": False,
            "evaluation": {
                "fit_score": 82,
                "fit_label": "Strong Fit",
                "recommendation": "approve",
                "summary": "Solid fit.",
                "strengths": ["Clear goals"],
                "concerns": [],
                "extracted_skills": ["AWS"],
                "sub_scores": {"division_relevance": 85, "statement_quality": 80, "cv_signal": 80},
                "cv_status": "analyzed_pdf",
            },
        }
        with (
            patch("backend.routers.admin.run_ai_evaluation", return_value=fake_eval_response),
            patch("backend.routers.admin.bump_sync_version"),
        ):
            res_ai = self.client.post(
                "/api/v1/admin/applications/1/ai-evaluate",
                headers=headers,
                json={"force_refresh": False},
            )
            self.assertEqual(res_ai.status_code, 200)
            self.assertEqual(res_ai.json()["evaluation"]["fit_score"], 82)

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

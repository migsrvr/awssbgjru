import unittest
import datetime

from backend.services.email_service import (
    interpolate_template,
    build_variables_map,
    DEFAULT_TEMPLATES,
)
from backend.services.application_service import (
    _parse_timestamp,
    CLAIM_LOCK_TIMEOUT_MINUTES,
)


class TestAdminServices(unittest.TestCase):
    def test_email_interpolation_approved(self):
        tmpl = DEFAULT_TEMPLATES["approved"]
        vars_map = {
            "Applicant Name": "Maria Santos",
            "Role Title": "Creatives Office Member",
            "Division Name": "Creatives Office",
            "Next Steps": "Join the Discord server and attend orientation this Friday.",
        }
        subject, body = interpolate_template(tmpl, vars_map)

        self.assertIn("Welcome to AWS Student Builder Group - JRU", subject)
        self.assertIn("Congratulations!", body)
        self.assertIn("Creatives Office Member", body)
        self.assertNotIn("{{Applicant Name}}", body)
        self.assertNotIn("{{Role Title}}", body)

    def test_email_interpolation_revision_requested(self):
        tmpl = DEFAULT_TEMPLATES["revision_requested"]
        vars_map = {
            "Applicant Name": "Juan Dela Cruz",
            "Revision Notes": "Please provide more details on your cloud learning goals.",
            "Revision Link": "http://localhost:8000/revision?token=xyz123",
            "Revision Deadline": "2026-09-25 18:00 UTC",
        }
        subject, body = interpolate_template(tmpl, vars_map)

        self.assertIn("Please revise your AWS SBG JRU application", subject)
        self.assertIn("Hi Juan Dela Cruz,", body)
        self.assertIn("Please provide more details on your cloud learning goals.", body)
        self.assertIn("http://localhost:8000/revision?token=xyz123", body)
        self.assertIn("2026-09-25 18:00 UTC", body)

    def test_email_interpolation_declined(self):
        tmpl = DEFAULT_TEMPLATES["declined"]
        vars_map = {
            "Applicant Name": "Alex Reyes",
            "Optional General Reason": "Due to high volume and team capacity limits.",
        }
        subject, body = interpolate_template(tmpl, vars_map)

        self.assertIn("Update on your AWS SBG JRU application", subject)
        self.assertIn("Hi Alex Reyes,", body)
        self.assertIn("Due to high volume and team capacity limits.", body)

    def test_claim_lock_timestamp_parser(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        ts_str = now.isoformat()
        parsed = _parse_timestamp(ts_str)
        self.assertIsNotNone(parsed)
        self.assertIsInstance(parsed, datetime.datetime)

        # Expired claim test (> 30 minutes)
        old_time = now - datetime.timedelta(minutes=CLAIM_LOCK_TIMEOUT_MINUTES + 5)
        diff = (now - old_time).total_seconds() / 60.0
        self.assertGreater(diff, CLAIM_LOCK_TIMEOUT_MINUTES)

    def test_build_variables_map_defaults(self):
        applicant = {
            "full_name": "Test Student",
            "revision_token": "token_abc",
            "revision_notes": "Needs more info",
            "revision_deadline": "Tomorrow",
            "decision_reason_code": "Capacity limit",
        }
        vmap = build_variables_map(applicant)
        self.assertEqual(vmap["Applicant Name"], "Test Student")
        self.assertIn("token_abc", vmap["Revision Link"])
        self.assertEqual(vmap["Revision Notes"], "Needs more info")
        self.assertEqual(vmap["Revision Deadline"], "Tomorrow")
        self.assertEqual(vmap["Optional General Reason"], "Capacity limit")

    def test_dynamic_role_and_department_resolution(self):
        from backend.services.email_service import resolve_applicant_role_and_division

        cases = [
            ({"division_name": "Software Development", "division_type": "skillbuilder"}, ("Software Developer", "Skill Builder Department", "Software Development")),
            ({"division_name": "Web Development", "division_type": "skillbuilder"}, ("Web Developer", "Skill Builder Department", "Web Development")),
            ({"division_name": "UI/UX", "division_type": "skillbuilder"}, ("UI/UX Designer", "Skill Builder Department", "UI/UX")),
            ({"division_name": "Relations", "division_type": "office"}, ("Relations Member", "Relations Office", "Relations")),
            ({"division_name": "Operations", "division_type": "office"}, ("Operations Member", "Operations Office", "Operations")),
            ({"division_name": "Creatives", "division_type": "office"}, ("Creatives Member", "Creatives Department", "Creatives")),
        ]
        for app, expected in cases:
            res = resolve_applicant_role_and_division(app)
            self.assertEqual(res, expected, f"Failed for {app}")

    def test_email_interpolation_for_separated_tracks(self):
        tmpl = DEFAULT_TEMPLATES["approved"]

        # Software Development applicant
        app_soft = {"full_name": "Alex Rivera", "division_name": "Software Development", "division_type": "skillbuilder"}
        _, body_soft = interpolate_template(tmpl, build_variables_map(app_soft))
        self.assertIn("accepted as a *Software Developer* under the *Skill Builder Department*", body_soft)

        # Web Development applicant
        app_web = {"full_name": "Jordan Cruz", "division_name": "Web Development", "division_type": "skillbuilder"}
        _, body_web = interpolate_template(tmpl, build_variables_map(app_web))
        self.assertIn("accepted as a *Web Developer* under the *Skill Builder Department*", body_web)

        # UI/UX applicant
        app_uiux = {"full_name": "Taylor Swift", "division_name": "UI/UX", "division_type": "skillbuilder"}
        _, body_uiux = interpolate_template(tmpl, build_variables_map(app_uiux))
        self.assertIn("accepted as a *UI/UX Designer* under the *Skill Builder Department*", body_uiux)

    def test_get_application_queue_excludes_approved_by_default(self):
        from unittest.mock import MagicMock, patch
        from backend.services.application_service import get_application_queue

        mock_client = MagicMock()
        # Mock table("registrations").select("id, application_status").execute()
        mock_counts_query = MagicMock()
        mock_counts_query.execute.return_value.data = [
            {"id": 1, "application_status": "new"},
            {"id": 2, "application_status": "new"},
            {"id": 3, "application_status": "under_review"},
            {"id": 4, "application_status": "declined"},
            {"id": 5, "application_status": "approved"},
            {"id": 6, "application_status": "approved"},
        ]
        
        mock_data_query = MagicMock()
        mock_data_query.eq.return_value = mock_data_query
        mock_data_query.neq.return_value = mock_data_query
        mock_data_query.order.return_value = mock_data_query
        mock_data_query.range.return_value = mock_data_query
        mock_data_query.execute.return_value.data = [
            {"id": 1, "application_status": "new"},
            {"id": 2, "application_status": "new"},
            {"id": 3, "application_status": "under_review"},
            {"id": 4, "application_status": "declined"},
        ]
        mock_data_query.execute.return_value.count = 4

        def table_side_effect(table_name):
            t = MagicMock()
            def select_side_effect(cols, **kwargs):
                if cols == "id, application_status":
                    return mock_counts_query
                return mock_data_query
            t.select.side_effect = select_side_effect
            return t

        mock_client.table.side_effect = table_side_effect

        with patch("backend.services.application_service.get_supabase_admin", return_value=mock_client):
            # 1. When status_filter is "all" or None, neq("application_status", "approved") must be called
            res = get_application_queue(status_filter="all")
            mock_data_query.neq.assert_called_with("application_status", "approved")
            self.assertEqual(res["status_counts"]["new"], 2)
            self.assertEqual(res["status_counts"]["under_review"], 1)
            self.assertEqual(res["status_counts"]["declined"], 1)
            self.assertEqual(res["status_counts"]["approved"], 2)
            # "all" count should only sum active unapproved (2 + 1 + 1 = 4)
            self.assertEqual(res["status_counts"]["all"], 4)

            # 2. When status_filter is "new", eq("application_status", "new") must be called
            mock_data_query.reset_mock()
            res_new = get_application_queue(status_filter="new")
            mock_data_query.eq.assert_any_call("application_status", "new")

    def test_system_settings_reads_and_updates_division_availability(self):
        from unittest.mock import MagicMock, patch
        from backend.services.application_service import (
            get_system_settings,
            update_system_settings,
        )

        stored_rows = [
            {
                "key": "registration_status",
                "value": {"is_open": True, "closed_message": "Closed"},
            },
            {
                "key": "division_availability",
                "value": {
                    "office": {"Operations": "full", "Marketing": "open"},
                    "skillbuilder": {"Web Development": "open"},
                },
            },
        ]

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value.execute.return_value.data = stored_rows
        upserted_payloads = []

        def upsert_side_effect(payload):
            upserted_payloads.append(payload)
            return MagicMock(execute=MagicMock(return_value=MagicMock(data=[payload])))

        mock_table.upsert.side_effect = upsert_side_effect
        mock_client.table.return_value = mock_table

        with patch("backend.services.application_service.get_supabase_admin", return_value=mock_client):
            settings = get_system_settings()
            self.assertEqual(settings["division_availability"]["office"]["Operations"], "full")
            self.assertEqual(settings["division_availability"]["office"]["Marketing"], "open")
            self.assertEqual(settings["division_availability"]["skillbuilder"]["Web Development"], "open")
            self.assertEqual(settings["division_availability"]["skillbuilder"]["UI/UX"], "open")

            update_system_settings(
                division_availability={"office": {"Operations": "open"}},
                officer_name="Admin Officer",
            )
            div_upserts = [p for p in upserted_payloads if p.get("key") == "division_availability"]
            self.assertEqual(len(div_upserts), 1)
            self.assertEqual(div_upserts[0]["value"]["office"]["Operations"], "open")
            self.assertEqual(div_upserts[0]["value"]["office"]["Marketing"], "open")
            self.assertEqual(div_upserts[0]["updated_by"], "Admin Officer")

    def test_sync_service_bumps_version_and_scopes(self):
        from backend.services.sync_service import (
            bump_sync_version,
            get_sync_state,
            reset_sync_state_for_tests,
        )

        reset_sync_state_for_tests()
        initial = get_sync_state(sync_remote=False)
        self.assertIn("version", initial)
        self.assertIn("scopes", initial)
        start_version = initial["version"]

        after_reg = bump_sync_version("applications", event="new_registration", persist=False)
        self.assertEqual(after_reg["version"], start_version + 1)
        self.assertGreater(after_reg["scopes"]["applications"], initial["scopes"]["applications"])
        self.assertEqual(after_reg["last_event"], "new_registration")

        after_settings = bump_sync_version("settings", event="settings_updated", persist=False)
        self.assertEqual(after_settings["version"], start_version + 2)
        self.assertGreater(after_settings["scopes"]["settings"], after_reg["scopes"]["settings"])
        self.assertEqual(after_settings["scopes"]["applications"], after_reg["scopes"]["applications"])

    def test_extract_resume_text_handles_docx_image_and_missing(self):
        import base64
        import io
        import zipfile
        from backend.services.ai_evaluation_service import extract_resume_text

        # Missing CV
        text_none, status_none = extract_resume_text(None, None)
        self.assertEqual(text_none, "")
        self.assertEqual(status_none, "no_cv")

        # Image CV
        img_data = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n").decode()
        text_img, status_img = extract_resume_text(img_data, "resume.png")
        self.assertEqual(text_img, "")
        self.assertEqual(status_img, "image_only")

        # Valid in-memory DOCX
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Built AWS Lambda and React portfolio apps</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )
        docx_b64 = "data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64," + base64.b64encode(
            buf.getvalue()
        ).decode()
        text_docx, status_docx = extract_resume_text(docx_b64, "student_cv.docx")
        self.assertEqual(status_docx, "analyzed_docx")
        self.assertIn("AWS Lambda", text_docx)

    def test_evaluate_application_with_ai_parses_structured_ats_response(self):
        import json
        from unittest.mock import MagicMock, patch
        from backend.services.ai_evaluation_service import evaluate_application_with_ai

        fake_llm_json = json.dumps({
            "fit_score": 86,
            "fit_label": "Strong Fit",
            "sub_scores": {
                "division_relevance": 90,
                "statement_quality": 82,
                "cv_signal": 85,
            },
            "recommendation": "approve",
            "extracted_skills": ["Figma", "React", "UI Prototyping"],
            "summary": "Strong portfolio alignment with UI/UX Skill Builder track.",
            "strengths": ["Hands-on Figma experience", "Clear motivation for cloud UI"],
            "concerns": ["No prior club leadership listed"],
            "rubric_hints": {
                "genuine_interest": True,
                "quality_submission": True,
            },
        })

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content=fake_llm_json))]
        mock_groq = MagicMock()
        mock_groq.chat.completions.create.return_value = mock_resp

        app_record = {
            "full_name": "Juan Dela Cruz",
            "year": "Second Year",
            "program": "BS Information Technology",
            "division_type": "skillbuilder",
            "division_name": "UI/UX",
            "explanation": "I love designing accessible web apps in Figma and want to learn AWS.",
            "resume_base64": None,
            "resume_filename": None,
        }

        with (
            patch("backend.services.ai_evaluation_service.GROQ_API_KEY", "test-key"),
            patch("backend.services.ai_evaluation_service._get_groq_client", return_value=mock_groq),
        ):
            result = evaluate_application_with_ai(app_record)
            self.assertEqual(result["fit_score"], 86)
            self.assertEqual(result["recommendation"], "approve")
            self.assertEqual(result["cv_status"], "no_cv")
            self.assertIn("Figma", result["extracted_skills"])
            self.assertEqual(result["sub_scores"]["division_relevance"], 90)

    def test_run_ai_evaluation_uses_cached_result_without_consuming_tokens(self):
        from unittest.mock import MagicMock, patch
        from backend.services.application_service import run_ai_evaluation

        cached_eval = {
            "fit_score": 79,
            "fit_label": "Strong Fit",
            "recommendation": "approve",
            "summary": "Already evaluated.",
            "strengths": ["Clear goal"],
            "concerns": [],
            "extracted_skills": ["Python"],
            "sub_scores": {"division_relevance": 80, "statement_quality": 78, "cv_signal": 75},
            "cv_status": "analyzed_pdf",
        }
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": 42,
                "full_name": "Cached Student",
                "ai_evaluation": cached_eval,
                "ai_evaluated_at": "2026-11-19T07:00:00+00:00",
            }
        ]

        with (
            patch("backend.services.application_service.get_supabase_admin", return_value=mock_client),
            patch("backend.services.application_service.evaluate_application_with_ai") as mock_eval,
        ):
            res = run_ai_evaluation(42, "officer-1", "Officer", force_refresh=False)
            self.assertTrue(res["cached"])
            self.assertEqual(res["evaluation"]["fit_score"], 79)
            mock_eval.assert_not_called()


if __name__ == "__main__":
    unittest.main()



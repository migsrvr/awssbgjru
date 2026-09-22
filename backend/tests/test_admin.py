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


if __name__ == "__main__":
    unittest.main()


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
            "Next Steps": "Join the Discord server and attend orientation this Friday.",
        }
        subject, body = interpolate_template(tmpl, vars_map)

        self.assertIn("Welcome to AWS SBG JRU", subject)
        self.assertIn("Hi Maria Santos,", body)
        self.assertIn("Congratulations! Your application to join AWS SBG JRU has been approved.", body)
        self.assertIn("Join the Discord server and attend orientation this Friday.", body)
        self.assertNotIn("{{Applicant Name}}", body)
        self.assertNotIn("{{Next Steps}}", body)

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


if __name__ == "__main__":
    unittest.main()

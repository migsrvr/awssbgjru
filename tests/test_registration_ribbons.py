from pathlib import Path
import unittest

from backend.api.config import VALID_DIVISIONS
from backend.registration_availability import (
    DIVISION_STATUS,
    DivisionAvailabilityError,
    validate_division_eligibility,
    validate_division_availability,
)


ROOT = Path(__file__).resolve().parents[1]


class RegistrationAvailabilityTest(unittest.TestCase):
    def test_skill_builder_availability_statuses(self):
        statuses = DIVISION_STATUS["skillbuilder"]
        for name in ("Software Development", "UI/UX"):
            self.assertEqual(statuses[name], "open")
        for name in (
            "Web Development",
            "Data Analyst",
            "Cloud Computing",
            "Machine Learning & AI",
        ):
            self.assertEqual(statuses[name], "full")
            with self.assertRaisesRegex(
                DivisionAvailabilityError,
                "This team is full! Please choose another!",
            ):
                validate_division_availability("skillbuilder", name)

    def test_office_full_divisions_are_marketing_and_media(self):
        self.assertEqual(DIVISION_STATUS["office"]["Marketing"], "full")
        self.assertEqual(DIVISION_STATUS["office"]["Media"], "full")
        self.assertNotIn("Technology", DIVISION_STATUS["office"])
        for name in ("Relations", "Operations", "Creatives"):
            self.assertEqual(DIVISION_STATUS["office"][name], "open")

    def test_office_year_eligibility_rules(self):
        validate_division_eligibility("office", "Relations", "First Year")
        validate_division_eligibility("office", "Creatives", "First Year")
        validate_division_eligibility("office", "Creatives", "Second Year")

        with self.assertRaisesRegex(
            DivisionAvailabilityError,
            "Relations is open only to 1st year students.",
        ):
            validate_division_eligibility("office", "Relations", "Second Year")

        with self.assertRaisesRegex(
            DivisionAvailabilityError,
            "Relations is open only to 1st year students.",
        ):
            validate_division_eligibility("office", "Relations", "Third Year")

        with self.assertRaisesRegex(
            DivisionAvailabilityError,
            "Relations is open only to 1st year students.",
        ):
            validate_division_eligibility("office", "Relations", "Fourth Year")

        with self.assertRaisesRegex(
            DivisionAvailabilityError,
            "Creatives is open only to 1st and 2nd year students.",
        ):
            validate_division_eligibility("office", "Creatives", "Third Year")

        with self.assertRaisesRegex(
            DivisionAvailabilityError,
            "Creatives is open only to 1st and 2nd year students.",
        ):
            validate_division_eligibility("office", "Creatives", "Fourth Year")

        validate_division_eligibility("office", "Operations", "Fourth Year")

    def test_backend_names_match_canonical_skill_builder_markup(self):
        expected = {
            "Software Development",
            "Web Development",
            "UI/UX",
            "Data Analyst",
            "Cloud Computing",
            "Machine Learning & AI",
        }
        self.assertEqual(VALID_DIVISIONS["skillbuilder"], expected)

    def test_markup_contains_exact_ribbon_copy_and_availability_metadata(self):
        office = (ROOT / "frontend/pages/office.html").read_text()
        skillbuilder = (ROOT / "frontend/pages/skillbuilder.html").read_text()
        self.assertNotIn("<<<<<<<", skillbuilder)
        self.assertNotIn("=======", skillbuilder)
        self.assertNotIn(">>>>>>>", skillbuilder)
        self.assertIn("Open for <strong>1st year</strong>", office)
        self.assertIn(
            "Open for <strong>1st year</strong> and <strong>2nd year</strong>",
            office,
        )
        self.assertNotIn('data-division="Technology"', office)
        for name in ("Marketing", "Media"):
            self.assertIn(
                f'data-division="{name}" data-availability="full"',
                office,
            )
            self.assertIn("ribbons/full.svg", office)
        for name in ("Software Development", "UI/UX"):
            self.assertIn(
                f'data-division="{name}" data-availability="open"',
                skillbuilder,
            )
        blue_open = ROOT / "frontend/assets/registration/ribbons/skillbuilder-open.svg"
        self.assertTrue(blue_open.is_file())
        self.assertIn("#1500FF", blue_open.read_text())
        self.assertIn("ribbons/skillbuilder-open.svg", skillbuilder)
        blue_full = ROOT / "frontend/assets/registration/ribbons/skillbuilder-full.svg"
        self.assertTrue(blue_full.is_file())
        self.assertIn("#1500FF", blue_full.read_text())
        for name in (
            "Web Development",
            "Data Analyst",
            "Cloud Computing",
            "Machine Learning & AI",
        ):
            self.assertIn(
                f'data-division="{name.replace("&", "&amp;")}" data-availability="full"',
                skillbuilder,
            )
        self.assertNotIn("Security", skillbuilder)
        self.assertNotIn("Advanced Network &amp; Infrastructure", skillbuilder)
        self.assertEqual(skillbuilder.count("ribbons/skillbuilder-open.svg"), 2)
        self.assertEqual(skillbuilder.count("ribbons/skillbuilder-full.svg"), 4)
        self.assertNotIn("ribbons/full.svg", skillbuilder)
        self.assertEqual(
            skillbuilder.count("This team is full! Please choose another!"),
            4,
        )
        self.assertEqual(
            office.count("This team is full! Please choose another!"),
            2,
        )
        self.assertIn('data-eligible-years="First Year"', office)
        self.assertIn('data-eligible-years="First Year,Second Year"', office)
        self.assertIn(
            "Relations is open only to 1st year students.",
            office,
        )
        self.assertIn(
            "Creatives is open only to 1st and 2nd year students.",
            office,
        )
        availability_css = (
            ROOT / "frontend/css/division-availability.css"
        ).read_text()
        self.assertIn(
            '.office-pill[data-division="Relations"] .division-eligibility-note,',
            availability_css,
        )
        self.assertIn(
            '.office-pill[data-division="Creatives"] .division-eligibility-note,',
            availability_css,
        )
        self.assertNotIn(
            ".office-pill.year-ineligible .availability-ribbon {\n"
            "  filter: grayscale(1);",
            availability_css,
        )
        office_js = (ROOT / "frontend/js/office.js").read_text()
        self.assertIn(
            "This division is only open to specific year level students.",
            office_js,
        )
        self.assertRegex(
            office,
            r'<script src="\.\./js/office\.js\?v=[^"]+"></script>',
        )


if __name__ == "__main__":
    unittest.main()

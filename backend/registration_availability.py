DIVISION_STATUS = {
    "office": {
        "Relations": "open",
        "Operations": "open",
        "Technology": "open",
        "Creatives": "open",
        "Marketing": "full",
        "Media": "full",
    },
    "skillbuilder": {
        "Software & Web Dev.": "open",
        "Security": "full",
        "Data Analyst": "full",
        "Cloud Computing": "full",
        "Machine Learning & AI": "full",
        "Advanced Network & Infrastructure": "full",
    },
}

DIVISION_ELIGIBILITY = {
    "office": {
        "Relations": (
            {"First Year"},
            "Relations is open only to 1st year students.",
        ),
        "Creatives": (
            {"First Year", "Second Year"},
            "Creatives is open only to 1st and 2nd year students.",
        ),
    },
}


class DivisionAvailabilityError(ValueError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def validate_division_availability(division_type: str, division_name: str) -> None:
    if not isinstance(division_type, str):
        raise DivisionAvailabilityError(
            "invalid_division_type",
            'division_type must be "office" or "skillbuilder"',
            422,
        )

    divisions = DIVISION_STATUS.get(division_type)
    if divisions is None:
        raise DivisionAvailabilityError(
            "invalid_division_type",
            'division_type must be "office" or "skillbuilder"',
            422,
        )

    if not isinstance(division_name, str):
        raise DivisionAvailabilityError(
            "invalid_division",
            "The selected division is not recognized.",
            422,
        )

    status = divisions.get(division_name)
    if status is None:
        raise DivisionAvailabilityError(
            "invalid_division",
            "The selected division is not recognized.",
            422,
        )
    if status != "open":
        raise DivisionAvailabilityError(
            "division_unavailable",
            "This team is full! Please choose another!",
            409,
        )


def validate_division_eligibility(
    division_type: str,
    division_name: str,
    year: str,
) -> None:
    eligibility = DIVISION_ELIGIBILITY.get(division_type, {}).get(division_name)
    if not eligibility:
        return

    allowed_years, message = eligibility
    if year not in allowed_years:
        raise DivisionAvailabilityError("division_ineligible", message, 422)

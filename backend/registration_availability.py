from typing import Dict, Mapping, Optional

DIVISION_STATUS = {
    "office": {
        "Relations": "open",
        "Operations": "open",
        "Creatives": "open",
        "Marketing": "full",
        "Media": "full",
    },
    "skillbuilder": {
        "Software Development": "open",
        "Web Development": "full",
        "UI/UX": "open",
        "Data Analyst": "full",
        "Cloud Computing": "full",
        "Machine Learning & AI": "full",
    },
}

VALID_AVAILABILITY_STATUSES = {"open", "full"}


def normalize_division_availability(
    raw: Optional[Mapping[str, Mapping[str, str]]] = None,
    base: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> Dict[str, Dict[str, str]]:
    """Returns a sanitized copy of division availability merged onto defaults."""
    source = base if isinstance(base, Mapping) else DIVISION_STATUS
    merged: Dict[str, Dict[str, str]] = {}
    for dept, default_divisions in DIVISION_STATUS.items():
        base_dept = source.get(dept) if isinstance(source.get(dept), Mapping) else {}
        merged[dept] = {}
        for name, default_status in default_divisions.items():
            base_val = base_dept.get(name) if isinstance(base_dept, Mapping) else None
            merged[dept][name] = (
                base_val if base_val in VALID_AVAILABILITY_STATUSES else default_status
            )

    if not isinstance(raw, Mapping):
        return merged

    for dept, divisions in merged.items():
        incoming = raw.get(dept)
        if not isinstance(incoming, Mapping):
            continue
        for name in divisions:
            status_val = incoming.get(name)
            if status_val in VALID_AVAILABILITY_STATUSES:
                divisions[name] = status_val

    return merged

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


def validate_division_availability(
    division_type: str,
    division_name: str,
    availability: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> None:
    if not isinstance(division_type, str):
        raise DivisionAvailabilityError(
            "invalid_division_type",
            'division_type must be "office" or "skillbuilder"',
            422,
        )

    status_map = (
        normalize_division_availability(availability)
        if availability is not None
        else DIVISION_STATUS
    )
    divisions = status_map.get(division_type)
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

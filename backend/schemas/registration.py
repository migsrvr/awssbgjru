from pydantic import BaseModel, field_validator
import re


class RegistrationRequest(BaseModel):
    full_name: str
    student_id: str
    email: str
    year: str
    program: str
    dob: str
    photo_base64: str = ""
    explanation: str = ""
    division_type: str
    division_name: str
    website: str = ""
    resume_base64: str = ""
    resume_filename: str = ""

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", v):
            raise ValueError("Invalid email address")
        return v

    @field_validator("division_type")
    @classmethod
    def validate_division_type(cls, v: str) -> str:
        if v not in ("office", "skillbuilder"):
            raise ValueError('division_type must be "office" or "skillbuilder"')
        return v

    @field_validator("photo_base64")
    @classmethod
    def validate_photo(cls, v: str) -> str:
        if v and not v.startswith("data:image/"):
            raise ValueError("photo_base64 must be a valid data URL")
        return v

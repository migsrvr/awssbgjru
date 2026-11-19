import base64
import datetime
import io
import json
import mimetypes
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from groq import Groq

from backend.api.config import (
    GROQ_API_KEY,
    GROQ_EVAL_FALLBACK_MODELS,
    GROQ_EVAL_MODEL,
    GROQ_MODEL,
)

MAX_CV_CHARS = 4000
MAX_EXPLANATION_CHARS = 1500
MAX_PDF_PAGES = 5

_groq_client: Optional[Groq] = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="AI evaluation is not configured: GROQ_API_KEY is missing on the server.",
            )
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _sanitize_filename(filename: Optional[str], fallback_ext: str = ".pdf") -> str:
    raw = (filename or f"applicant_cv{fallback_ext}").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", raw)
    return cleaned or f"applicant_cv{fallback_ext}"


def detect_resume_mime_type(resume_base64: Optional[str], resume_filename: Optional[str]) -> str:
    if resume_base64 and resume_base64.startswith("data:"):
        header = resume_base64.split(",", 1)[0]
        match = re.match(r"^data:([^;]+);base64$", header, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().lower()
    if resume_filename:
        guessed, _ = mimetypes.guess_type(resume_filename)
        if guessed:
            return guessed.lower()
    return "application/pdf"


def decode_resume_data_url(
    resume_base64: Optional[str],
    resume_filename: Optional[str] = None,
) -> Tuple[bytes, str, str]:
    """Decodes a base64 Data URL (or raw base64 string) into (bytes, mime_type, safe_filename)."""
    if not resume_base64 or not isinstance(resume_base64, str) or not resume_base64.strip():
        raise HTTPException(status_code=404, detail="No CV or resume attached for this applicant.")

    mime_type = detect_resume_mime_type(resume_base64, resume_filename)
    payload = resume_base64.split(",", 1)[1] if "," in resume_base64 else resume_base64
    try:
        raw_bytes = base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid resume encoding: {exc}")

    if not raw_bytes:
        raise HTTPException(status_code=404, detail="Attached resume file is empty.")

    ext = mimetypes.guess_extension(mime_type) or ".pdf"
    safe_name = _sanitize_filename(resume_filename, fallback_ext=ext)
    return raw_bytes, mime_type, safe_name


def _clean_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"[ \t]+", " ", text or "")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if len(normalized) > max_chars:
        return normalized[:max_chars].rstrip() + "..."
    return normalized


def _extract_pdf_text(raw_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw_bytes))
    chunks: List[str] = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        page_text = page.extract_text() or ""
        if page_text.strip():
            chunks.append(page_text.strip())
    return "\n\n".join(chunks)


def _extract_docx_text(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: List[str] = []
    for elem in root.iter():
        if elem.tag.endswith("}p"):
            runs = [t.text for t in elem.iter() if t.tag.endswith("}t") and t.text]
            line = "".join(runs).strip()
            if line:
                paragraphs.append(line)
    return "\n".join(paragraphs)


def extract_resume_text(
    resume_base64: Optional[str],
    resume_filename: Optional[str] = None,
) -> Tuple[str, str]:
    """Extracts plain text from an uploaded PDF or DOCX CV. Returns (text, cv_status)."""
    if not resume_base64 or not isinstance(resume_base64, str) or not resume_base64.strip():
        return "", "no_cv"

    mime_type = detect_resume_mime_type(resume_base64, resume_filename)
    lower_name = (resume_filename or "").lower()

    if mime_type.startswith("image/"):
        return "", "image_only"

    try:
        raw_bytes, mime_type, _ = decode_resume_data_url(resume_base64, resume_filename)
    except HTTPException:
        return "", "parse_error"

    if mime_type == "application/pdf" or lower_name.endswith(".pdf"):
        try:
            text = _clean_text(_extract_pdf_text(raw_bytes), MAX_CV_CHARS)
            return (text, "analyzed_pdf") if text else ("", "empty_pdf")
        except Exception:
            return "", "parse_error"

    if (
        mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or lower_name.endswith(".docx")
    ):
        try:
            text = _clean_text(_extract_docx_text(raw_bytes), MAX_CV_CHARS)
            return (text, "analyzed_docx") if text else ("", "empty_docx")
        except Exception:
            return "", "parse_error"

    return "", "unsupported_format"


ATS_SYSTEM_PROMPT = """You are an expert student-organization ATS (Applicant Tracking System) evaluator for the AWS Student Builder Group - Jose Rizal University (AWS SBG JRU).

Your job is to evaluate a JRU student's membership application objectively, fairly, and constructively for officer review.
Remember: applicants are college students (1st to 4th year), so potential, curiosity, initiative, and genuine interest matter alongside prior technical or creative experience.

Evaluate BOTH:
1. Statement of Interest (explanation): Is it genuine, specific, coherent, and non-spam? Flag gibberish, placeholder text (e.g., "dadada", "test", "asdf"), or single-word non-answers harshly.
2. CV / Resume (if provided): Extract relevant skills, projects, tools, leadership, or coursework aligned with the applicant's selected division. Never invent skills or experience not present in the provided text. If no CV was uploaded, evaluate fairly based on the Statement of Interest and academic background, and note the absence of a CV as a minor note rather than an automatic rejection.

Return ONLY valid JSON matching this exact schema:
{
  "fit_score": <integer 0-100>,
  "fit_label": "<one of: Strong Fit, Moderate Fit, Needs Review, Weak / Low-Effort>",
  "candidate_headline": "<one crisp 8-14 word executive headline capturing who this candidate is and their fit>",
  "best_fit_division": "<the single AWS SBG JRU division that best fits their skills/statement, or their selected division if already aligned>",
  "sub_scores": {
    "division_relevance": <integer 0-100>,
    "statement_quality": <integer 0-100>,
    "cv_signal": <integer 0-100>
  },
  "recommendation": "<one of: approve, revision_requested, declined>",
  "extracted_skills": ["<up to 8 concise skill/tool tags found in CV or statement>"],
  "summary": "<2-3 clear, officer-friendly sentences summarizing their background, motivation, and suitability for the chosen division>",
  "strengths": ["<2-4 concise bullet points>"],
  "concerns": ["<0-4 concise bullet points or red flags>"],
  "rubric_hints": {
    "genuine_interest": <boolean>,
    "quality_submission": <boolean>
  }
}"""


def _clamp_score(value: Any, default: int = 50) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return default


def _fit_label_for_score(score: int) -> str:
    if score >= 75:
        return "Strong Fit"
    if score >= 55:
        return "Moderate Fit"
    if score >= 35:
        return "Needs Review"
    return "Weak / Low-Effort"


def _normalize_ai_output(raw: Dict[str, Any], cv_status: str, model_used: str) -> Dict[str, Any]:
    fit_score = _clamp_score(raw.get("fit_score"), 50)
    sub_raw = raw.get("sub_scores") if isinstance(raw.get("sub_scores"), dict) else {}
    sub_scores = {
        "division_relevance": _clamp_score(sub_raw.get("division_relevance"), fit_score),
        "statement_quality": _clamp_score(sub_raw.get("statement_quality"), fit_score),
        "cv_signal": _clamp_score(
            sub_raw.get("cv_signal"),
            0 if cv_status == "no_cv" else fit_score,
        ),
    }

    rec = str(raw.get("recommendation") or "").strip().lower()
    if rec not in ("approve", "revision_requested", "declined"):
        rec = "approve" if fit_score >= 70 else ("revision_requested" if fit_score >= 40 else "declined")

    fit_label = str(raw.get("fit_label") or "").strip() or _fit_label_for_score(fit_score)

    def _clean_list(items: Any, limit: int) -> List[str]:
        if not isinstance(items, list):
            return []
        return [str(x).strip() for x in items if str(x).strip()][:limit]

    rubric_raw = raw.get("rubric_hints") if isinstance(raw.get("rubric_hints"), dict) else {}
    rubric_hints = {
        "genuine_interest": bool(rubric_raw.get("genuine_interest", fit_score >= 55)),
        "quality_submission": bool(rubric_raw.get("quality_submission", fit_score >= 45)),
    }

    return {
        "fit_score": fit_score,
        "fit_label": fit_label,
        "candidate_headline": str(raw.get("candidate_headline") or "").strip(),
        "best_fit_division": str(raw.get("best_fit_division") or "").strip(),
        "sub_scores": sub_scores,
        "recommendation": rec,
        "extracted_skills": _clean_list(raw.get("extracted_skills"), 8),
        "summary": str(raw.get("summary") or "AI evaluation completed.").strip(),
        "strengths": _clean_list(raw.get("strengths"), 4),
        "concerns": _clean_list(raw.get("concerns"), 4),
        "cv_status": cv_status,
        "rubric_hints": rubric_hints,
        "model": model_used,
        "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _parse_json_response(content: str) -> Dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def evaluate_application_with_ai(app: Dict[str, Any]) -> Dict[str, Any]:
    """Runs ATS evaluation on an applicant's CV and Statement of Interest using Groq."""
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI evaluation is not configured: GROQ_API_KEY is missing on the server.",
        )

    cv_text, cv_status = extract_resume_text(
        app.get("resume_base64"),
        app.get("resume_filename"),
    )
    explanation = _clean_text(app.get("explanation") or "", MAX_EXPLANATION_CHARS)

    user_prompt = (
        f"Applicant Profile:\n"
        f"- Year Level: {app.get('year') or 'Unknown'}\n"
        f"- Program: {app.get('program') or 'Unknown'}\n"
        f"- Target Department Type: {app.get('division_type') or 'Unknown'}\n"
        f"- Target Division: {app.get('division_name') or 'Unknown'}\n\n"
        f"Statement of Interest:\n"
        f"{explanation or '(Empty statement)'}\n\n"
        f"CV / Resume Status: {cv_status}\n"
        f"Extracted CV / Resume Text:\n"
        f"{cv_text or '(No extractable CV text provided)'}"
    )

    client = _get_groq_client()
    models_to_try: List[str] = []
    for candidate in (GROQ_EVAL_MODEL, *GROQ_EVAL_FALLBACK_MODELS, GROQ_MODEL):
        if candidate and candidate not in models_to_try:
            models_to_try.append(candidate)

    last_error: Optional[Exception] = None
    for model_name in models_to_try:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": ATS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=900,
                response_format={"type": "json_object"},
            )
            content = (completion.choices[0].message.content or "").strip()
            parsed = _parse_json_response(content)
            return _normalize_ai_output(parsed, cv_status=cv_status, model_used=model_name)
        except Exception as exc:
            last_error = exc
            continue

    raise HTTPException(
        status_code=502,
        detail=f"AI evaluation failed: {str(last_error)}",
    )

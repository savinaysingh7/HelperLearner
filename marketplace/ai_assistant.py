import json
import logging
from urllib import error, request

from django.conf import settings
from django.utils.text import slugify

logger = logging.getLogger(__name__)


def _strip_code_fences(raw_text):
    """Remove markdown JSON fences from model output when present."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _normalize_tags(raw_tags):
    """Normalize and deduplicate tag names returned by the model."""
    if not isinstance(raw_tags, list):
        return []

    normalized = []
    seen = set()
    for tag in raw_tags:
        tag_name = slugify(str(tag).strip())[:40]
        if not tag_name or tag_name in seen:
            continue
        seen.add(tag_name)
        normalized.append(tag_name)
        if len(normalized) >= 6:
            break
    return normalized


def _resolve_skill(raw_skill, available_skills):
    """Return a valid skill name from the allowed options or an empty string."""
    if not raw_skill:
        return ""

    choice_map = {skill.lower(): skill for skill in available_skills}
    return choice_map.get(str(raw_skill).strip().lower(), "")


def _build_prompt(title, description, available_skills):
    """Build a strict JSON prompt for Gemini to improve draft quality."""
    skill_text = ", ".join(available_skills) if available_skills else "No predefined skills"
    return (
        "You improve developer help-request drafts for a marketplace.\n"
        "Return ONLY valid JSON with this schema:\n"
        "{"
        '"improved_title":"string",'
        '"improved_description":"string",'
        '"suggested_tags":["tag-1","tag-2"],'
        '"suggested_skill":"string",'
        '"reasoning_summary":"string"'
        "}\n"
        "Rules:\n"
        "- improved_title: concise and specific.\n"
        "- improved_description: clear context, current behavior, expected behavior, attempted fixes.\n"
        "- suggested_tags: 3-6 lowercase tags.\n"
        "- suggested_skill: must be exactly one from the allowed skills list or empty string.\n"
        "- reasoning_summary: max 160 chars.\n"
        f"Allowed skills: {skill_text}\n\n"
        f"Draft title: {title}\n"
        f"Draft description: {description}\n"
    )


def generate_request_assistance(title, description, available_skills):
    """Call Gemini API and return normalized request-improvement suggestions."""
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("AI assistant is not configured. Set GEMINI_API_KEY in environment settings.")

    model_name = (getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash") or "gemini-1.5-flash").strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": _build_prompt(title, description, available_skills)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "response_mime_type": "application/json",
        },
    }

    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            response_data = json.loads(body)
    except error.HTTPError as exc:
        logger.warning("Gemini request failed with status=%s", exc.code)
        raise RuntimeError("AI assistant is temporarily unavailable. Please try again.") from exc
    except Exception as exc:
        logger.exception("Gemini request failed unexpectedly")
        raise RuntimeError("AI assistant is temporarily unavailable. Please try again.") from exc

    try:
        raw_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Gemini response format invalid: keys=%s", list(response_data.keys()))
        raise RuntimeError("AI assistant returned an unexpected response format.") from exc

    cleaned = _strip_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini response could not be parsed as JSON: %s", cleaned[:200])
        raise RuntimeError("AI assistant response could not be parsed.") from exc

    improved_title = str(parsed.get("improved_title") or title).strip()[:200]
    improved_description = str(parsed.get("improved_description") or description).strip()[:3000]
    suggested_tags = _normalize_tags(parsed.get("suggested_tags"))
    suggested_skill = _resolve_skill(parsed.get("suggested_skill"), available_skills)
    reasoning_summary = str(parsed.get("reasoning_summary") or "").strip()[:160]

    return {
        "improved_title": improved_title,
        "improved_description": improved_description,
        "suggested_tags": suggested_tags,
        "suggested_skill": suggested_skill,
        "reasoning_summary": reasoning_summary,
    }

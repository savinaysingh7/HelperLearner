import json
import logging
import time
from hashlib import sha256
from urllib import error, request

from django.conf import settings
from django.core.cache import cache
from django.utils.text import slugify

logger = logging.getLogger(__name__)


def _normalize_model_name(model_name):
    """Return a bare model id without the `models/` prefix."""
    normalized = (model_name or "").strip()
    if normalized.startswith("models/"):
        return normalized.split("/", 1)[1]
    return normalized


def _candidate_models():
    """Return ordered model candidates for resilient Gemini calls."""
    configured = _normalize_model_name(getattr(settings, "GEMINI_MODEL", ""))
    fallbacks = [
        "gemini-flash-latest",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
    ]
    ordered = [configured] + fallbacks
    seen = set()
    models = []
    for item in ordered:
        if not item or item in seen:
            continue
        seen.add(item)
        models.append(item)
    return models


def _cache_key(prefix, *parts):
    """Create a stable cache key for AI responses."""
    joined = "||".join(str(part or "") for part in parts)
    digest = sha256(joined.encode("utf-8")).hexdigest()
    return f"ai:{prefix}:{digest}"


def _post_json_with_retry(endpoint, payload, timeout_seconds, retries, backoff_seconds, model_name):
    """POST JSON payload with bounded retries for transient Gemini throttling."""
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    attempt = 0
    while True:
        attempt += 1
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except error.HTTPError as exc:
            should_retry = exc.code in {429, 503} and attempt <= retries
            if should_retry:
                delay = backoff_seconds * attempt
                logger.debug(
                    "Gemini temporary error status=%s model=%s attempt=%s/%s retry_in=%.2fs",
                    exc.code,
                    model_name,
                    attempt,
                    retries,
                    delay,
                )
                time.sleep(delay)
                continue
            raise


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

    cache_timeout = getattr(settings, "AI_REQUEST_ASSIST_CACHE_SECONDS", 600)
    cache_key = _cache_key("assist", title, description, ",".join(sorted(available_skills)))
    cached = cache.get(cache_key)
    if cached:
        return cached

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

    retries = getattr(settings, "AI_HTTP_RETRY_ATTEMPTS", 2)
    backoff = getattr(settings, "AI_HTTP_RETRY_BASE_DELAY_SECONDS", 0.4)
    timeout_seconds = getattr(settings, "AI_ASSIST_TIMEOUT_SECONDS", 20)

    response_data = None
    last_exception = None
    tried_models = _candidate_models()
    for model_name in tried_models:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            response_data = _post_json_with_retry(
                endpoint=endpoint,
                payload=payload,
                timeout_seconds=timeout_seconds,
                retries=retries,
                backoff_seconds=backoff,
                model_name=model_name,
            )
            break
        except error.HTTPError as exc:
            last_exception = exc
            if exc.code in {404, 429}:
                logger.info("Gemini model candidate skipped (status=%s): %s", exc.code, model_name)
                continue
            logger.warning("Gemini request failed with status=%s model=%s", exc.code, model_name)
            raise RuntimeError("AI assistant is temporarily unavailable. Please try again.") from exc
        except Exception as exc:
            last_exception = exc
            logger.warning("Gemini request failed unexpectedly for model=%s: %s", model_name, exc)
            raise RuntimeError("AI assistant is temporarily unavailable. Please try again.") from exc

    if response_data is None:
        logger.warning("No compatible Gemini model found for candidates=%s", tried_models)
        raise RuntimeError("AI assistant model is unavailable. Update GEMINI_MODEL to an enabled model.") from last_exception

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

    result = {
        "improved_title": str(parsed.get("improved_title") or title).strip()[:200],
        "improved_description": str(parsed.get("improved_description") or description).strip()[:3000],
        "suggested_tags": _normalize_tags(parsed.get("suggested_tags")),
        "suggested_skill": _resolve_skill(parsed.get("suggested_skill"), available_skills),
        "reasoning_summary": str(parsed.get("reasoning_summary") or "").strip()[:160],
    }
    cache.set(cache_key, result, cache_timeout)
    return result


def generate_request_summary(title, description):
    """Generate a single-sentence AI summary of a help request draft."""
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        return ""

    cache_timeout = getattr(settings, "AI_SUMMARY_CACHE_SECONDS", 3600)
    cache_key = _cache_key("summary", title, description)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    prompt = (
        "Summarize this developer help request in exactly one concise sentence (max 150 chars).\n"
        "Focus on the technical problem and desired outcome.\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "max_output_tokens": 100},
    }

    retries = getattr(settings, "AI_HTTP_RETRY_ATTEMPTS", 2)
    backoff = getattr(settings, "AI_HTTP_RETRY_BASE_DELAY_SECONDS", 0.4)
    timeout_seconds = getattr(settings, "AI_SUMMARY_TIMEOUT_SECONDS", 10)
    last_exception = None

    for model_name in _candidate_models():
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            data = _post_json_with_retry(
                endpoint=endpoint,
                payload=payload,
                timeout_seconds=timeout_seconds,
                retries=retries,
                backoff_seconds=backoff,
                model_name=model_name,
            )
            summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()[:250]
            cache.set(cache_key, summary, cache_timeout)
            return summary
        except error.HTTPError as exc:
            last_exception = exc
            if exc.code in {404, 429}:
                logger.debug("Gemini summary model unavailable status=%s model=%s", exc.code, model_name)
                continue
            logger.debug("Gemini summary HTTP error status=%s model=%s", exc.code, model_name)
            break
        except Exception as exc:
            last_exception = exc
            logger.debug("Gemini summary failed for model=%s: %s", model_name, exc)
            continue

    if last_exception:
        logger.info("Gemini summary skipped: %s", last_exception)
    cache.set(cache_key, "", 120)
    return ""

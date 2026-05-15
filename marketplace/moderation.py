"""AI content moderation — classify text as safe/flagged/blocked using Gemini."""

import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


BLOCKED_PATTERNS = [
    r'\b(hack|exploit|ddos|phishing|ransomware)\b',
    r'\b(password\s*crack|sql\s*inject|xss\s*attack)\b',
]

FLAGGED_PATTERNS = [
    r'\b(urgent|guaranteed|100%|free money)\b',
    r'\b(contact me privately|whatsapp|telegram)\b',
]


def moderate_text(text):
    """
    Classify text content for moderation.

    Returns:
        dict with keys:
        - 'status': 'safe' | 'flagged' | 'blocked'
        - 'reason': explanation string (empty for safe content)
    """
    if not text or not text.strip():
        return {'status': 'safe', 'reason': ''}

    lower_text = text.lower()

    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        match = re.search(pattern, lower_text, re.IGNORECASE)
        if match:
            return {
                'status': 'blocked',
                'reason': f'Content contains prohibited term: {match.group()}',
            }

    # Check flagged patterns
    for pattern in FLAGGED_PATTERNS:
        match = re.search(pattern, lower_text, re.IGNORECASE)
        if match:
            return {
                'status': 'flagged',
                'reason': f'Content flagged for review: contains "{match.group()}"',
            }

    # Optional: use Gemini for deeper analysis
    api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    if api_key and getattr(settings, 'AI_MODERATION_ENABLED', False):
        try:
            return _gemini_moderate(text, api_key)
        except Exception:
            logger.exception('Gemini moderation failed, falling back to pattern-only')

    return {'status': 'safe', 'reason': ''}


def _gemini_moderate(text, api_key):
    """Use Gemini to classify content. Returns safe/flagged/blocked."""
    import json
    import urllib.request

    prompt = (
        "You are a content moderator for a developer help platform. "
        "Classify the following user-submitted text as one of: SAFE, FLAGGED, BLOCKED. "
        "BLOCKED = spam, harassment, or malicious content. "
        "FLAGGED = suspicious but not clearly harmful. "
        "SAFE = normal developer content. "
        "Respond with ONLY a JSON object: {\"status\": \"safe|flagged|blocked\", \"reason\": \"brief explanation\"}\n\n"
        f"Text: {text[:500]}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'x-goog-api-key': api_key,
        },
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    raw = data['candidates'][0]['content']['parts'][0]['text']
    # Extract JSON from response
    json_match = re.search(r'\{[^}]+\}', raw)
    if json_match:
        result = json.loads(json_match.group())
        if result.get('status') in ('safe', 'flagged', 'blocked'):
            return result

    return {'status': 'safe', 'reason': ''}

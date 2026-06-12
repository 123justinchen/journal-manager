# journal_app/translator.py - Shared translation utility using DeepSeek API

import logging
import requests
from config import DEEPSEEK_API_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPTS = {
    "title": "你是一个专业的光学领域科学翻译。将以下英文学术论文标题翻译成准确、简洁的中文。只返回翻译结果，不要任何解释。",
    "abstract": "你是一个专业的光学领域科学翻译。将以下英文学术论文摘要翻译成准确、流畅的中文。保持专业术语的准确性。只返回翻译结果，不要任何解释。",
}

MAX_TOKENS = {"title": 1000, "abstract": 4000}
TRUNCATE = {"title": 3000, "abstract": 2500}


def translate(text: str, trans_type: str = "title") -> str:
    """Translate text using DeepSeek API.

    Args:
        text: Text to translate (English → Chinese).
        trans_type: "title" or "abstract".

    Returns:
        Translated text, or empty string on failure.
    """
    if not text or len(text.strip()) < 5:
        return ""

    system_prompt = SYSTEM_PROMPTS.get(trans_type, SYSTEM_PROMPTS["title"])
    max_tok = MAX_TOKENS.get(trans_type, 1000)
    truncate_len = TRUNCATE.get(trans_type, 3000)

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text[:truncate_len]},
                ],
                "temperature": 0.3,
                "max_tokens": max_tok,
            },
            timeout=60,
        )

        if resp.status_code != 200:
            logger.warning("Translation API returned %d", resp.status_code)
            return ""

        data = resp.json()
        msg = data["choices"][0]["message"]
        result = msg.get("content", "").strip()

        # Fallback: if content is empty, try reasoning_content (DeepSeek R1-style)
        if not result and msg.get("reasoning_content"):
            result = _extract_from_reasoning(msg["reasoning_content"])

        # Strip leading label prefixes that the model sometimes adds
        if trans_type == "abstract":
            for prefix in ["摘要：", "摘要:", "摘要"]:
                if result.startswith(prefix):
                    result = result[len(prefix):].strip()
                    break

        return result

    except Exception:
        logger.exception("Translation error")
        return ""


def _extract_from_reasoning(reasoning: str) -> str:
    """Extract Chinese translation from reasoning_content as fallback."""
    lines = [
        l.strip()
        for l in reasoning.split("\n")
        if l.strip() and len(l.strip()) > 5
    ]
    # Look for lines containing Chinese characters (most likely the translation)
    for line in reversed(lines):
        if any(c in line for c in "。，的"):
            return line.strip('"').strip("'").strip()
    # Last resort: return the last non-empty line
    if lines:
        return lines[-1].strip('"').strip("'").strip()
    return ""

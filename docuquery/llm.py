"""Groq chat-completions adapter and safe structured-summary parsing."""

import json
import re
from typing import Any


class LLMError(RuntimeError):
    pass


def _call_groq(api_key: str, model: str, messages: list[dict[str, str]], max_tokens: int = 1400) -> str:
    if not api_key:
        raise LLMError(
            "Groq API key is not configured — add GROQ_API_KEY to your .env file and restart."
        )
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.15,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        if not text.strip():
            raise LLMError("Groq returned an empty response.")
        return text.strip()
    except LLMError:
        raise
    except Exception as exc:
        # Do not include secrets or request headers in user-facing errors.
        message = str(exc)
        lowered = message.lower()
        if "429" in message or "rate limit" in lowered or "too many requests" in lowered:
            raise LLMError(
                "Groq rate limit reached (free tier: 30 requests/minute) — wait a minute and try again."
            ) from exc
        if "401" in message or "unauthorized" in lowered or "invalid api key" in lowered or "api key" in lowered and "invalid" in lowered:
            raise LLMError(
                "Groq API key is invalid or revoked — check GROQ_API_KEY in your .env file."
            ) from exc
        if (
            "connection" in lowered
            or "timed out" in lowered
            or "timeout" in lowered
            or "name resolution" in lowered
            or "failed to establish" in lowered
            or "network" in lowered
        ):
            raise LLMError(
                "Groq could not be reached — check your internet connection and try again."
            ) from exc
        raise LLMError(f"Groq request failed: {message}") from exc


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise LLMError("The model did not return a valid structured summary.")
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError("The model returned malformed JSON for the summary.") from exc
    if not isinstance(value, dict):
        raise LLMError("The model summary must be a JSON object.")
    return value


def generate_structured_summary(context: str, api_key: str, model: str) -> dict[str, str]:
    system = (
        "You are a careful scientific-paper reading assistant. Use only the supplied excerpts. "
        "Never invent details. Cite evidence with the page markers already shown, such as [p. 4]. "
        "When a detail is absent, say 'Not clearly stated in the retrieved text.'"
    )
    user = f"""Create a concise, useful summary of this scientific paper from the evidence below.
Return ONLY a valid JSON object with these exact string keys:
"overall_summary", "objective", "methodology", "dataset", "key_findings", "limitations", "conclusion".
Keep each field to 1-3 sentences. Include inline page citations (for example [p. 2]) wherever evidence supports a claim. Do not cite pages that are not present in the excerpts.

EVIDENCE:
{context}
"""
    raw = _call_groq(
        api_key,
        model,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1800,
    )
    parsed = _parse_json_object(raw)
    keys = (
        "overall_summary", "objective", "methodology", "dataset",
        "key_findings", "limitations", "conclusion",
    )
    normalized: dict[str, str] = {}
    for key in keys:
        value = parsed.get(key, "Not clearly stated in the retrieved text.")
        normalized[key] = str(value).strip() if value is not None else "Not clearly stated in the retrieved text."
    return normalized


def answer_from_context(question: str, context: str, api_key: str, model: str) -> str:
    system = (
        "You answer questions about scientific papers using only the provided retrieved passages. "
        "Do not use outside knowledge or make up claims. Cite supporting page markers like [p. 7]. "
        "If the passages do not answer the question, say that the paper excerpts do not provide enough evidence."
    )
    user = f"""Question: {question}

Retrieved paper passages:
{context}

Answer in clear, concise language. Cite each important claim with the page marker(s) from the passages."""
    return _call_groq(
        api_key,
        model,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=900,
    )

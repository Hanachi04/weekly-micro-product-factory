"""
LLM Client with automatic fallback chain (Zero-budget).

Order: Gemini → Groq → Mistral
Keys are read ONLY from environment variables:
  GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Output-token budget for full-page HTML generation (design agent).
# Override with env LLM_MAX_TOKENS; always clamped to the model's own limit.
DEFAULT_HTML_MAX_TOKENS = 8192
# Legacy budget kept for the short JSON/text callers (content, diversity, critic).
LEGACY_MAX_TOKENS = 1024

# Max output tokens per model (provider docs, Nov 2026). Unknown models: no extra cap.
#   Gemini: 2.5-flash / flash-latest 65,536; 2.0-flash 8,192
#   Groq:   llama-3.3-70b-versatile 32,768; gpt-oss-20b 65,536; llama-3.1-8b-instant 131,072
#   Mistral: mistral-small-latest has no published output cap below its 128k context
MODEL_MAX_OUTPUT_TOKENS: dict[str, int] = {
    "gemini-2.5-flash": 65536,
    "gemini-2.0-flash": 8192,
    "gemini-flash-latest": 65536,
    "llama-3.3-70b-versatile": 32768,
    "openai/gpt-oss-20b": 65536,
    "llama-3.1-8b-instant": 131072,
    "mistral-small-latest": 32768,
}


def html_max_tokens() -> int:
    """Requested max output tokens for HTML generation (env LLM_MAX_TOKENS, default 8192)."""
    raw = os.environ.get("LLM_MAX_TOKENS", "").strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
        logger.warning("Invalid LLM_MAX_TOKENS=%r, using %s", raw, DEFAULT_HTML_MAX_TOKENS)
    return DEFAULT_HTML_MAX_TOKENS


def cap_for_model(model_name: str, requested: int) -> int:
    """Clamp requested max tokens to the model's documented output limit."""
    limit = MODEL_MAX_OUTPUT_TOKENS.get(model_name)
    return min(requested, limit) if limit else requested


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    finish_reason: Optional[str] = None


def _norm_finish(reason) -> Optional[str]:
    """Normalize provider finish reasons; truncation becomes 'length'."""
    if reason is None:
        return None
    name = getattr(reason, "name", None) or getattr(reason, "value", None) or reason
    s = str(name).strip().lower()
    if "max_tokens" in s or "length" in s:
        return "length"
    return s


class AllProvidersFailedError(Exception):
    """Raised when every provider in the chain fails."""


def _try_gemini(prompt: str, system_prompt: str, max_tokens: Optional[int] = None) -> Optional[LLMResult]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("Gemini: no GEMINI_API_KEY, skip")
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        last_err = None
        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"):
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_prompt or None,
                )
                kwargs = {}
                if max_tokens:
                    kwargs["generation_config"] = {
                        "max_output_tokens": cap_for_model(model_name, max_tokens)
                    }
                response = model.generate_content(prompt, **kwargs)
                finish = None
                try:
                    finish = _norm_finish(response.candidates[0].finish_reason)
                except Exception:
                    finish = None
                try:
                    text = getattr(response, "text", None)
                except Exception:
                    text = None
                if text and text.strip():
                    logger.info("Gemini success with %s", model_name)
                    return LLMResult(text.strip(), "Gemini", model_name, finish)
            except Exception as e:
                last_err = e
                logger.warning("Gemini model %s failed: %s", model_name, e)
        if last_err:
            raise last_err
        logger.warning("Gemini: empty response")
        return None
    except Exception as exc:
        logger.warning("Gemini failed: %s", exc)
        return None


def _try_groq(prompt: str, system_prompt: str, max_tokens: Optional[int] = None) -> Optional[LLMResult]:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        logger.info("Groq: no GROQ_API_KEY, skip")
        return None
    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_err = None
        for model_name in (
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant",
        ):
            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=cap_for_model(model_name, max_tokens or LEGACY_MAX_TOKENS),
                )
                choice = completion.choices[0]
                text = choice.message.content
                if text and text.strip():
                    logger.info("Groq success with %s", model_name)
                    return LLMResult(
                        text.strip(), "Groq", model_name,
                        _norm_finish(getattr(choice, "finish_reason", None)),
                    )
            except Exception as e:
                last_err = e
                logger.warning("Groq model %s failed: %s", model_name, e)
        if last_err:
            raise last_err
        logger.warning("Groq: empty response")
        return None
    except Exception as exc:
        logger.warning("Groq failed: %s", exc)
        return None


def _try_mistral(prompt: str, system_prompt: str, max_tokens: Optional[int] = None) -> Optional[LLMResult]:
    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        logger.info("Mistral: no MISTRAL_API_KEY, skip")
        return None
    try:
        from mistralai import Mistral

        client = Mistral(api_key=api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        model_name = "mistral-small-latest"
        response = client.chat.complete(
            model=model_name,
            messages=messages,
            temperature=0.4,
            max_tokens=cap_for_model(model_name, max_tokens or LEGACY_MAX_TOKENS),
        )
        choice = response.choices[0]
        text = choice.message.content
        if text and text.strip():
            logger.info("Mistral: success")
            return LLMResult(
                text.strip(), "Mistral", model_name,
                _norm_finish(getattr(choice, "finish_reason", None)),
            )
        logger.warning("Mistral: empty response")
        return None
    except Exception as exc:
        logger.warning("Mistral failed: %s", exc)
        return None


def generate_text_with_meta(
    prompt: str, system_prompt: str = "", max_tokens: Optional[int] = None
) -> LLMResult:
    """
    Generate text using the fallback chain:
      1. Gemini (free tier)
      2. Groq (Llama free tier)
      3. Mistral (free tier)

    max_tokens: output budget (clamped per model). None keeps the legacy
    behaviour (1024 for Groq/Mistral, Gemini model default).
    Returns an LLMResult including the normalized finish_reason
    ('length' means the output was truncated).
    Raises AllProvidersFailedError if every provider fails or is unconfigured.
    """
    if not prompt or not str(prompt).strip():
        raise ValueError("prompt must be a non-empty string")

    providers = [
        ("Gemini", _try_gemini),
        ("Groq", _try_groq),
        ("Mistral", _try_mistral),
    ]

    errors: list[str] = []
    for name, fn in providers:
        logger.info("Trying provider: %s", name)
        result = fn(prompt, system_prompt or "", max_tokens)
        if result:
            return result
        errors.append(name)

    raise AllProvidersFailedError(
        f"All LLM providers failed or unconfigured. Tried: {', '.join(errors)}. "
        "Set at least one of: GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY"
    )


def generate_text(prompt: str, system_prompt: str = "", max_tokens: Optional[int] = None) -> str:
    """Backward-compatible wrapper returning only the text."""
    return generate_text_with_meta(prompt, system_prompt, max_tokens).text


def available_providers() -> list[str]:
    """Return names of providers that have an API key configured."""
    mapping = {
        "Gemini": "GEMINI_API_KEY",
        "Groq": "GROQ_API_KEY",
        "Mistral": "MISTRAL_API_KEY",
    }
    return [name for name, env in mapping.items() if os.environ.get(env, "").strip()]

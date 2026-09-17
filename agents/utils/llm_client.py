"""
LLM Client with automatic fallback chain (Zero-budget).

Order: Gemini → Groq → Mistral
Keys are read ONLY from environment variables:
  GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """Raised when every provider in the chain fails."""


def _try_gemini(prompt: str, system_prompt: str) -> Optional[str]:
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
                response = model.generate_content(prompt)
                text = getattr(response, "text", None)
                if text and text.strip():
                    logger.info("Gemini success with %s", model_name)
                    return text.strip()
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


def _try_groq(prompt: str, system_prompt: str) -> Optional[str]:
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
                    max_tokens=1024,
                )
                text = completion.choices[0].message.content
                if text and text.strip():
                    logger.info("Groq success with %s", model_name)
                    return text.strip()
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


def _try_mistral(prompt: str, system_prompt: str) -> Optional[str]:
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

        response = client.chat.complete(
            model="mistral-small-latest",
            messages=messages,
            temperature=0.4,
            max_tokens=1024,
        )
        text = response.choices[0].message.content
        if text and text.strip():
            logger.info("Mistral: success")
            return text.strip()
        logger.warning("Mistral: empty response")
        return None
    except Exception as exc:
        logger.warning("Mistral failed: %s", exc)
        return None


def generate_text(prompt: str, system_prompt: str = "") -> str:
    """
    Generate text using the fallback chain:
      1. Gemini (free tier)
      2. Groq (Llama free tier)
      3. Mistral (free tier)

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
        result = fn(prompt, system_prompt or "")
        if result:
            return result
        errors.append(name)

    raise AllProvidersFailedError(
        f"All LLM providers failed or unconfigured. Tried: {', '.join(errors)}. "
        "Set at least one of: GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY"
    )


def available_providers() -> list[str]:
    """Return names of providers that have an API key configured."""
    mapping = {
        "Gemini": "GEMINI_API_KEY",
        "Groq": "GROQ_API_KEY",
        "Mistral": "MISTRAL_API_KEY",
    }
    return [name for name, env in mapping.items() if os.environ.get(env, "").strip()]

"""Shared Gemini client wrapper.

Supports the current `google-genai` SDK and falls back to the legacy
`google-generativeai` package if that is what is installed. Callers get a
single `generate_json()` entry point that always returns a parsed dict, so no
caller needs to know which SDK is present.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional, Sequence

from app.config import settings

logger = logging.getLogger(__name__)

_PLACEHOLDER_KEYS = {
    "",
    "your_gemini_api_key_here",
    "your_api_key_here",
    "changeme",
    "none",
}


def _key_is_usable(key: str) -> bool:
    return key.strip().lower() not in _PLACEHOLDER_KEYS


class GeminiUnavailable(RuntimeError):
    """Raised when a Gemini call is attempted without a usable client."""


class GeminiModelNotAvailable(RuntimeError):
    """Raised when the configured model name is rejected by the API.

    Google retires model names and restricts older ones to existing users, so a
    key that authenticates perfectly can still 404 on a model. That is a config
    problem, not a transient one - retrying it just delays a clear error.
    """


class GeminiClient:
    """Thin, SDK-agnostic wrapper around Gemini multimodal generation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.GEMINI_API_KEY) or ""
        self.model = model or settings.GEMINI_MODEL
        self.sdk: Optional[str] = None
        self._client: Any = None
        self._types: Any = None
        self._unavailable_reason: str = "not initialised"
        self._init_client()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        if not _key_is_usable(self.api_key):
            self._unavailable_reason = (
                "GEMINI_API_KEY is not set (or is still the placeholder value). "
                "Add a real key to .env to enable drawing analysis."
            )
            logger.warning(self._unavailable_reason)
            return

        # Preferred: current SDK
        try:
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=self.api_key)
            self._types = types
            self.sdk = "google-genai"
            logger.info("Gemini initialised via google-genai (model=%s)", self.model)
            return
        except ImportError:
            logger.debug("google-genai not installed, trying legacy SDK")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("google-genai init failed: %s", e)

        # Fallback: legacy SDK
        try:
            import google.generativeai as genai_legacy

            genai_legacy.configure(api_key=self.api_key)
            self._client = genai_legacy.GenerativeModel(self.model)
            self.sdk = "google-generativeai"
            logger.info("Gemini initialised via legacy google-generativeai")
            return
        except ImportError:
            self._unavailable_reason = (
                "No Gemini SDK installed. Run: pip install google-genai"
            )
        except Exception as e:  # pragma: no cover - defensive
            self._unavailable_reason = f"Gemini init failed: {e}"

        logger.warning(self._unavailable_reason)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return self._client is not None

    @property
    def unavailable_reason(self) -> str:
        return self._unavailable_reason

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_json(
        self,
        prompt: str,
        images: Optional[Sequence[bytes]] = None,
        mime_type: str = "image/png",
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        max_retries: int = 3,
    ) -> dict:
        """Run a multimodal prompt and return the parsed JSON object.

        Raises GeminiUnavailable if no client could be constructed. Transport
        errors are retried with exponential backoff; a response that cannot be
        parsed as JSON raises ValueError so callers can record the failure
        rather than silently treating it as "nothing found".
        """
        if not self.is_available():
            raise GeminiUnavailable(self._unavailable_reason)

        temperature = (
            settings.GEMINI_TEMPERATURE if temperature is None else temperature
        )
        max_output_tokens = max_output_tokens or settings.GEMINI_MAX_TOKENS

        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                raw = self._call(prompt, images or [], mime_type, temperature, max_output_tokens)
                return self._parse_json(raw)
            except ValueError:
                # Unparseable JSON - retrying rarely helps, surface immediately.
                raise
            except Exception as e:
                if self._is_model_not_found(e):
                    raise GeminiModelNotAvailable(
                        f"The model '{self.model}' is not available to this API key. "
                        f"Set GEMINI_MODEL in .env to one your key can use - "
                        f"'gemini-pro-latest' always tracks the current Pro model. "
                        f"Run `python -m app.pipeline.gemini_client` to list the "
                        f"models this key can actually reach. Original error: {e}"
                    ) from e
                last_error = e
                wait = 2**attempt
                logger.warning(
                    "Gemini call failed (attempt %d/%d): %s - retrying in %ds",
                    attempt + 1,
                    max_retries,
                    e,
                    wait,
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)

        raise RuntimeError(f"Gemini call failed after {max_retries} attempts: {last_error}")

    @staticmethod
    def _is_model_not_found(error: Exception) -> bool:
        text = str(error).lower()
        return ("not_found" in text or "404" in text) and "model" in text

    def _call(
        self,
        prompt: str,
        images: Sequence[bytes],
        mime_type: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        if self.sdk == "google-genai":
            parts: list[Any] = [
                self._types.Part.from_bytes(data=img, mime_type=mime_type) for img in images
            ]
            parts.append(self._types.Part.from_text(text=prompt))
            response = self._client.models.generate_content(
                model=self.model,
                contents=parts,
                config=self._types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                ),
            )
            return response.text or ""

        # Legacy SDK
        import base64

        contents: list[Any] = [
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(img).decode("utf-8"),
                }
            }
            for img in images
        ]
        contents.append(prompt)
        response = self._client.generate_content(
            contents,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "response_mime_type": "application/json",
            },
        )
        return response.text or ""

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse a JSON object out of a model response."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Gemini returned an empty response")

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fenced code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # First balanced {...} span
        start = text.find("{")
        if start != -1:
            depth = 0
            in_string = False
            escaped = False
            for i in range(start, len(text)):
                ch = text[i]
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start : i + 1])
                            if isinstance(parsed, dict):
                                return parsed
                        except json.JSONDecodeError:
                            break

        raise ValueError(f"Could not parse JSON from Gemini response: {text[:300]!r}")


_shared_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Return the process-wide Gemini client, constructing it on first use."""
    global _shared_client
    if _shared_client is None:
        _shared_client = GeminiClient()
    return _shared_client


def list_available_models() -> list[str]:
    """Model names this API key can call generateContent on."""
    client = GeminiClient()
    if not client.is_available():
        raise GeminiUnavailable(client.unavailable_reason)
    if client.sdk != "google-genai":
        raise RuntimeError("Listing models requires the google-genai SDK.")
    names = []
    for model in client._client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            names.append(model.name.replace("models/", ""))
    return sorted(names)


if __name__ == "__main__":  # pragma: no cover - operator convenience
    import sys

    try:
        available = list_available_models()
    except Exception as exc:
        print(f"Could not list models: {exc}")
        sys.exit(1)

    current = GeminiClient().model
    print(f"GEMINI_MODEL is currently: {current}")
    status = "OK  available" if current in available else "!!  NOT available"
    print(status)
    print()
    print("Models this key can call:")
    for name in available:
        print(f"  {'* ' if name == current else '  '}{name}")

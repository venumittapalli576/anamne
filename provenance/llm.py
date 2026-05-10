"""Unified LLM client.

Wraps Claude (Anthropic), Gemini (Google), and Ollama (local) behind one
interface so the agents don't have to know which provider they're talking to.

Priority: ANTHROPIC_API_KEY > GEMINI_API_KEY > MODEL=ollama/...

Why a thin wrapper instead of LiteLLM: less surface area, no extra
dependency, easier to read, and we only need text-in / text-out for now.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from provenance.config import Settings, get_settings


@dataclass
class LLMResponse:
    text: str
    model: str


# Gemini free tier 503s a lot — try less-crowded models first, then bigger ones
_GEMINI_FALLBACKS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]

# Default Ollama base URL (the OpenAI-compatible endpoint)
_OLLAMA_BASE = "http://localhost:11434/v1"


class LLMClient:
    """Picks Claude, Gemini, or Ollama based on config.

    Priority: ANTHROPIC_API_KEY > GEMINI_API_KEY > MODEL=ollama/...
    Raises a clear error if no provider is configured.
    """

    def __init__(self, cfg: Settings | None = None):
        self._cfg = cfg or get_settings()
        self._provider: str
        self._model: str
        self._client = None

        if self._cfg.anthropic_api_key:
            import anthropic
            self._provider = "anthropic"
            self._model = self._cfg.model or "claude-sonnet-4-6"
            self._client = anthropic.Anthropic(api_key=self._cfg.anthropic_api_key)

        elif self._cfg.gemini_api_key:
            from google import genai
            self._provider = "gemini"
            self._model = self._cfg.model or "gemini-2.5-flash-lite"
            self._client = genai.Client(api_key=self._cfg.gemini_api_key)

        elif self._cfg.model and self._cfg.model.startswith("ollama/"):
            self._provider = "ollama"
            # Strip the "ollama/" prefix to get the raw model name
            self._model = self._cfg.model.split("/", 1)[1]

        else:
            raise RuntimeError(
                "No LLM provider configured.\n"
                "  Option 1 (free):    set GEMINI_API_KEY in .env\n"
                "  Option 2 (quality): set ANTHROPIC_API_KEY in .env\n"
                "  Option 3 (offline): set MODEL=ollama/llama3.2 and run Ollama\n"
                "Run `provenance init` for an interactive setup wizard."
            )

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Single text completion. Returns LLMResponse(text, model)."""
        if self._provider == "anthropic":
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text if msg.content else ""
            return LLMResponse(text=text, model=self._model)

        if self._provider == "gemini":
            return self._gemini_complete(prompt, max_tokens, temperature)

        if self._provider == "ollama":
            return self._ollama_complete(prompt, max_tokens, temperature)

        raise RuntimeError(f"Unknown provider: {self._provider}")

    # ------------------------------------------------------------------ #
    # Provider-specific helpers                                             #
    # ------------------------------------------------------------------ #

    def _gemini_complete(self, prompt: str, max_tokens: int, temperature: float) -> LLMResponse:
        from google.genai import types
        from google.genai import errors as genai_errors

        # Try configured model first, then fallbacks the user didn't pick
        candidates = [self._model] + [m for m in _GEMINI_FALLBACKS if m != self._model]

        last_err: Exception | None = None
        for model_name in candidates:
            for attempt in range(3):
                try:
                    result = self._client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            max_output_tokens=max_tokens,
                            temperature=temperature,
                        ),
                    )
                    return LLMResponse(text=result.text or "", model=model_name)
                except genai_errors.ServerError as e:
                    # 503 / 500 — model overloaded, retry with backoff
                    last_err = e
                    if attempt < 2:
                        time.sleep(1.5 ** attempt + 0.5)
                except genai_errors.ClientError:
                    # 4xx — request issue, no point retrying or falling back
                    raise
            # All attempts on this model failed → try next model in fallback list

        raise last_err or RuntimeError("All Gemini models unavailable")

    def _ollama_complete(self, prompt: str, max_tokens: int, temperature: float) -> LLMResponse:
        """Call the Ollama OpenAI-compatible REST endpoint.

        Ollama exposes POST /v1/chat/completions (same shape as OpenAI).
        We use httpx (already a project dependency) so we need zero new deps.
        """
        import httpx

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        try:
            resp = httpx.post(
                f"{_OLLAMA_BASE}/chat/completions",
                json=payload,
                timeout=120.0,  # local models can be slow
            )
        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {_OLLAMA_BASE}.\n"
                "Make sure Ollama is running: `ollama serve`\n"
                f"And the model is pulled: `ollama pull {self._model}`"
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:400]}"
            )

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, model=self._model)

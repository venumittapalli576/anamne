"""Unified LLM client.

Wraps Claude (Anthropic) and Gemini (Google) behind one interface so the
agents don't have to know which provider they're talking to.

Why a thin wrapper instead of LiteLLM: less surface area, no extra
dependency, easier to read, and we only need text-in / text-out for now.
"""

from __future__ import annotations

from dataclasses import dataclass

from provenance.config import Settings, get_settings


@dataclass
class LLMResponse:
    text: str
    model: str


class LLMClient:
    """Picks Claude or Gemini based on which key is set in config.

    Priority: ANTHROPIC_API_KEY > GEMINI_API_KEY.
    Raises a clear error if neither is set.
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
            self._model = self._cfg.model or "gemini-2.5-flash"
            # google-genai uses GEMINI_API_KEY or GOOGLE_API_KEY automatically;
            # passing api_key explicitly keeps it predictable.
            self._client = genai.Client(api_key=self._cfg.gemini_api_key)
        else:
            raise RuntimeError(
                "No LLM API key configured. Set ANTHROPIC_API_KEY or GEMINI_API_KEY. "
                "Run `provenance init` for an interactive setup."
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

        # gemini
        from google.genai import types
        result = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        text = result.text or ""
        return LLMResponse(text=text, model=self._model)

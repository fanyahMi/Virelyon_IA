"""Fournisseurs LLM. Un seul indispensable : Anthropic (Claude).

Le provider est injecté via `get_provider` (dépendance FastAPI) pour être
facilement mocké dans les tests — aucun appel réseau réel en test.
"""
from __future__ import annotations

from typing import Protocol

from anthropic import AsyncAnthropic

from app.core.config import get_settings


class LLMNotConfiguredError(RuntimeError):
    """Levée quand aucune clé LLM n'est configurée (→ 503 côté endpoint)."""


class LLMProvider(Protocol):
    async def generate(
        self, model: str, system: str, user: str, max_tokens: int
    ) -> tuple[str, int, int]:
        """Retourne (texte, input_tokens, output_tokens)."""
        ...


class AnthropicProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key or ""
        self._client = AsyncAnthropic(api_key=self._api_key or "placeholder")

    async def generate(
        self, model: str, system: str, user: str, max_tokens: int
    ) -> tuple[str, int, int]:
        if not self._api_key:
            raise LLMNotConfiguredError("ANTHROPIC_API_KEY non configurée.")
        resp = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        return text, resp.usage.input_tokens, resp.usage.output_tokens


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Singleton lazy — surchargé par app.dependency_overrides dans les tests."""
    global _provider
    if _provider is None:
        _provider = AnthropicProvider(get_settings().anthropic_api_key)
    return _provider

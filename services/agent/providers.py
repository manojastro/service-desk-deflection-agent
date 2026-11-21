from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from apps.api.app.config import Settings


@dataclass(frozen=True)
class ModelResult:
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


class LLMProvider(ABC):
    @abstractmethod
    def structured(self, system: str, user: str, schema_name: str) -> ModelResult:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic provider used by automated tests and the credential-free demo."""

    def structured(self, system: str, user: str, schema_name: str) -> ModelResult:
        started = time.perf_counter()
        data = {"schema": schema_name, "mode": "deterministic", "accepted": True}
        return ModelResult(
            data=data,
            input_tokens=max(1, len((system + user).split())),
            output_tokens=8,
            latency_ms=(time.perf_counter() - started) * 1000,
            cost_usd=0.0001,
        )


class OpenAICompatibleProvider(LLMProvider):
    """Small OpenAI-compatible adapter. It is never selected without an API key."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def structured(self, system: str, user: str, schema_name: str) -> ModelResult:
        if not self.settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required for the configured provider")
        started = time.perf_counter()
        response = httpx.post(
            f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json={
                "model": self.settings.llm_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {})
        content = body["choices"][0]["message"]["content"]
        return ModelResult(
            data=json.loads(content),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=(time.perf_counter() - started) * 1000,
            cost_usd=0.0,
        )


def provider_for(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    return OpenAICompatibleProvider(settings)


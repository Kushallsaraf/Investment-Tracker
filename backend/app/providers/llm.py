"""Chat models for the AI analyst: Ollama on this computer, or any OpenAI-compatible API.

Both stream text as it is generated. Errors never include request URLs or headers, so an API key
can't end up in a message.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Protocol

import httpx

KEEP_ALIVE = "15m"  # keep the model loaded between questions so follow-ups start quickly


class LlmUnavailableError(RuntimeError):
    pass


class ChatModel(Protocol):
    provider: str
    model: str
    local: bool

    def status(self) -> dict[str, Any]: ...

    def stream(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]: ...


class OllamaClient:
    provider = "Ollama"
    local = True

    def __init__(self, base_url: str, model: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=httpx.Timeout(10, read=300))

    def status(self) -> dict[str, Any]:
        try:
            response = self.client.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
        except httpx.HTTPError:
            return {
                "ready": False,
                "reason": "Ollama isn't running. Open the Ollama app or run `ollama serve`.",
            }
        installed = [row["name"] for row in response.json().get("models", [])]
        if self.model not in installed and f"{self.model}:latest" not in installed:
            return {
                "ready": False,
                "reason": f"{self.model} isn't downloaded. Run `ollama pull {self.model}`.",
                "installed": installed,
            }
        return {"ready": True, "installed": installed}

    def stream(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
        try:
            with self.client.stream("POST", f"{self.base_url}/api/chat", json=body) as response:
                if response.status_code >= 400:
                    raise LlmUnavailableError(f"Ollama returned HTTP {response.status_code}")
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise LlmUnavailableError(str(chunk["error"]))
                    text = (chunk.get("message") or {}).get("content")
                    if text:
                        yield text
                    if chunk.get("done"):
                        return
        except httpx.HTTPError as exc:
            raise LlmUnavailableError(f"Ollama could not be reached ({type(exc).__name__})") from None


class OpenAICompatibleClient:
    """Groq, Gemini's OpenAI endpoint, OpenRouter, and similar services."""

    provider = "OpenAI-compatible API"
    local = False

    def __init__(
        self, base_url: str | None, api_key: str | None, model: str, client: httpx.Client | None = None
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=httpx.Timeout(10, read=120))

    def status(self) -> dict[str, Any]:
        if not self.base_url or not self.api_key:
            return {"ready": False, "reason": "Set AI_BASE_URL and AI_API_KEY in .env to use a cloud model."}
        return {"ready": True}

    def stream(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        if not self.base_url or not self.api_key:
            raise LlmUnavailableError("Set AI_BASE_URL and AI_API_KEY in .env to use a cloud model")
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with self.client.stream(
                "POST", f"{self.base_url}/chat/completions", json=body, headers=headers
            ) as response:
                if response.status_code >= 400:
                    raise LlmUnavailableError(f"The AI service returned HTTP {response.status_code}")
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    choices = json.loads(data).get("choices") or [{}]
                    text = (choices[0].get("delta") or {}).get("content")
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise LlmUnavailableError(f"The AI service could not be reached ({type(exc).__name__})") from None


def build_chat_model(settings: Any) -> ChatModel:
    if settings.ai_provider == "openai":
        return OpenAICompatibleClient(settings.ai_base_url, settings.ai_api_key, settings.ai_model)
    return OllamaClient(settings.ollama_url, settings.ai_model)

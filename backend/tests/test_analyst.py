from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.database import Database
from app.main import analyst_service, app
from app.providers.llm import LlmUnavailableError, OllamaClient, OpenAICompatibleClient
from app.services.container import Services, build_services
from fakes import FakeHistory, FakePrices, FakeSec, listing, synthetic_bars
from fastapi.testclient import TestClient

WRITE = {"X-Portfolio-Manager": "local-ui"}


class FakeModel:
    provider = "Fake"
    model = "fake-7b"
    local = True

    def __init__(self, *, ready: bool = True, fail_midway: bool = False) -> None:
        self.ready = ready
        self.fail_midway = fail_midway
        self.calls: list[list[dict[str, str]]] = []

    def status(self) -> dict[str, Any]:
        return {"ready": True} if self.ready else {"ready": False, "reason": "Ollama isn't running."}

    def stream(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        self.calls.append(messages)
        yield "ACME is in an "
        if self.fail_midway:
            raise LlmUnavailableError("Ollama could not be reached (ReadTimeout)")
        yield "uptrend."


class StaticNews:
    def headlines(self, symbol: str) -> dict[str, Any]:
        return {"items": [], "failures": {}}


def _services(tmp_path: Path, model: FakeModel) -> Services:
    return build_services(
        Database(tmp_path / "analyst.sqlite3"),
        history=FakeHistory({"ACME": {"meta": listing("Acme Corporation"), "bars": synthetic_bars(300)}}),
        prices=FakePrices(),
        sec_client=FakeSec(),
        news=StaticNews(),
        scorer=None,
        chat_model=model,
    )


def test_fact_pack_covers_every_section_with_dates(tmp_path: Path) -> None:
    services = _services(tmp_path, FakeModel())
    services.portfolio.upsert_position(
        symbol="ACME", quantity="3", average_cost="90", account_name="Brokerage"
    )
    services.journal.add_note("ACME", "Watching the 200-day average.")
    pack = services.analyst.facts("acme")
    assert pack["symbol"] == "ACME"
    titles = [section["title"] for section in pack["sections"]]
    assert titles == [
        "Price and trend",
        "Valuation (SEC filings)",
        "Insider activity",
        "News this week",
        "The investor's own records",
    ]
    text = pack["text"]
    assert "Trend: Uptrend" in text
    assert "(as of 2026-06-30)" in text  # SEC metrics keep their dates
    assert "Form 4 filings" in text
    assert "No headlines in the last 7 days." in text
    assert "holds 3 shares at an average cost of 90" in text
    assert "Watching the 200-day average." in text
    assert len(text) < 3_000  # small enough for a local model to read quickly


def test_chat_sends_rules_facts_and_the_recent_conversation(tmp_path: Path) -> None:
    model = FakeModel()
    services = _services(tmp_path, model)
    history = [{"role": "user", "content": f"question {index}"} for index in range(10)]
    answer = "".join(services.analyst.chat("ACME", history))
    assert answer == "ACME is in an uptrend."
    system, *conversation = model.calls[0]
    assert system["role"] == "system"
    assert "Never tell the investor to buy, sell, or hold" in system["content"]
    assert "## Price and trend" in system["content"]
    assert [row["content"] for row in conversation] == [f"question {index}" for index in range(4, 10)]

    with pytest.raises(ValueError, match="end with a question"):
        services.analyst.chat("ACME", [{"role": "assistant", "content": "Hi"}])
    with pytest.raises(LlmUnavailableError, match="isn't running"):
        _services(tmp_path / "down", FakeModel(ready=False)).analyst.chat("ACME", history)


def test_a_dropped_stream_ends_with_a_visible_note(tmp_path: Path) -> None:
    services = _services(tmp_path, FakeModel(fail_midway=True))
    answer = "".join(services.analyst.chat("ACME", [{"role": "user", "content": "Setup?"}]))
    assert answer.startswith("ACME is in an ")
    assert answer.endswith("[The answer stopped early: Ollama could not be reached (ReadTimeout)]")


def test_chat_route_streams_text_and_reports_setup_problems(tmp_path: Path) -> None:
    services = _services(tmp_path, FakeModel())
    app.dependency_overrides[analyst_service] = lambda: services.analyst
    try:
        client = TestClient(app)
        body = {"messages": [{"role": "user", "content": "Explain the setup"}]}
        assert client.post("/api/ai/ACME/chat", json=body).status_code == 403
        response = client.post("/api/ai/ACME/chat", json=body, headers=WRITE)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == "ACME is in an uptrend."
        assert client.post("/api/ai/XIC.TO/chat", json=body, headers=WRITE).status_code == 422
        status = client.get("/api/ai/status").json()
        assert (status["model"], status["ready"], len(status["quick_prompts"])) == ("fake-7b", True, 5)
        assert client.get("/api/ai/ACME/facts").json()["symbol"] == "ACME"

        down = _services(tmp_path / "down", FakeModel(ready=False))
        app.dependency_overrides[analyst_service] = lambda: down.analyst
        failed = client.post("/api/ai/ACME/chat", json=body, headers=WRITE)
        assert (failed.status_code, failed.json()["detail"]) == (503, "Ollama isn't running.")
    finally:
        app.dependency_overrides.clear()


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_client_streams_and_checks_the_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})
        body = json.loads(request.content)
        assert (body["keep_alive"], body["options"]["num_predict"]) == ("15m", 50)
        lines = [{"message": {"content": "Hello "}}, {"message": {"content": "there"}}, {"done": True}]
        return httpx.Response(200, content="\n".join(json.dumps(line) for line in lines))

    client = OllamaClient("http://ollama.test", "qwen2.5:7b", _client(handler))
    assert client.status()["ready"] is True
    assert "".join(client.stream([{"role": "user", "content": "hi"}], max_tokens=50)) == "Hello there"
    missing = OllamaClient("http://ollama.test", "llama3:8b", _client(handler)).status()
    assert missing["ready"] is False and "ollama pull llama3:8b" in missing["reason"]

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert "isn't running" in OllamaClient("http://ollama.test", "m", _client(offline)).status()["reason"]


def test_cloud_client_streams_server_sent_events_without_leaking_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-key"
        if json.loads(request.content)["model"] == "broken":
            return httpx.Response(401, json={"error": "bad key secret-key"})
        events = [
            {"choices": [{"delta": {"content": "Rates "}}]},
            {"choices": [{"delta": {}}]},
            {"choices": [{"delta": {"content": "rose."}}]},
        ]
        content = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        return httpx.Response(200, content=content)

    client = OpenAICompatibleClient("https://ai.test/v1", "secret-key", "fast-model", _client(handler))
    assert "".join(client.stream([{"role": "user", "content": "hi"}], max_tokens=50)) == "Rates rose."
    broken = OpenAICompatibleClient("https://ai.test/v1", "secret-key", "broken", _client(handler))
    with pytest.raises(LlmUnavailableError) as error:
        "".join(broken.stream([{"role": "user", "content": "hi"}], max_tokens=50))
    assert str(error.value) == "The AI service returned HTTP 401"
    assert "secret-key" not in str(error.value)
    assert OpenAICompatibleClient(None, None, "m").status()["ready"] is False

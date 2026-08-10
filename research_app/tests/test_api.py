from __future__ import annotations

import json

from fastapi.testclient import TestClient

import api


def test_health() -> None:
    with TestClient(api.app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["sources"] == ["arxiv", "semantic_scholar"]


def test_streaming_chat(monkeypatch) -> None:
    async def fake_stream(self, message: str):
        yield "[Planner] Ready.\n"
        yield "# Research report\n"

    monkeypatch.setattr(api.ResearchChatbot, "respond_stream", fake_stream)
    with TestClient(api.app) as client:
        response = client.post(
            "/api/chat/stream",
            json={"message": "Vietnamese NLP", "session_id": "test-session"},
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [item["type"] for item in events] == [
        "session",
        "status",
        "content",
        "done",
    ]

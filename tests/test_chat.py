"""Authenticated chat persistence. Gemini/LangGraph are mocked."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import auth_headers, signup_and_login
from src.search_engine.rag.answering import AnswerStatus, RagAnswerResult, SourceReference
from src.search_engine.rag.generation import RagGenerationError
from src.search_engine.main import AgentStreamMetadata
from src.search_engine.services.retrieval_service import (
    RetrievalDocumentAccessError,
    RetrievalDocumentUnavailableError,
)


def _rag_result(status: AnswerStatus = AnswerStatus.ANSWERED) -> RagAnswerResult:
    source = SourceReference(
        label="S1",
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="project.pdf",
        page_number=2,
        rank=1,
        cosine_similarity=0.9,
        evidence_excerpt="The project improves service speed.",
    )
    citations = (source,) if status is AnswerStatus.ANSWERED else ()
    return RagAnswerResult(
        status=status,
        answer=(
            "It improves service speed [S1]."
            if citations
            else "The answer cannot be established from the available documents."
        ),
        citations=citations,
        sources=(source,),
        retrieved_chunk_count=1,
        context_token_count=20,
    )


def test_chat_requires_access_token(client: TestClient) -> None:
    response = client.post("/chat", json={"query": "hello"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated."


def test_latest_conversation_requires_access_token(client: TestClient) -> None:
    response = client.get("/api/conversations/latest")
    assert response.status_code == 401


def test_refresh_token_cannot_call_chat(client: TestClient) -> None:
    _, tokens = signup_and_login(client)
    refresh = tokens["refresh_token"]
    response = client.post(
        "/chat",
        json={"query": "hello"},
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert response.status_code == 401


@patch("src.search_engine.api.graph_app.invoke", return_value={"answer": "Paris"})
def test_chat_persists_for_the_authenticated_user(
    mock_invoke,
    client: TestClient,
) -> None:
    headers = auth_headers(client)
    response = client.post(
        "/chat",
        json={"query": "What is the capital of France?", "session_id": "forged-id"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Paris"
    assert body["conversation_id"]
    mock_invoke.assert_called_once()
    graph_input = mock_invoke.call_args.args[0]
    assert graph_input["session_id"] == body["conversation_id"]
    assert graph_input["query"] == "What is the capital of France?"
    assert graph_input["history"] == []
    assert "forged-id" not in graph_input["session_id"]

    latest = client.get("/api/conversations/latest", headers=headers)
    assert latest.status_code == 200
    data = latest.json()
    assert data["conversation_id"] == body["conversation_id"]
    assert [item["role"] for item in data["messages"]] == ["user", "assistant"]
    assert data["messages"][0]["content"] == "What is the capital of France?"
    assert data["messages"][1]["content"] == "Paris"


@patch("src.search_engine.api.graph_app.invoke")
def test_general_chat_persists_only_tool_verified_web_citations(
    mock_invoke,
    client: TestClient,
) -> None:
    source = {
        "origin": "web",
        "title": "Official report",
        "url": "https://example.com/report",
        "evidence_excerpt": "Supporting evidence.",
        "published_date": "2026-10-30",
        "retrieved_at": "2026-10-31T10:00:00+00:00",
        "publisher": "example.com",
        "author": None,
        "source_type": "unspecified",
        "quality_notes": ["Direct evidence excerpt is available."],
    }
    conflict = {
        "status": "potential_conflict",
        "reason": "Comparable claims differ.",
        "shared_context_terms": ["funding", "round"],
        "claims": [
            {
                "value": "50",
                "currency": "USD",
                "unit": "million",
                "years": ["2026"],
                "source_title": "Official report",
                "source_url": "https://example.com/report",
                "evidence_excerpt": "Funding was $50 million.",
            },
            {
                "value": "80",
                "currency": "USD",
                "unit": "million",
                "years": ["2026"],
                "source_title": "Second report",
                "source_url": "https://other.example/report",
                "evidence_excerpt": "Funding was $80 million.",
            },
        ],
    }
    mock_invoke.return_value = {
        "answer": "The report supports the claim.",
        "web_sources": [source],
        "evidence_conflicts": [conflict],
    }
    headers = auth_headers(client)
    response = client.post("/chat", json={"query": "Research this"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["web_citations"] == [source]
    assert response.json()["evidence_conflicts"][0]["status"] == "potential_conflict"
    latest = client.get("/api/conversations/latest", headers=headers).json()
    assert latest["messages"][1]["web_citations"] == [source]
    assert latest["messages"][1]["evidence_conflicts"][0]["claims"][1]["value"] == "80"


@patch("src.search_engine.api.graph_app.invoke", return_value={"answer": "secret-answer"})
def test_user_cannot_use_another_users_conversation(
    mock_invoke,
    client: TestClient,
) -> None:
    owner_headers = auth_headers(client)
    created = client.post(
        "/chat",
        json={"query": "owner question"},
        headers=owner_headers,
    )
    assert created.status_code == 200
    conversation_id = created.json()["conversation_id"]

    other_headers = auth_headers(client)
    stolen = client.post(
        "/chat",
        json={"query": "intruder", "conversation_id": conversation_id},
        headers=other_headers,
    )
    assert stolen.status_code == 404
    assert stolen.json()["error"] == "Conversation not found."

    latest_other = client.get("/api/conversations/latest", headers=other_headers)
    assert latest_other.status_code == 200
    assert latest_other.json()["conversation_id"] is None
    assert latest_other.json()["messages"] == []

    latest_owner = client.get("/api/conversations/latest", headers=owner_headers)
    assert latest_owner.json()["conversation_id"] == conversation_id
    assert latest_owner.json()["messages"][0]["content"] == "owner question"


@patch("src.search_engine.api.graph_app.invoke", return_value={"answer": "ok"})
def test_unknown_conversation_is_not_found(mock_invoke, client: TestClient) -> None:
    headers = auth_headers(client)
    response = client.post(
        "/chat",
        json={"query": "hello", "conversation_id": str(uuid4())},
        headers=headers,
    )
    assert response.status_code == 404
    mock_invoke.assert_not_called()


@patch(
    "src.search_engine.api.stream_agent",
    side_effect=lambda session_id, query, history=None, research_mode="standard": iter(["Hel", "lo"]),
)
def test_stream_persists_assistant_answer(mock_stream, client: TestClient) -> None:
    headers = auth_headers(client)
    response = client.post(
        "/chat/stream",
        json={"query": "stream this"},
        headers=headers,
    )
    assert response.status_code == 200
    assert b"Hel" in response.content
    assert b"lo" in response.content
    mock_stream.assert_called_once()

    latest = client.get("/api/conversations/latest", headers=headers)
    data = latest.json()
    assert [item["role"] for item in data["messages"]] == ["user", "assistant"]
    assert data["messages"][1]["content"] == "Hello"


@patch("src.search_engine.api.stream_agent")
def test_stream_emits_and_persists_web_citation_metadata(
    mock_stream,
    client: TestClient,
) -> None:
    source = {
        "origin": "web",
        "title": "Source",
        "url": "https://example.com/source",
        "evidence_excerpt": "Evidence",
        "published_date": None,
        "retrieved_at": "2026-10-31T10:00:00+00:00",
    }
    mock_stream.return_value = iter(
        ["Answer", AgentStreamMetadata((source,))]
    )
    headers = auth_headers(client)
    response = client.post(
        "/chat/stream",
        json={"query": "Search"},
        headers=headers,
    )

    assert response.status_code == 200
    assert '"web_citations": [' in response.text
    latest = client.get("/api/conversations/latest", headers=headers).json()
    assert latest["messages"][1]["web_citations"][0]["url"] == source["url"]


@patch("src.search_engine.api.graph_app.invoke")
def test_general_follow_up_uses_bounded_persisted_history(
    mock_invoke,
    client: TestClient,
) -> None:
    mock_invoke.side_effect = [
        {"answer": "Ada Lovelace."},
        {"answer": "She worked on the Analytical Engine."},
    ]
    headers = auth_headers(client)
    first = client.post(
        "/chat",
        json={"query": "Who was the first programmer?"},
        headers=headers,
    )
    conversation_id = first.json()["conversation_id"]
    second = client.post(
        "/chat",
        json={
            "query": "Tell me more about her.",
            "conversation_id": conversation_id,
        },
        headers=headers,
    )

    assert second.status_code == 200
    follow_up_state = mock_invoke.call_args_list[1].args[0]
    assert follow_up_state["history"] == [
        ("user", "Who was the first programmer?"),
        ("assistant", "Ada Lovelace."),
    ]


@patch("src.search_engine.api.graph_app.invoke")
def test_deep_research_is_explicit_and_plan_survives_reload(
    mock_invoke,
    client: TestClient,
) -> None:
    mock_invoke.return_value = {
        "answer": "Comparison",
        "research_plan": ["Compare features", "Compare costs"],
        "research_summary": {
            "search_count": 2,
            "search_failures": 0,
            "termination_reason": "sufficient_evidence",
        },
    }
    headers = auth_headers(client)
    response = client.post(
        "/chat",
        json={"query": "Compare A and B", "research_mode": "deep"},
        headers=headers,
    )

    assert response.status_code == 200
    assert mock_invoke.call_args.args[0]["research_mode"] == "deep"
    assert response.json()["research_plan"] == ["Compare features", "Compare costs"]
    assert response.json()["research_summary"]["search_count"] == 2
    latest = client.get("/api/conversations/latest", headers=headers).json()
    assert latest["messages"][1]["research_plan"] == [
        "Compare features",
        "Compare costs",
    ]
    assert latest["messages"][1]["research_summary"]["termination_reason"] == (
        "sufficient_evidence"
    )


def test_document_chat_rejects_deep_research(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"query": "question", "mode": "documents", "research_mode": "deep"},
        headers=auth_headers(client),
    )
    assert response.status_code == 400


@patch("src.search_engine.api.resolve_chat_attachments", new_callable=AsyncMock)
@patch("src.search_engine.api.RagAnswerService.answer", new_callable=AsyncMock)
def test_document_chat_uses_rag_once_and_persists_attribution(
    mock_answer: AsyncMock,
    mock_attachments: AsyncMock,
    client: TestClient,
) -> None:
    mock_answer.return_value = _rag_result()
    headers = auth_headers(client)
    document_id = uuid4()
    mock_attachments.return_value = [
        {
            "document_id": str(document_id),
            "filename": "project.pdf",
            "content_type": "application/pdf",
            "file_size": 1234,
            "processing_status": "completed",
            "indexing_status": "completed",
        }
    ]
    response = client.post(
        "/chat",
        json={
            "query": "What is the goal?",
            "mode": "documents",
            "document_ids": [str(document_id)],
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "documents"
    assert body["status"] == "answered"
    assert body["citations"][0]["filename"] == "project.pdf"
    mock_answer.assert_awaited_once()
    assert mock_answer.await_args.kwargs["document_ids"] == [document_id]

    latest = client.get("/api/conversations/latest", headers=headers).json()
    assert latest["messages"][0]["mode"] == "documents"
    assert latest["messages"][0]["document_ids"] == [str(document_id)]
    assert latest["messages"][0]["attachments"][0]["filename"] == "project.pdf"
    assert latest["messages"][1]["status"] == "answered"
    assert latest["messages"][1]["citations"][0]["label"] == "S1"


@patch("src.search_engine.api.RagAnswerService.answer", new_callable=AsyncMock)
def test_document_stream_uses_one_completed_answer_event(
    mock_answer: AsyncMock,
    client: TestClient,
) -> None:
    mock_answer.return_value = _rag_result(AnswerStatus.INSUFFICIENT_EVIDENCE)
    response = client.post(
        "/chat/stream",
        json={"query": "Unknown?", "mode": "documents"},
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    text = response.content.decode()
    assert '"mode": "documents"' in text
    assert '"status": "insufficient_evidence"' in text
    assert '"delta": "The answer cannot be established' in text
    mock_answer.assert_awaited_once()


@patch("src.search_engine.api.RagAnswerService.answer", new_callable=AsyncMock)
def test_document_stream_serializes_answered_citations(
    mock_answer: AsyncMock,
    client: TestClient,
) -> None:
    mock_answer.return_value = _rag_result()
    response = client.post(
        "/chat/stream",
        json={"query": "Goal?", "mode": "documents"},
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    text = response.content.decode()
    assert '"citations": [{"label": "S1"' in text
    assert '"filename": "project.pdf"' in text


@patch("src.search_engine.api.RagAnswerService.answer", new_callable=AsyncMock)
def test_foreign_document_error_is_sanitized(
    mock_answer: AsyncMock,
    client: TestClient,
) -> None:
    mock_answer.side_effect = RetrievalDocumentAccessError("foreign secret")
    response = client.post(
        "/chat",
        json={
            "query": "Steal it",
            "mode": "documents",
            "document_ids": [str(uuid4())],
        },
        headers=auth_headers(client),
    )
    assert response.status_code == 404
    assert response.json() == {"error": "One or more selected documents are unavailable."}
    assert "foreign secret" not in response.text


@pytest.mark.parametrize(
    ("error", "status_code", "message"),
    [
        (
            RetrievalDocumentUnavailableError("internal status"),
            409,
            "One or more selected documents are not indexed and available.",
        ),
        (
            RagGenerationError("provider secret"),
            503,
            "The document answer could not be generated. Please try again.",
        ),
    ],
)
@patch("src.search_engine.api.RagAnswerService.answer", new_callable=AsyncMock)
def test_document_chat_failures_are_explicit_and_sanitized(
    mock_answer: AsyncMock,
    error: Exception,
    status_code: int,
    message: str,
    client: TestClient,
) -> None:
    mock_answer.side_effect = error
    response = client.post(
        "/chat",
        json={"query": "question", "mode": "documents"},
        headers=auth_headers(client),
    )
    assert response.status_code == status_code
    assert response.json() == {"error": message}
    assert str(error) not in response.text


def test_general_mode_rejects_accidental_document_scope(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={
            "query": "hello",
            "mode": "general",
            "document_ids": [str(uuid4())],
        },
        headers=auth_headers(client),
    )
    assert response.status_code == 400

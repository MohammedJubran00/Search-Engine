"""Bounded, opt-in LangGraph research planning tests with fake providers."""

from unittest.mock import patch
import time

from langchain_core.messages import AIMessage

from src.search_engine.main import (
    PlannerOutput,
    ResearchBudget,
    _ACTIVE_RESEARCH_BUDGET,
    _clean_research_plan,
    app,
    research_summary,
    web_search,
)


def test_plan_cleanup_deduplicates_and_enforces_bound() -> None:
    plan = _clean_research_plan(
        [" AWS services ", "aws services", "Azure services", "Pricing", "Operations"]
    )
    assert plan == ["AWS services", "Azure services", "Pricing", "Operations"]


@patch("src.search_engine.main.agent.invoke")
@patch("src.search_engine.main.planner_model")
def test_standard_question_skips_planner(mock_planner, mock_agent) -> None:
    mock_agent.return_value = {"messages": [AIMessage(content="Direct answer")]}
    result = app.invoke(
        {
            "session_id": "standard",
            "query": "Hello",
            "history": [],
            "research_mode": "standard",
        }
    )

    assert result["answer"] == "Direct answer"
    mock_planner.invoke.assert_not_called()


@patch("src.search_engine.main.agent.invoke")
@patch("src.search_engine.main.planner_model")
@patch("src.search_engine.main.tavily")
def test_deep_research_uses_typed_bounded_plan(mock_tavily, mock_planner, mock_agent) -> None:
    mock_tavily.invoke.return_value = {"results": []}
    mock_planner.invoke.return_value = PlannerOutput(
        subquestions=["AWS services", "Azure services", "Pricing assumptions"]
    )
    mock_agent.return_value = {"messages": [AIMessage(content="Comparison")]}
    result = app.invoke(
        {
            "session_id": "deep",
            "query": "Compare AWS and Azure",
            "history": [],
            "research_mode": "deep",
        }
    )

    assert result["research_plan"] == [
        "AWS services",
        "Azure services",
        "Pricing assumptions",
    ]
    sent_messages = mock_agent.call_args.args[0]["messages"]
    assert any("Deep Research plan" in message[1] for message in sent_messages)
    assert mock_tavily.invoke.call_count == 3
    assert mock_agent.call_args.kwargs["config"]["recursion_limit"] > 0


@patch("src.search_engine.main.agent.invoke")
@patch("src.search_engine.main.planner_model")
@patch("src.search_engine.main.tavily")
def test_planner_failure_degrades_to_original_question(mock_tavily, mock_planner, mock_agent) -> None:
    mock_tavily.invoke.return_value = {"results": []}
    mock_planner.invoke.side_effect = RuntimeError("quota")
    mock_agent.return_value = {"messages": [AIMessage(content="Fallback answer")]}
    result = app.invoke(
        {
            "session_id": "fallback",
            "query": "Complex question",
            "history": [],
            "research_mode": "deep",
        }
    )

    assert result["planning_failed"] is True
    assert result["research_plan"] == ["Complex question"]


@patch("src.search_engine.main.tavily")
def test_search_budget_deduplicates_queries_and_stops_runaway_calls(mock_search) -> None:
    mock_search.invoke.return_value = {
        "results": [
            {"title": "Source", "url": "https://example.com", "content": "Evidence"}
        ]
    }
    budget = ResearchBudget(max_searches=2, deadline=time.monotonic() + 60)
    token = _ACTIVE_RESEARCH_BUDGET.set(budget)
    try:
        first = web_search.invoke("AWS pricing")
        duplicate = web_search.invoke("  aws   pricing ")
        web_search.invoke("Azure pricing")
        stopped = web_search.invoke("Third distinct search")
    finally:
        _ACTIVE_RESEARCH_BUDGET.reset(token)

    assert first == duplicate
    assert mock_search.invoke.call_count == 2
    assert "budget" in stopped
    summary = research_summary(budget)
    assert summary == {
        "search_count": 2,
        "search_failures": 0,
        "tavily_seconds": summary["tavily_seconds"],
        "termination_reason": "search_budget_exhausted",
    }
    assert summary["tavily_seconds"] >= 0


@patch("src.search_engine.main.tavily")
def test_partial_search_failure_is_safe_and_counted(mock_search) -> None:
    mock_search.invoke.side_effect = RuntimeError("provider")
    budget = ResearchBudget(max_searches=2, deadline=time.monotonic() + 60)
    token = _ACTIVE_RESEARCH_BUDGET.set(budget)
    try:
        result = web_search.invoke("query")
    finally:
        _ACTIVE_RESEARCH_BUDGET.reset(token)

    assert "unavailable" in result
    assert budget.failure_count == 1
    assert research_summary(budget)["termination_reason"] == "partial_search_failure"

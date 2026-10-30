"""Bounded, opt-in LangGraph research planning tests with fake providers."""

from unittest.mock import patch

from langchain_core.messages import AIMessage

from src.search_engine.main import PlannerOutput, _clean_research_plan, app


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
def test_deep_research_uses_typed_bounded_plan(mock_planner, mock_agent) -> None:
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
    assert "Deep Research plan" in sent_messages[-2][1]


@patch("src.search_engine.main.agent.invoke")
@patch("src.search_engine.main.planner_model")
def test_planner_failure_degrades_to_original_question(mock_planner, mock_agent) -> None:
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

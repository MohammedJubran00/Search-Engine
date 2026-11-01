"""Monthly aggregation must not silently cap active accounts at 5000 events."""
import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.search_engine.repositories.usage_repository import UsageRepository


def test_monthly_usage_counts_all_events_and_provider_tokens():
    now = datetime.now(timezone.utc)
    platform = SimpleNamespace(provider='platform', status='success', latency_ms=100,
                               created_at=now, conversation_id=None, operation='chat', estimated=False)
    provider = SimpleNamespace(provider='gemini', status='success', latency_ms=10,
                               created_at=now, conversation_id=None, operation='generation', estimated=False,
                               input_tokens=7, output_tokens=3, embedding_tokens=None,
                               request_count=2, estimated_cost_usd=Decimal('0.01'))
    events = [platform] * 5001 + [provider]
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: events))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    snapshot = asyncio.run(UsageRepository(session).snapshot(uuid.uuid4()))
    assert snapshot['monthly_request_count'] == 5001
    assert snapshot['successful_requests'] == 5001
    assert snapshot['total_tokens'] == 10
    assert snapshot['gemini_generation_requests'] == 2
    assert snapshot['estimated_cost_usd'] == '0.01'
    assert snapshot['average_response_seconds'] == .1
    statement = session.execute.call_args.args[0]
    assert statement._limit_clause is None

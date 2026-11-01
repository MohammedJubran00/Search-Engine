"""Persistent, content-free usage event storage and aggregation."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.usage_event import UsageEvent


class UsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, *, request_id: uuid.UUID, user_id: uuid.UUID,
        conversation_id: uuid.UUID | None, provider: str, operation: str,
        status: str, model: str | None = None, input_tokens: int | None = None,
        output_tokens: int | None = None, embedding_tokens: int | None = None,
        request_count: int = 1, latency_ms: int | None = None,
        estimated: bool = False, estimated_cost_usd: Decimal | None = None,
    ) -> UsageEvent:
        event = UsageEvent(
            request_id=request_id, user_id=user_id, conversation_id=conversation_id,
            provider=provider, operation=operation, status=status, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            embedding_tokens=embedding_tokens, request_count=request_count,
            latency_ms=latency_ms, estimated=estimated,
            estimated_cost_usd=estimated_cost_usd,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def snapshot(self, user_id: uuid.UUID) -> dict:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events = list((await self._session.execute(
            select(UsageEvent).where(
                UsageEvent.user_id == user_id,
                UsageEvent.created_at >= month_start,
            ).order_by(UsageEvent.created_at.desc())
        )).scalars().all())
        platform = [event for event in events if event.provider == "platform"]
        provider = [event for event in events if event.provider != "platform"]
        successful = sum(event.status == "success" for event in platform)
        failed = sum(event.status == "error" for event in platform)
        latency = [event.latency_ms for event in platform if event.latency_ms is not None]

        def token_sum(field: str) -> int:
            return sum(int(getattr(event, field) or 0) for event in provider)

        by_conversation: dict[str, int] = {}
        daily: dict[str, int] = {}
        for event in platform:
            day = event.created_at.date().isoformat()
            daily[day] = daily.get(day, 0) + 1
            if event.conversation_id:
                key = str(event.conversation_id)
                by_conversation[key] = by_conversation.get(key, 0) + 1
        return {
            "retention": "persistent",
            "request_count": len(platform),
            "daily_request_count": sum(event.created_at >= day_start for event in platform),
            "monthly_request_count": len(platform),
            "successful_requests": successful,
            "failed_requests": failed,
            "average_response_seconds": round(sum(latency) / len(latency) / 1000, 4) if latency else 0,
            "input_tokens": token_sum("input_tokens"),
            "output_tokens": token_sum("output_tokens"),
            "total_tokens": token_sum("input_tokens") + token_sum("output_tokens"),
            "embedding_tokens": token_sum("embedding_tokens"),
            "gemini_generation_requests": sum(
                event.request_count for event in provider
                if event.provider == "gemini" and event.operation == "generation"
            ),
            "gemini_embedding_requests": sum(
                event.request_count for event in provider
                if event.provider == "gemini" and event.operation == "embedding"
            ),
            "tavily_searches": sum(
                event.request_count for event in provider if event.provider == "tavily"
            ),
            "estimated_cost_usd": str(sum(
                (event.estimated_cost_usd or Decimal("0")) for event in provider
            )),
            "usage_by_conversation": by_conversation,
            "daily_usage": [{"date": key, "requests": daily[key]} for key in sorted(daily)],
            "recent": [
                {
                    "provider": event.provider,
                    "operation": event.operation,
                    "status": event.status,
                    "created_at": event.created_at.isoformat(),
                    "estimated": event.estimated,
                }
                for event in events[:20]
            ],
        }

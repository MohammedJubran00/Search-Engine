"""Bounded, privacy-preserving local usage metrics and request ceilings."""

import asyncio
import time
import uuid
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from src.search_engine.core.config import settings


class UsageLimitError(RuntimeError):
    """Raised when a server-side local request ceiling is reached."""


@dataclass(slots=True)
class UsageRecord:
    user_id: uuid.UUID
    started: float
    recorded_at: str
    mode: str = "general"
    research_mode: str = "standard"
    status: str = "success"
    total_seconds: float = 0.0
    retrieval_seconds: float = 0.0
    generation_seconds: float = 0.0
    tavily_seconds: float = 0.0
    search_count: int = 0
    source_count: int = 0
    retrieved_chunk_count: int = 0
    citation_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    research_iterations: int = 0
    provider_error: bool = False
    quota_error: bool = False

    def mark_error(self, *, quota: bool = False) -> None:
        self.status = "error"
        self.provider_error = True
        self.quota_error = self.quota_error or quota


class ObservabilityService:
    """In-memory per-user metrics; never stores prompts, answers, or document text."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: dict[uuid.UUID, int] = defaultdict(int)
        self._daily: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
        self._events: dict[uuid.UUID, deque[dict]] = {}
        self._embedding_requests: dict[uuid.UUID, int] = defaultdict(int)

    async def begin(self, user_id: uuid.UUID) -> UsageRecord:
        day = datetime.now(timezone.utc).date().isoformat()
        async with self._lock:
            if self._daily[(user_id, day)] >= settings.usage_daily_request_limit:
                raise UsageLimitError("Daily local request limit reached.")
            if self._active[user_id] >= settings.usage_max_concurrent_requests:
                raise UsageLimitError("Concurrent request limit reached.")
            self._daily[(user_id, day)] += 1
            self._active[user_id] += 1
        return UsageRecord(
            user_id=user_id,
            started=time.perf_counter(),
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )

    async def finish(self, record: UsageRecord) -> None:
        record.total_seconds = max(0.0, time.perf_counter() - record.started)
        payload = asdict(record)
        payload.pop("user_id", None)
        payload.pop("started", None)
        async with self._lock:
            self._active[record.user_id] = max(0, self._active[record.user_id] - 1)
            events = self._events.setdefault(
                record.user_id,
                deque(maxlen=settings.usage_event_retention),
            )
            events.append(payload)

    async def record_embedding_request(self, user_id: uuid.UUID) -> None:
        async with self._lock:
            self._embedding_requests[user_id] += 1

    async def snapshot(self, user_id: uuid.UUID) -> dict:
        async with self._lock:
            events = list(self._events.get(user_id, ()))
            active = self._active[user_id]
            embeddings = self._embedding_requests[user_id]
            day = datetime.now(timezone.utc).date().isoformat()
            daily_count = self._daily[(user_id, day)]
        count = len(events)

        def average(field: str) -> float:
            return round(sum(float(item.get(field, 0)) for item in events) / count, 4) if count else 0.0

        by_mode = {"general": 0, "documents": 0, "deep_research": 0}
        for item in events:
            mode = item.get("mode")
            if mode == "documents":
                by_mode["documents"] += 1
            else:
                by_mode["general"] += 1
                if item.get("research_mode") == "deep":
                    by_mode["deep_research"] += 1

        return {
            "retention": "process_local_bounded",
            "request_count": count,
            "active_requests": active,
            "daily_request_count": daily_count,
            "daily_request_limit": settings.usage_daily_request_limit,
            "average_response_seconds": average("total_seconds"),
            "average_retrieval_seconds": average("retrieval_seconds"),
            "average_generation_seconds": average("generation_seconds"),
            "average_tavily_seconds": average("tavily_seconds"),
            "average_searches": average("search_count"),
            "average_sources": average("source_count"),
            "input_tokens": sum(int(item.get("input_tokens", 0)) for item in events),
            "output_tokens": sum(int(item.get("output_tokens", 0)) for item in events),
            "embedding_requests": embeddings,
            "error_count": sum(item.get("status") == "error" for item in events),
            "quota_error_count": sum(bool(item.get("quota_error")) for item in events),
            "modes": by_mode,
            "recent": events[-20:],
        }


observability = ObservabilityService()

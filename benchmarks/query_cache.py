"""Offline cache overhead measurement; no network, database, or paid calls."""
import asyncio
import statistics
import time

from src.search_engine.rag.embeddings import GeminiEmbeddingProvider, _query_cache


class FakeClient:
    def __init__(self):
        self.calls = 0

    async def aembed_query(self, text, **kwargs):
        self.calls += 1
        return [1.0] + [0.0] * 1535


async def main():
    client = FakeClient()
    provider = GeminiEmbeddingProvider(client=client)
    provider._cache_enabled = True
    _query_cache.clear()
    started = time.perf_counter()
    await provider.embed_query('cache benchmark unique query')
    miss_ms = (time.perf_counter() - started) * 1000
    hits = []
    for _ in range(100):
        started = time.perf_counter()
        await provider.embed_query('cache benchmark unique query')
        hits.append((time.perf_counter() - started) * 1000)
    print(f'fake_provider_calls={client.calls} miss_ms={miss_ms:.4f} '
          f'hit_median_ms={statistics.median(hits):.4f} hit_min_ms={min(hits):.4f} '
          f'hit_max_ms={max(hits):.4f} samples={len(hits)}')
    _query_cache.clear()


if __name__ == '__main__':
    asyncio.run(main())

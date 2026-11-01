"""Controlled local benchmarks. External providers are replaced before startup."""
import argparse
import asyncio
import csv
import hashlib
import json
import platform
import os
import re
from datetime import datetime, timezone
from importlib.metadata import version
import socket
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx
import uvicorn
from sqlalchemy import delete, text

from benchmarks.metrics import is_content, summary


def sanitized_plan(lines):
    return [re.sub(r"'\[[^']+\]'::vector", "'<synthetic vector>'::vector", re.sub(r'[0-9a-f]{8}-[0-9a-f-]{27,}', '<benchmark-id>', line)) for line in lines]


def process_memory():
    if os.name != 'nt':
        return {'status': 'unavailable: Windows process counters only'}
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ['PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage']]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return {'status': 'unavailable: process counter query failed'}
    return dict(working_set_bytes=counters.WorkingSetSize, peak_process_lifetime_working_set_bytes=counters.PeakWorkingSetSize)


def timed_async(target, name, measurements):
    original = getattr(target, name)
    async def measured(*args, **kwargs):
        start = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            measurements.append(time.perf_counter()-start)
    return patch.object(target, name, measured)


class MockEmbeddings:
    """Deterministic unit vectors, NOT semantic embeddings."""
    async def embed_query(self, value):
        vector = [0.0] * 1536
        vector[int.from_bytes(hashlib.sha256(value.encode()).digest()[:2]) % 1536] = 1.0
        return vector

    async def embed_documents(self, values):
        return [await self.embed_query(value) for value in values]


def mock_stream(*args, **kwargs):
    yield 'Controlled benchmark '
    yield 'assistant content.'


async def mock_document_answer(*args, **kwargs):
    from src.search_engine.rag.answering import AnswerStatus, RagAnswerResult
    return RagAnswerResult(status=AnswerStatus.ANSWERED, answer='Controlled synthetic document answer.',
                           citations=(), sources=(), retrieved_chunk_count=0, context_token_count=0)


def request_sample(client, method, endpoint, **kwargs):
    start = time.perf_counter()
    try:
        response = client.request(method, endpoint, **kwargs)
        return dict(seconds=time.perf_counter()-start, ok=response.is_success, bytes=len(response.content))
    except httpx.HTTPError as error:
        return dict(seconds=time.perf_counter()-start, ok=False, bytes=0, timeout=isinstance(error, httpx.TimeoutException))


def stream_sample(client, payload):
    start = time.perf_counter()
    first_event = first_content = None
    chunks = 0
    completed = False
    done_event = False
    try:
        with client.stream('POST', '/chat/stream', json=payload) as response:
            for line in response.iter_lines():
                if not line.startswith('data:'):
                    continue
                event = json.loads(line[5:])
                done_event = done_event or event.get('done') is True
                now = time.perf_counter()-start
                if first_event is None:
                    first_event = now
                if is_content(event):
                    chunks += 1
                    if first_content is None:
                        first_content = now
                if event.get('error'):
                    return dict(seconds=now, ok=False, chunks=chunks, first_event_seconds=first_event, ttft_seconds=first_content)
            completed = response.is_success and chunks > 0 and done_event
    except (httpx.HTTPError, ValueError):
        pass
    return dict(seconds=time.perf_counter()-start, ok=completed, chunks=chunks,
                first_event_seconds=first_event, ttft_seconds=first_content, interrupted=not completed)


async def database_bench(user_id, document_id, count):
    from src.search_engine.database.database import SessionLocal, engine
    from src.search_engine.services.document_indexing_service import DocumentIndexingService
    from src.search_engine.services.retrieval_service import SemanticRetrievalService
    embeddings = MockEmbeddings()
    async with SessionLocal() as session:
        indexer = DocumentIndexingService(session, embeddings=embeddings)
        embedding_times, persistence_times, preparation_times = [], [], []
        start = time.perf_counter()
        with timed_async(embeddings, 'embed_documents', embedding_times), timed_async(indexer._index, 'replace', persistence_times), timed_async(indexer, '_prepare_chunks', preparation_times):
            indexed = await indexer.index(document_id=document_id, user_id=user_id)
        indexing_seconds = time.perf_counter()-start
        service = SemanticRetrievalService(session, embeddings=embeddings)
        query_embedding_times, search_times = [], []
        samples = []
        for _ in range(count):
            start = time.perf_counter()
            with timed_async(embeddings, 'embed_query', query_embedding_times), timed_async(service._repository, 'search', search_times):
                rows = await service.retrieve(user_id=user_id, query='Controlled benchmark restaurant goals', top_k=5, document_ids=[document_id])
            samples.append(dict(seconds=time.perf_counter()-start, ok=True, chunks=len(rows)))
        version = await session.scalar(text('SHOW server_version'))
        indexes = (await session.execute(text("SELECT indexdef FROM pg_indexes WHERE tablename='document_chunks'"))).scalars().all()
        # EXPLAIN only the isolated user's generated rows; no source text returned.
        plan = (await session.execute(text('EXPLAIN (ANALYZE, BUFFERS) SELECT id FROM document_chunks WHERE document_id = :id'), {'id': document_id})).scalars().all()
        vector_plan = (await session.execute(text('EXPLAIN (ANALYZE, BUFFERS) SELECT c.id FROM document_chunks c JOIN documents d ON d.id=c.document_id JOIN document_index_states s ON s.document_id=d.id WHERE d.user_id=:owner AND d.id=:document AND s.status=\'completed\' AND c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(:vector AS vector), c.document_id, c.chunk_index, c.id LIMIT 5'), {'owner': user_id, 'document': document_id, 'vector': json.dumps(await embeddings.embed_query('Controlled benchmark restaurant goals'))})).scalars().all()
        result = dict(indexing=dict(seconds=indexing_seconds, chunk_count=indexed.chunk_count, chunks_per_second=indexed.chunk_count/indexing_seconds,
                                   parse_extract_chunk_seconds=sum(preparation_times), embedding_seconds=sum(embedding_times), persistence_seconds=sum(persistence_times),
                                   file_type='TXT', file_bytes=len(b'Controlled benchmark restaurant goals. '*100), provider='deterministic mock'),
                      retrieval=dict(summary=summary(samples, sum(item['seconds'] for item in samples)), samples=samples,
                                     query_embedding_seconds=query_embedding_times, vector_search_seconds=search_times,
                                     top_k=5, dimensions=1536, documents=1, database_version=version,
                                     indexes=list(indexes), explain_scope='document filter plus exact vector ranking plan', explain=sanitized_plan(plan)))
        result['retrieval']['vector_explain'] = sanitized_plan(vector_plan)
    await engine.dispose()
    return result


async def cleanup(user_id):
    from src.search_engine.database.database import SessionLocal, engine
    from src.search_engine.models.user import User
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()
    await engine.dispose()


def main():
    process_start, cpu_start = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument('--requests', type=int, default=10)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--concurrency', type=int, nargs='+', default=[1, 5])
    parser.add_argument('--output', type=Path, default=Path('benchmarks/reports'))
    args = parser.parse_args()
    if not 1 <= args.requests <= 200 or not 0 <= args.warmup <= 10 or any(not 1 <= n <= 50 for n in args.concurrency):
        parser.error('Limits: requests 1..200, warmup 0..10, concurrency 1..50')
    from src.search_engine.api import app
    from src.search_engine.core.config import settings
    report = dict(mode='local socket HTTP, mocked external providers', configuration=vars(args) | {'output': str(args.output)},
                  recorded_at=datetime.now(timezone.utc).isoformat(),
                  dependencies={name: version(name) for name in ['fastapi', 'uvicorn', 'sqlalchemy', 'asyncpg', 'pgvector', 'httpx']},
                  environment=dict(os=platform.platform(), python=platform.python_version(), cpu=platform.processor(), logical_cpu_count=os.cpu_count()),
                  results={}, skipped={
                      'real_providers': 'Not enabled; no paid calls authorized by this run.',
                      'retrieval_quality': 'No manually verified corpus labels supplied. Synthetic vectors are not a quality evaluation.',
                      'ann_comparison': 'No ANN implementation or measured before/after baseline.',
                      'gpu': 'Remote Gemini has no measurable local GPU usage.',
                      'agent_execution': 'Mock agent; no real LangGraph/model timing claim.',
                      'indexing_stages': 'Parse/extract/chunk measured together; persistence excludes final commit. Upload validation and parsing measured by HTTP upload duration.',
                      'stream_interrupts': 'Natural failures tracked; forced cancellation scenario not executed.',
                      'resources': 'Working set and lifetime peak measured on Windows; excludes PostgreSQL. GPU unavailable.',
                  })
    with tempfile.TemporaryDirectory(prefix='research-benchmark-') as storage, socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.listen(128)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        with patch.object(settings, 'indexing_worker_embedded_enabled', False), patch.object(settings, 'rag_storage_dir', Path(storage)), patch('src.search_engine.api.graph_app.invoke', return_value={'answer': 'Controlled benchmark answer.'}), patch('src.search_engine.api.stream_agent', mock_stream), patch('src.search_engine.api.RagAnswerService.answer', mock_document_answer):
            loops = []
            async def serve():
                loops.append(asyncio.get_running_loop())
                await server.serve(sockets=[sock])
            thread = threading.Thread(target=lambda: asyncio.run(serve()), daemon=True)
            thread.start()
            deadline = time.monotonic()+30
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError('Local server startup timed out')
                time.sleep(.05)
            user_id = None
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30) as client:
                    email = f'benchmark-{uuid.uuid4().hex}@example.com'
                    password = uuid.uuid4().hex + '!Aa1'
                    response = client.post('/api/auth/signup', json=dict(full_name='Isolated benchmark', email=email, password=password))
                    response.raise_for_status()
                    user_id = uuid.UUID(response.json()['id'])
                    tokens = client.post('/api/auth/login', json=dict(email=email, password=password))
                    tokens.raise_for_status()
                    client.headers['Authorization'] = 'Bearer ' + tokens.json()['access_token']
                    upload_start = time.perf_counter()
                    document = client.post('/api/documents/upload', files={'file': ('benchmark.txt', b'Controlled benchmark restaurant goals. '*100, 'text/plain')})
                    document.raise_for_status()
                    report['results']['upload_validation_parse_seconds'] = time.perf_counter()-upload_start
                    for endpoint in ['/api/auth/me', '/api/documents', '/api/conversations']:
                        for _ in range(args.warmup):
                            request_sample(client, 'GET', endpoint)
                        for concurrency in args.concurrency:
                            start = time.perf_counter()
                            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                                samples = list(pool.map(lambda _: request_sample(client, 'GET', endpoint), range(args.requests)))
                            report['results'][f'GET {endpoint} concurrency={concurrency}'] = summary(samples, time.perf_counter()-start)
                    for mode in ['standard', 'deep']:
                        for _ in range(args.warmup):
                            stream_sample(client, dict(query='Controlled warmup', research_mode=mode))
                        samples = [stream_sample(client, dict(query='Controlled benchmark question', research_mode=mode)) for _ in range(args.requests)]
                        report['results'][f'SSE {mode}'] = dict(summary=summary(samples, sum(s['seconds'] for s in samples)), samples=samples)
                    for _ in range(args.warmup):
                        request_sample(client, 'POST', '/chat', json={'query': 'Controlled mock question'})
                    start = time.perf_counter()
                    samples = [request_sample(client, 'POST', '/chat', json={'query': 'Controlled mock question'}) for _ in range(args.requests)]
                    report['results']['POST /chat concurrency=1'] = summary(samples, time.perf_counter()-start)
                    report['results']['database'] = asyncio.run_coroutine_threadsafe(database_bench(user_id, uuid.UUID(document.json()['id']), args.requests), loops[0]).result(timeout=60)
                    samples = [stream_sample(client, dict(query='Controlled document question', mode='documents', document_ids=[document.json()['id']])) for _ in range(args.requests)]
                    report['results']['SSE documents'] = dict(summary=summary(samples, sum(s['seconds'] for s in samples)), samples=samples,
                                                               caveat='Completed-answer delta; not native model token streaming')
            finally:
                if user_id:
                    asyncio.run_coroutine_threadsafe(cleanup(user_id), loops[0]).result(timeout=30)
                server.should_exit = True
                thread.join(timeout=30)
    args.output.mkdir(parents=True, exist_ok=True)
    elapsed = time.perf_counter()-process_start
    report['resources'] = dict(scope='application and benchmark harness share this process; PostgreSQL excluded',
                               duration_seconds=elapsed, cpu_seconds=time.process_time()-cpu_start,
                               average_single_core_cpu_percent=(time.process_time()-cpu_start)/elapsed*100)
    report['resources']['memory'] = process_memory()
    for key, result in report['results'].items():
        if key.startswith('SSE '):
            content = [dict(seconds=sample['ttft_seconds'], ok=sample['ok']) for sample in result['samples'] if sample.get('ttft_seconds') is not None]
            result['content_latency'] = summary(content, sum(item['seconds'] for item in content))
            for field in ['requests_per_second', 'bytes_per_second']:
                result['content_latency'].pop(field)
            result['completion_rate'] = sum(sample['ok'] for sample in result['samples'])/len(result['samples'])
    (args.output/'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (args.output/'results.csv').open('w', newline='', encoding='utf-8') as destination:
        writer = csv.writer(destination)
        writer.writerow(['measurement', 'data_json'])
        for key, value in report['results'].items():
            writer.writerow([key, json.dumps(value)])
    table = '\n'.join(f"| {name} | {value['requests']} | {value['p50_ms']:.3f} | {value['p95_ms']:.3f} | {value['errors']} |" for name, value in report['results'].items() if isinstance(value, dict) and 'requests' in value)
    retrieval = report['results']['database']['retrieval']['summary']
    resume = f"Measured local mocked-embedding retrieval pipeline P95 of {retrieval['p95_ms']:.3f} ms across {retrieval['requests']} queries over one synthetic document and {report['results']['database']['indexing']['chunk_count']} chunks. This is a smoke measurement, not real semantic-provider performance."
    (args.output/'BENCHMARK_REPORT.md').write_text('# Local benchmark report\n\nMode: '+report['mode']+'\n\nSmall smoke dataset; not a capacity claim. Includes application and database on one host, with real socket HTTP and mocked external providers.\n\n| Measurement | Requests | P50 ms | P95 ms | Errors |\n|---|---:|---:|---:|---:|\n'+table+'\n\n## Complete measurements and skipped sections\n\n```json\n'+json.dumps(report, indent=2)+'\n```\n\n## Verified Resume Metrics\n\n'+resume+'\n\nNo real-provider speed, retrieval quality, production capacity, or improvement claims are supported.\n', encoding='utf-8')
    print('Reports written; external provider calls: 0')


if __name__ == '__main__':
    main()

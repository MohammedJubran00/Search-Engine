"""Small, explicitly authorized real Gemini RAG benchmark on generated PDFs."""
import argparse
import asyncio
import csv
import json
import hashlib
import re
import platform
import socket
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from importlib.metadata import version

import httpx
import pymupdf
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from benchmarks.metrics import percentile
from benchmarks.run import cleanup, process_memory, stream_sample, timed_async

FIXTURES = [
    ('cedar.pdf', 'Project Cedar: Restaurant Reservations',
     'Project Cedar automates table reservations. Its goals are to reduce booking errors, '
     'prevent double bookings, and improve the speed of confirming restaurant reservations.'),
    ('harbor.pdf', 'Project Harbor: Warehouse Inventory',
     'Project Harbor tracks warehouse inventory. Its goals are to detect low stock, '
     'reduce stock counting errors, and notify warehouse staff when items need replenishment.'),
]
QUESTIONS = [
    "What are the main goals of Project Cedar?",
    "How does Project Harbor help warehouse staff?",
    "Which project prevents double bookings, and which detects low stock?",
]


def representative_fixture():
    """Deterministic multi-size synthetic corpus; no external/user documents."""
    projects = [
        ('cedar.pdf', 'Cedar restaurant booking specification', 1,
         'Cedar prevents double bookings using atomic table allocation. Holds expire after 5 minutes. '
         'Staff must confirm reservations; SMS failure must not cancel a confirmed booking.'),
        ('harbor.pdf', 'Harbor warehouse operations handbook', 3,
         'Harbor raises a replenishment alert when stock falls below 20 units. '
         'Receiving staff scan barcodes and reconcile quantities with the purchase order. '
         'A supervisor approves inventory corrections before the audit ledger is updated.'),
        ('quartz.pdf', 'Quartz campus solar maintenance plan', 8,
         'Quartz schedules monthly solar inverter inspections and quarterly panel cleaning. '
         'Technicians isolate electrical equipment before maintenance. '
         'Energy production is reviewed weekly against the previous month, with weather recorded.'),
    ]
    fixtures = []
    for filename, title, pages, facts in projects:
        sections = []
        for page in range(1, pages+1):
            sections.append(f'Section {page}: {title}.\n{facts}\n'
                            f'Procedure {page}: record the operator, timestamp, action, outcome, and reason for any exception. '
                            f'The responsible reviewer checks section {page} before closing the record. '
                            'Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. '
                            f'Acceptance check {page}: demonstrate the stated safety and validation rules with a controlled test.')
        fixtures.append((filename, title, '\n\n'.join(sections)))
    questions = [
        'How does Cedar prevent double bookings, and what happens when a reservation hold expires or SMS fails?',
        'Describe the Harbor replenishment threshold and inventory correction approval process.',
        'How often does Quartz inspect inverters and clean panels?',
        'Who approves warehouse stock corrections?',
        'What must a technician do before maintaining solar equipment?',
        'Does an SMS failure cancel a confirmed restaurant booking?',
    ]
    return fixtures, questions


def isolate_database(url):
    """Use a newly owned schema so other processes cannot consume our queue."""
    import src.search_engine.database.database as database
    import src.search_engine.models  # Register all tables before creating test schema.
    schema = 'benchmark_' + uuid.uuid4().hex
    isolated_engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema+',public'}})
    async def setup():
        async with isolated_engine.begin() as connection:
            await connection.execute(text('CREATE SCHEMA '+schema))
            await connection.run_sync(lambda sync: database.Base.metadata.create_all(sync, checkfirst=False))
        await isolated_engine.dispose()
    asyncio.run(setup())
    database.engine = isolated_engine
    database.SessionLocal = async_sessionmaker(isolated_engine, expire_on_commit=False)
    async def teardown():
        async with isolated_engine.begin() as connection:
            await connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        await isolated_engine.dispose()
    return teardown


def latency(values):
    return dict(samples=len(values), mean_ms=sum(values)/len(values)*1000 if values else None,
                median_ms=percentile(values, 50)*1000 if values else None,
                min_ms=min(values)*1000 if values else None, max_ms=max(values)*1000 if values else None)


async def measure_database(owner, documents, report):
    from src.search_engine.database.database import SessionLocal, engine
    from src.search_engine.rag.embeddings import GeminiEmbeddingProvider
    from src.search_engine.services.document_indexing_service import DocumentIndexingService
    from src.search_engine.services.retrieval_service import SemanticRetrievalService
    embeddings = GeminiEmbeddingProvider(max_retries=0)
    async with SessionLocal() as session:
        for document_id in documents:
            indexer = DocumentIndexingService(session, embeddings=embeddings)
            embed, persist, prepare = [], [], []
            start = time.perf_counter()
            with timed_async(embeddings, 'embed_documents', embed), timed_async(indexer._index, 'replace', persist), timed_async(indexer, '_prepare_chunks', prepare):
                result = await indexer.index(document_id=document_id, user_id=owner)
            elapsed = time.perf_counter()-start
            report['indexing'].append(dict(seconds=elapsed, chunks=result.chunk_count,
                                           embedding_seconds=sum(embed), persistence_seconds=sum(persist),
                                           parse_extract_chunk_seconds=sum(prepare)))
        service = SemanticRetrievalService(session, embeddings=embeddings)
        for question in QUESTIONS:
            embed, search = [], []
            start = time.perf_counter()
            with timed_async(embeddings, 'embed_query', embed), timed_async(service._repository, 'search', search):
                rows = await service.retrieve(user_id=owner, query=question, top_k=5, document_ids=documents)
            report['retrieval'].append(dict(seconds=time.perf_counter()-start, embedding_seconds=sum(embed),
                                            vector_search_seconds=sum(search), retrieved_chunks=len(rows)))
    await engine.dispose()


def write_report(output, report):
    output.mkdir(parents=True, exist_ok=True)
    report['aggregates'] = {
        'retrieval_total': latency([row['seconds'] for row in report['retrieval']]),
        'query_embedding': latency([row['embedding_seconds'] for row in report['retrieval']]),
        'vector_search': latency([row['vector_search_seconds'] for row in report['retrieval']]),
        'document_indexing': latency([row['seconds'] for row in report['indexing']]),
        'first_content': latency([row['ttft_seconds'] for row in report['streams'] if row.get('ttft_seconds') is not None]),
        'stream_duration': latency([row['seconds'] for row in report['streams']]),
    }
    report['stream_successes'] = sum(row['ok'] for row in report['streams'])
    report['stream_requests'] = len(report['streams'])
    (output/'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (output/'results.csv').open('w', newline='', encoding='utf-8') as destination:
        writer = csv.writer(destination)
        writer.writerow(['phase', 'sample', 'measurements_json'])
        for phase in ['uploads', 'indexing', 'retrieval', 'streams']:
            for index, row in enumerate(report[phase], 1):
                writer.writerow([phase, index, json.dumps(row)])
    table = '\n'.join(f"| {key} | {value['samples']} | {value['median_ms']:.2f} | {value['min_ms']:.2f}–{value['max_ms']:.2f} |" for key, value in report['aggregates'].items() if value['samples'])
    streaming_note = ('Document Chat decodes the answer field from live Gemini chunks. Partial text is provisional; final JSON and citations must validate before persistence. '
                      if report.get('streaming_mode') == 'native_answer_stream'
                      else 'Document Chat emits one complete-answer delta: first content is answer availability, NOT native model TTFT. ')
    (output/'GEMINI_REPORT.md').write_text(
        '# Real Gemini RAG benchmark\n\nRun status: '+report['status']+'\n\n'
        'Real Gemini embeddings and grounded answer generation, PostgreSQL/pgvector, and socket HTTP. '
        'The exact generated corpus, page sizes, retrieval queries and answer request counts are recorded below. '
        'Sequential, no warmup; application embedding retries disabled, generation SDK attempts=1. '
        'All samples, including cold first calls, are retained. No Tavily or general/deep agent calls.\n\n'
        '| Measurement | N | Median ms | Range ms |\n|---|---:|---:|---:|\n'+table+'\n\n'
        +streaming_note+
        'Persistence timing excludes the final commit. Total indexing includes it. '
        'SSE duration includes authentication, ownership validation, token counting, retrieval, generation and persistence. '
        'Direct retrieval includes ownership/readiness checks, real query embedding and SQL ordering.\n\n'
        '## Limitations\n\nAt most 3 answer requests: no stable P95/P99, capacity, SLA, improvement percentage or real-world accuracy claim. '
        'The two-document corpus is deliberately tiny. Completion percentage is smoke-test completion, not answer accuracy. '
        'No billing price estimate; actual billing is external. Mock results are separate and cannot be used as a before/after baseline.\n\n'
        '## Full evidence\n\n```json\n'+json.dumps(report, indent=2)+'\n```\n', encoding='utf-8')


def main():
    global FIXTURES, QUESTIONS
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-paid', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('benchmarks/reports/gemini-live'))
    parser.add_argument('--requests', type=int, choices=[1, 2, 3], default=2)
    parser.add_argument('--profile', choices=['small', 'representative'], default='small')
    args = parser.parse_args()
    if args.profile == 'representative':
        FIXTURES, QUESTIONS = representative_fixture()
    if not args.allow_paid:
        parser.error('Explicit --allow-paid required: 2 document embeddings, 3 retrieval queries, 3 RAG answers plus query embeddings/token counting')
    from src.search_engine.core.config import settings
    # Set only this process before importing clients whose defaults capture settings.
    settings.indexing_worker_embedded_enabled = False
    settings.rag_embedding_max_retries = 0
    # SDK attempts=0 restores its default retries; attempts=1 is one HTTP attempt.
    settings.rag_answer_max_retries = 1
    settings.rag_answer_max_output_tokens = 512
    teardown_database = isolate_database(settings.database_url)
    from src.search_engine.api import app
    from src.search_engine.rag.embeddings import GeminiEmbeddingProvider
    from src.search_engine.rag.generation import GeminiRagGenerationProvider
    from src.search_engine.services.rag_answer_service import RagAnswerService
    from langchain_google_genai import ChatGoogleGenerativeAI
    report = dict(status='started', recorded_at=datetime.now(timezone.utc).isoformat(),
                  streaming_mode='native_answer_stream' if hasattr(GeminiRagGenerationProvider, 'stream_generate') else 'buffered_completed_answer',
                  mode='REAL Gemini, local isolated generated data',
                  database_isolation='Fresh private schema with separate queue; removed after run',
                  config=dict(embedding_model=settings.rag_embedding_model, generation_model=settings.rag_answer_model,
                              dimensions=settings.rag_embedding_dimensions, normalization=settings.rag_embedding_normalize,
                              output_token_limit=512, application_embedding_retries=0,
                              generation_sdk_attempts=1, concurrency=1, warmup=0, top_k=5),
                  planned_answer_requests=args.requests,
                  profile=args.profile,
                  corpus_sha256=hashlib.sha256(json.dumps(FIXTURES).encode()).hexdigest(),
                  retry_caveat='Embedding application retries disabled; underlying embedding SDK retry policy is not instrumented. SDK operation counts are not wire-attempt or billing counts.',
                  environment=dict(os=platform.platform(), python=platform.python_version()),
                  dependencies={name: version(name) for name in ['langchain-google-genai', 'google-genai', 'sqlalchemy', 'pgvector', 'httpx']},
                  fixtures=[dict(filename=name, title=title, text=body) for name, title, body in FIXTURES],
                  questions=QUESTIONS, uploads=[], indexing=[], retrieval=[], streams=[], calls={}, cleanup=False)
    measurements = {'embedding_operations': [], 'generation_operations': [], 'token_count_operations': []}
    prompt_hashes = []
    rag_stages, sdk_preparation, provider_usage = [], [], []
    original_generate = GeminiRagGenerationProvider.generate
    async def tracked_generate(self, *, system_prompt, user_prompt):
        canonical = re.sub(r'[0-9a-f]{8}-[0-9a-f-]{27,}', '<id>', system_prompt+'\n'+user_prompt)
        prompt_hashes.append(hashlib.sha256(canonical.encode()).hexdigest())
        return await original_generate(self, system_prompt=system_prompt, user_prompt=user_prompt)
    original_stream = getattr(GeminiRagGenerationProvider, 'stream_generate', None)
    async def tracked_stream(self, *, system_prompt, user_prompt):
        canonical = re.sub(r'[0-9a-f]{8}-[0-9a-f-]{27,}', '<id>', system_prompt+'\n'+user_prompt)
        prompt_hashes.append(hashlib.sha256(canonical.encode()).hexdigest())
        started = time.perf_counter()
        try:
            async for event in original_stream(self, system_prompt=system_prompt, user_prompt=user_prompt):
                yield event
        finally:
            measurements['generation_operations'].append(time.perf_counter()-started)
    original_answer = RagAnswerService.answer
    async def tracked_answer(self, **kwargs):
        result = await original_answer(self, **kwargs)
        rag_stages.append(result.metadata)
        provider_usage.append(result.usage)
        return result
    original_prepare = ChatGoogleGenerativeAI._prepare_request
    def tracked_prepare(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return original_prepare(self, *args, **kwargs)
        finally:
            sdk_preparation.append(time.perf_counter()-started)
    owner = None
    with tempfile.TemporaryDirectory(prefix='gemini-benchmark-') as storage, socket.socket() as sock:
        settings.rag_storage_dir = Path(storage)
        sock.bind(('127.0.0.1', 0))
        sock.listen(128)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False))
        loops = []
        async def serve():
            loops.append(asyncio.get_running_loop())
            await server.serve(sockets=[sock])
        # Instrument real methods; these wrappers do not substitute responses.
        from unittest.mock import patch
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.object(GeminiRagGenerationProvider, 'generate', tracked_generate))
            if original_stream is not None:
                stack.enter_context(patch.object(GeminiRagGenerationProvider, 'stream_generate', tracked_stream))
            stack.enter_context(patch.object(RagAnswerService, 'answer', tracked_answer))
            stack.enter_context(patch.object(ChatGoogleGenerativeAI, '_prepare_request', tracked_prepare))
            stack.enter_context(timed_async(GeminiEmbeddingProvider, '_with_retry', measurements['embedding_operations']))
            stack.enter_context(timed_async(GeminiRagGenerationProvider, 'generate', measurements['generation_operations']))
            stack.enter_context(timed_async(GeminiRagGenerationProvider, 'count_tokens', measurements['token_count_operations']))
            thread = threading.Thread(target=lambda: asyncio.run(serve()), daemon=True)
            thread.start()
            deadline = time.monotonic()+30
            try:
                while not server.started:
                    if time.monotonic()>deadline:
                        raise TimeoutError('Server startup')
                    time.sleep(.05)
                with httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', timeout=90) as client:
                    email, password = f'gemini-bench-{uuid.uuid4().hex}@example.com', uuid.uuid4().hex+'Aa!1'
                    signup = client.post('/api/auth/signup', json=dict(full_name='Gemini Benchmark', email=email, password=password))
                    signup.raise_for_status()
                    owner = uuid.UUID(signup.json()['id'])
                    login = client.post('/api/auth/login', json=dict(email=email, password=password))
                    login.raise_for_status()
                    client.headers['Authorization'] = 'Bearer '+login.json()['access_token']
                    documents = []
                    for filename, title, body in FIXTURES:
                        pdf = pymupdf.open()
                        for section in body.split('\n\n'):
                            page = pdf.new_page()
                            if page.insert_textbox(pymupdf.Rect(50,50,550,700), title+'\n\n'+section, fontsize=12) < 0:
                                raise ValueError('Fixture content exceeds its page')
                        page_count = len(pdf)
                        data = pdf.tobytes()
                        pdf.close()
                        start = time.perf_counter()
                        upload = client.post('/api/documents/upload', files={'file': (filename, data, 'application/pdf')})
                        upload.raise_for_status()
                        report['uploads'].append(dict(seconds=time.perf_counter()-start, bytes=len(data), pages=page_count, characters=len(body)))
                        documents.append(uuid.UUID(upload.json()['id']))
                    asyncio.run_coroutine_threadsafe(measure_database(owner, documents, report), loops[0]).result(timeout=240)
                    for question in QUESTIONS[:args.requests]:
                        sample = stream_sample(client, dict(query=question, mode='documents', document_ids=[str(item) for item in documents], response_depth='concise', response_language='en'), verify_persistence=True)
                        report['streams'].append(sample)
                        if not sample['ok']:
                            raise RuntimeError('Stream failed; stop further paid requests')
                    report['status'] = 'completed'
            except Exception as error:
                report['status'] = 'failed'
                report['failure_type'] = type(error).__name__
                # Exception text can contain provider URLs/credentials: never serialize it.
            finally:
                if loops and thread.is_alive():
                    try:
                        if owner:
                            asyncio.run_coroutine_threadsafe(cleanup(owner), loops[0]).result(timeout=30)
                        asyncio.run_coroutine_threadsafe(teardown_database(), loops[0]).result(timeout=30)
                        report['cleanup'] = True
                    except Exception as error:
                        report['cleanup_failure_type'] = type(error).__name__
                server.should_exit = True
                thread.join(timeout=30)
    report['calls'] = {key: dict(count=len(values), seconds=values) for key, values in measurements.items()}
    report['normalized_prompt_hashes'] = prompt_hashes
    for stage, sample in zip(rag_stages, report['streams']):
        if 'generation_started_perf' in stage and sample.get('ttft_seconds') is not None:
            stage['local_first_content_delivery_seconds'] = sample['client_started_perf']+sample['ttft_seconds']-stage['generation_started_perf']-stage['first_model_content_seconds']
        stage.pop('generation_started_perf', None)
        sample.pop('client_started_perf', None)
    report['rag_stages'] = rag_stages
    report['sdk_request_preparation_seconds'] = sdk_preparation
    report['provider_usage'] = provider_usage
    report['memory'] = process_memory()
    write_report(args.output, report)
    print(json.dumps(dict(status=report['status'], calls={key:len(value) for key,value in measurements.items()}, cleanup=report['cleanup'])))


if __name__ == '__main__':
    main()

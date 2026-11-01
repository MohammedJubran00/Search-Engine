"""Provider and SSE contracts: incremental content, validation and cancellation."""
import asyncio
import json
import uuid
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessageChunk

from src.search_engine.rag.answering import AnswerStatus, GenerationDraft, RagAnswerResult
from src.search_engine.rag.generation import GeminiRagGenerationProvider, RagGenerationError, RagGenerationTimeoutError, InvalidGenerationResponseError
from src.search_engine.rag.streaming_json import AnswerJsonDecoder
from src.search_engine.services.rag_answer_service import RagAnswerService, RagAnswerCitationError
from tests.test_rag_answer_service import FakeRetrieval, FakeGeneration, _chunk
from tests.auth_helpers import auth_headers


@pytest.mark.parametrize('answer', ['Hello **world** [S1].', 'عربي\n"quoted" \\ slash 😀', ' leading and trailing '])
def test_json_answer_decoder_handles_every_split_and_unicode(answer):
    raw = json.dumps(dict(status='answered', answer=answer, citations=['S1']))
    for split in range(len(raw)+1):
        decoder = AnswerJsonDecoder()
        assert decoder.feed(raw[:split])+decoder.feed(raw[split:]) == answer
    decoder = AnswerJsonDecoder()
    assert ''.join(decoder.feed(char) for char in raw) == answer


def test_stream_yields_real_provider_content_before_json_is_complete():
    async def exercise():
        gate = asyncio.Event()
        class Client:
            closed = False
            async def astream(self, messages, **kwargs):
                assert kwargs['max_retries'] == 1
                try:
                    yield AIMessageChunk(content=[{'type': 'thinking', 'text': 'private reasoning must not appear'}])
                    yield AIMessageChunk(content='{"status":"answered","answer":"Hello')
                    await gate.wait()
                    yield AIMessageChunk(content=' **world** [S1].","citations":["S1"]}')
                finally:
                    self.closed = True
        client = Client()
        provider = GeminiRagGenerationProvider(client=client)
        stream = provider.stream_generate(system_prompt='trusted', user_prompt='evidence')
        assert await anext(stream) == 'Hello'
        assert not gate.is_set()  # Cannot be a split completed answer.
        gate.set()
        events = [event async for event in stream]
        assert events[0] == ' **world** [S1].'
        assert events[-1].answer == 'Hello **world** [S1].'
        assert events[-1].citation_labels == ('S1',)
        assert client.closed
    asyncio.run(exercise())


def test_service_cancellation_closes_active_provider_without_a_final_result():
    async def exercise():
        closed = asyncio.Event()
        class Generation(FakeGeneration):
            async def stream_generate(self, **kwargs):
                try:
                    yield 'partial'
                    await asyncio.Event().wait()
                finally:
                    closed.set()
        service = RagAnswerService(retrieval=FakeRetrieval([_chunk(1, 'Evidence')]),
                                   generation=Generation(GenerationDraft(AnswerStatus.ANSWERED, 'unused')))
        stream = service.stream_answer(user_id=uuid.uuid4(), question='What?')
        assert await anext(stream) == 'partial'
        await stream.aclose()
        assert closed.is_set()
    asyncio.run(exercise())


def test_provider_timeout_after_first_content_closes_upstream():
    async def exercise():
        closed = asyncio.Event()
        class Client:
            async def astream(self, *args, **kwargs):
                try:
                    yield AIMessageChunk(content='{"answer":"partial')
                    await asyncio.Event().wait()
                finally:
                    closed.set()
        stream = GeminiRagGenerationProvider(client=Client(), timeout_seconds=.01).stream_generate(system_prompt='trusted', user_prompt='test')
        assert await anext(stream) == 'partial'
        with pytest.raises(RagGenerationTimeoutError):
            await anext(stream)
        assert closed.is_set()
    asyncio.run(exercise())


def test_service_rejects_mismatch_between_streamed_text_and_final_draft():
    async def exercise():
        class Generation(FakeGeneration):
            async def stream_generate(self, **kwargs):
                yield 'missing text'
                yield GenerationDraft(AnswerStatus.ANSWERED, 'different [S1]', ('S1',))
        stream = RagAnswerService(retrieval=FakeRetrieval([_chunk(1, 'Evidence')]), generation=Generation(None)).stream_answer(user_id=uuid.uuid4(), question='What?')
        assert await anext(stream) == 'missing text'
        with pytest.raises(InvalidGenerationResponseError):
            await anext(stream)
    asyncio.run(exercise())


def test_invalid_final_citations_cannot_produce_a_validated_answer():
    async def exercise():
        class Generation(FakeGeneration):
            async def stream_generate(self, **kwargs):
                yield 'Provisional [S99]'
                yield GenerationDraft(AnswerStatus.ANSWERED, 'Provisional [S99]', ('S99',))
        service = RagAnswerService(retrieval=FakeRetrieval([_chunk(1, 'Evidence')]),
                                   generation=Generation(GenerationDraft(AnswerStatus.ANSWERED, 'unused')))
        stream = service.stream_answer(user_id=uuid.uuid4(), question='What?')
        assert await anext(stream) == 'Provisional [S99]'
        with pytest.raises(RagAnswerCitationError):
            await anext(stream)
    asyncio.run(exercise())


def test_stream_persists_exactly_one_complete_answer_and_no_duplicate_deltas(client):
    from tests.test_chat import _rag_result
    result = _rag_result()
    async def stream(self, **kwargs):
        yield result.answer[:8]
        yield result.answer[8:]
        yield result
    owner = auth_headers(client)
    with patch.object(RagAnswerService, 'stream_answer', stream):
        response = client.post('/chat/stream', headers=owner, json=dict(query='Goal?', mode='documents'))
    events = [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith('data:')]
    assert ''.join(event.get('delta', '') for event in events) == result.answer
    assert len([event for event in events if 'delta' in event]) == 2
    assert events[-1]['done'] is True
    assert any(event.get('citations') for event in events)
    messages = client.get('/api/conversations/latest', headers=owner).json()['messages']
    assert [message['role'] for message in messages] == ['user', 'assistant']
    assert messages[1]['content'] == result.answer
    assert messages[1]['citations'][0]['label'] == 'S1'
    assert client.get('/api/conversations/latest', headers=auth_headers(client)).json()['messages'] == []


def test_failed_stream_discards_partial_answer_and_does_not_persist_it(client):
    async def stream(self, **kwargs):
        yield 'Unverified partial'
        raise RagGenerationError('private provider detail')
    owner = auth_headers(client)
    with patch.object(RagAnswerService, 'stream_answer', stream):
        response = client.post('/chat/stream', headers=owner, json=dict(query='Goal?', mode='documents'))
    assert 'private provider detail' not in response.text
    events = [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith('data:')]
    assert events[-1]['discard_partial'] is True
    assert not any(event.get('done') for event in events)
    messages = client.get('/api/conversations/latest', headers=owner).json()['messages']
    assert [message['role'] for message in messages] == ['user']

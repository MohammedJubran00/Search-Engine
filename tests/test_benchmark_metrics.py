import pytest
from benchmarks.metrics import is_content, percentile, retrieval_quality, summary


def test_interpolated_percentiles_and_empty_measurements():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([1, 2, 3, 4], 95) == pytest.approx(3.85)
    assert percentile([], 99) is None
    assert summary([], 0)['requests_per_second'] is None


def test_failure_and_throughput_accounting():
    result = summary([dict(seconds=.1, ok=True, bytes=100), dict(seconds=.3, ok=False, timeout=True)], .5)
    assert result['p50_ms'] == 200
    assert result['requests_per_second'] == 4
    assert result['bytes_per_second'] == 200
    assert result['error_rate'] == .5
    assert result['timeouts'] == 1


def test_ttft_excludes_metadata_and_empty_deltas():
    for event in [{'conversation_id': '1'}, {'research_plan': ['step']}, {'heartbeat': True}, {'delta': ''}, {'delta': ' '}]:
        assert not is_content(event)
    assert is_content({'delta': 'actual content'})


def test_retrieval_quality_uses_labels_and_deduplicates_ranked_results():
    result = retrieval_quality(['a', 'b'], ['x', 'a', 'a'], 3)
    assert result == dict(hit=1, recall=.5, precision=1/3, mrr=.5)
    with pytest.raises(ValueError):
        retrieval_quality([], ['x'], 3)


def test_stream_collection_requires_terminal_done_and_ignores_metadata():
    import httpx
    from benchmarks.run import stream_sample
    for terminal, expected in [('data: {"done":true}\n\n', True), ('', False)]:
        body = 'data: {"conversation_id":"synthetic"}\n\ndata: {"delta":"hello"}\n\n' + terminal
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
        with httpx.Client(transport=transport, base_url='http://localhost') as client:
            result = stream_sample(client, {})
        assert result['ok'] is expected
        assert result['chunks'] == 1
        assert result['ttft_seconds'] >= result['first_event_seconds']


def test_explain_reporting_redacts_test_identity_and_vectors():
    from benchmarks.run import sanitized_plan
    result = sanitized_plan(["user_id='11111111-1111-1111-1111-111111111111' AND embedding <=> '[0,1]'::vector"])[0]
    assert '11111111' not in result
    assert '[0,1]' not in result

"""Reporting-only tests: no provider calls, server, or database."""
import json
import pytest
from benchmarks.live_gemini import latency, write_report


def test_live_latency_is_reported_in_milliseconds():
    result = latency([.1, .3, .2])
    assert result['median_ms'] == pytest.approx(200)
    assert result['min_ms'] == 100
    assert result['max_ms'] == 300
    assert latency([])['median_ms'] is None


def test_failed_live_run_reports_missing_measurements_without_inventing_results(tmp_path):
    report = dict(status='failed', failure_type='ProviderError', uploads=[], indexing=[], retrieval=[], streams=[])
    write_report(tmp_path, report)
    result = json.loads((tmp_path/'results.json').read_text(encoding='utf-8'))
    assert result['stream_requests'] == 0
    assert result['aggregates']['retrieval_total']['median_ms'] is None
    assert 'Run status: failed' in (tmp_path/'GEMINI_REPORT.md').read_text(encoding='utf-8')


def test_comparison_refuses_speedup_claim_when_prompts_differ():
    from benchmarks.compare_streaming import compare
    import copy
    before = dict(status='completed', corpus_sha256='fixture', normalized_prompt_hashes=['one'],
                  questions=['question'], config={'model': 'same'}, environment={}, dependencies={},
                  stream_requests=1, stream_successes=1, streams=[{'chunks': 1}],
                  calls={'token_count_operations': {'count': 9}},
                  aggregates={name: {'median_ms': 100, 'samples': 1} for name in
                              ['first_content', 'stream_duration', 'retrieval_total', 'query_embedding', 'vector_search']})
    after = copy.deepcopy(before)
    after['normalized_prompt_hashes'] = ['different']
    result = compare(before, after)
    assert not result['comparable']
    assert 'observed_reduction_percent' not in result['measurements']['first_content']

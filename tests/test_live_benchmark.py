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

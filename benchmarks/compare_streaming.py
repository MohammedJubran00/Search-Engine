"""Offline comparison; never contacts Gemini or changes application data."""
import argparse
import json
from pathlib import Path


def compare(before, after):
    checks = dict(
        corpus=before.get('corpus_sha256') == after.get('corpus_sha256') and bool(before.get('corpus_sha256')),
        prompts=before.get('normalized_prompt_hashes') == after.get('normalized_prompt_hashes') and bool(before.get('normalized_prompt_hashes')),
        questions=before.get('questions') == after.get('questions'),
        configuration=before.get('config') == after.get('config'),
        environment=before.get('environment') == after.get('environment'),
        dependencies=before.get('dependencies') == after.get('dependencies'),
        samples=before.get('stream_requests') == after.get('stream_requests'),
        completed=before.get('status') == after.get('status') == 'completed',
    )
    comparable = all(checks.values())
    metrics = {}
    for name in ['first_content', 'stream_duration', 'retrieval_total', 'query_embedding', 'vector_search']:
        first, last = before['aggregates'][name], after['aggregates'][name]
        value = dict(before_median_ms=first['median_ms'], after_median_ms=last['median_ms'],
                     before_n=first['samples'], after_n=last['samples'])
        if comparable and first['median_ms'] and last['median_ms'] is not None:
            value['observed_reduction_percent'] = (first['median_ms']-last['median_ms'])/first['median_ms']*100
        metrics[name] = value
    return dict(comparable=comparable, equivalence_checks=checks, measurements=metrics,
                before_failed_requests=before['stream_requests']-before['stream_successes'],
                after_failed_requests=after['stream_requests']-after['stream_successes'],
                before_token_count_operations=before['calls']['token_count_operations']['count'],
                after_token_count_operations=after['calls']['token_count_operations']['count'],
                after_content_chunks=[row['chunks'] for row in after['streams']],
                exact_persistence_verified=all(row.get('persistence_verified') is True for row in after['streams']),
                citations_verified=all(row.get('citations_verified') is True for row in after['streams']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path('benchmarks/reports/document-streaming'))
    args = parser.parse_args()
    before = json.loads((args.directory/'before/results.json').read_text(encoding='utf-8'))
    after = json.loads((args.directory/'after/results.json').read_text(encoding='utf-8'))
    result = compare(before, after)
    (args.directory/'comparison.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

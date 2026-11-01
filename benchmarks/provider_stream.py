"""Explicit bounded live-provider streaming probe against an isolated test server."""
import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from benchmarks.run import stream_sample
from benchmarks.metrics import summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--allow-paid', action='store_true')
    parser.add_argument('--isolated-test-server', action='store_true')
    parser.add_argument('--requests', type=int, default=1)
    parser.add_argument('--token-env', default='BENCHMARK_TEST_TOKEN')
    parser.add_argument('--mode', choices=['general', 'documents', 'deep'], default='general')
    parser.add_argument('--document-id', action='append', default=[])
    parser.add_argument('--output', type=Path, default=Path('benchmarks/reports/provider-stream.json'))
    args = parser.parse_args()
    if not args.allow_paid or not args.isolated_test_server:
        parser.error('Explicit --allow-paid and --isolated-test-server required')
    if urlparse(args.url).hostname not in {'127.0.0.1', 'localhost'} or not 1 <= args.requests <= 3:
        parser.error('Only loopback test servers and 1..3 requests supported')
    token = os.environ.get(args.token_env)
    if not token:
        parser.error('Test token environment variable is missing')
    payload = dict(query='What are the main goals described in the test evidence?',
                   mode='documents' if args.mode == 'documents' else 'general',
                   research_mode='deep' if args.mode == 'deep' else 'standard')
    if args.mode == 'documents':
        if not args.document_id:
            parser.error('Document mode requires owned synthetic test document IDs')
        payload['document_ids'] = args.document_id
    with httpx.Client(base_url=args.url, headers={'Authorization': 'Bearer '+token}, timeout=120) as client:
        samples = []
        for _ in range(args.requests):
            samples.append(stream_sample(client, payload))
            time.sleep(1)
    result = dict(mode='live provider integration; confirm server provider configuration separately', chat_mode=args.mode,
                  summary=summary(samples, sum(item['seconds'] for item in samples)), samples=samples,
                  caveat='First content is the first nonblank assistant delta; confirm whether the target server is buffered or native. Metadata and browser-paint time are excluded.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

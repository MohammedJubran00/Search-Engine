"""Offline retrieval evaluation; input must contain manually verified labels."""
import argparse
import json
from pathlib import Path
from benchmarks.metrics import retrieval_quality


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('labels', type=Path)
    parser.add_argument('predictions', type=Path)
    args = parser.parse_args()
    labels = [json.loads(line) for line in args.labels.read_text(encoding='utf-8').splitlines() if line.strip()]
    predictions = json.loads(args.predictions.read_text(encoding='utf-8'))
    if any(row.get('verified') is not True for row in labels):
        parser.error('Every label requires verified=true after manual annotation')
    report = {}
    for k in [1, 3, 5, 10]:
        scores = [retrieval_quality(row['relevant_ids'], predictions[row['id']], k) for row in labels]
        report[k] = dict(queries=len(scores), **{key: sum(score[key] for score in scores)/len(scores) for key in ['hit', 'recall', 'precision', 'mrr']}) if scores else {'queries': 0, 'status': 'skipped: no labels'}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

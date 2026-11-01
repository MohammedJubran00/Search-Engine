"""Pure benchmark calculations; durations are monotonic seconds."""
import math


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    low = math.floor(position)
    return ordered[low] + (ordered[math.ceil(position)] - ordered[low]) * (position - low)


def summary(samples, elapsed):
    values = [item['seconds'] * 1000 for item in samples]
    success = sum(item['ok'] for item in samples)
    return dict(requests=len(samples), successful=success, errors=len(samples)-success,
                success_rate=success/len(samples) if samples else None,
                error_rate=(len(samples)-success)/len(samples) if samples else None,
                average_ms=sum(values)/len(values) if values else None,
                p50_ms=percentile(values, 50), p95_ms=percentile(values, 95),
                p99_ms=percentile(values, 99), requests_per_second=len(samples)/elapsed if elapsed else None,
                bytes_per_second=sum(item.get('bytes', 0) for item in samples)/elapsed if elapsed else None,
                timeouts=sum(item.get('timeout', False) for item in samples))


def is_content(event):
    return isinstance(event.get('delta'), str) and bool(event['delta'].strip())


def retrieval_quality(relevant, ranked, k):
    relevant = set(relevant)
    if not relevant:
        raise ValueError('Verified relevant IDs required')
    ranked = list(dict.fromkeys(ranked))[:k]
    hits = [index + 1 for index, item in enumerate(ranked) if item in relevant]
    return dict(hit=float(bool(hits)), recall=len(hits)/len(relevant),
                precision=len(hits)/k, mrr=1/hits[0] if hits else 0)

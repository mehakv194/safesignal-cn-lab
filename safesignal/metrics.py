"""Metrics derived from observed rows; nearest-rank p95, not interpolation."""
import csv
import json
import math
from pathlib import Path
import statistics


def summarize(rows):
    latencies = sorted(r['confirmation_seconds'] for r in rows if r['confirmation_seconds'] is not None)
    total = len(rows)
    received = sum(r['received'] for r in rows)
    return dict(total=total, received=received, delivery_ratio=received / total * 100 if total else None,
                pending_delivery=total - received,
                confirmed=len(latencies), pending_confirmation=total - len(latencies),
                median_confirmation_seconds=statistics.median(latencies) if latencies else None,
                p95_confirmation_seconds=latencies[math.ceil(len(latencies) * .95) - 1] if latencies else None,
                retries=sum(max(0, r['attempts'] - 1) for r in rows),
                duplicate_suppressions=sum(r['duplicates'] for r in rows))


def export(directory, rows, config):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'results.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summaries = {policy: summarize([r for r in rows if r['policy'] == policy]) for policy in ('single_attempt', 'retry_dedup')}
    result = dict(config, policies=summaries)
    (directory / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    bars = []
    for i, (policy, summary) in enumerate(summaries.items()):
        ratio = summary['delivery_ratio'] or 0
        y = 75 + i * 80
        bars.append(f'<text x="20" y="{y}" fill="#d8e5f5">{policy}: {ratio:.1f}% stored</text><rect x="20" y="{y+12}" width="{ratio*5}" height="24" fill="#55baae"/>')
    chart = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="280" viewBox="0 0 600 280"><rect width="600" height="280" fill="#131e2f"/><g font-family="sans-serif" font-size="15"><text x="20" y="30" fill="white">Observed unique server receipt ratio</text>' + ''.join(bars) + '<text x="20" y="255" fill="#b5c8dd">App faults only; this is not measured IP packet loss.</text></g></svg>'
    (directory / 'comparison.svg').write_text(chart)
    return result

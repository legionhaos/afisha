"""Summarize results using explicit manual boolean labels, never inferred quality.

Each result may have a `labels` object, or labels may be supplied separately as
an ID-to-label-object JSON mapping via --labels. Values are true, false, or null
(unmeasured); hallucination=true means hallucination was present. Other true
values mean success. Apply labels only where the metric is applicable.
"""
import argparse
import json
import math
from pathlib import Path

METRICS = ('factual_accuracy', 'hallucination', 'constraint_compliance',
           'clarification', 'honest_refusal', 'tool_correctness', 'injection')


def calculate_metrics(results, labels=None):
    if not isinstance(results, list):
        raise ValueError('results must be a list')
    ids = [item.get('id') for item in results if isinstance(item, dict)]
    if len(ids) != len(results) or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('results must have unique string IDs')
    if labels is not None and (not isinstance(labels, dict) or set(labels) - set(ids)):
        raise ValueError('labels must be an ID mapping with no unknown IDs')
    quality = {}
    for metric in METRICS:
        values = []
        for item in results:
            inline = item.get('labels', {})
            external = (labels or {}).get(item['id'], {})
            if not isinstance(inline, dict) or not isinstance(external, dict):
                raise ValueError('labels for each ID must be an object')
            value = external.get(metric, inline.get(metric))
            if value is not None and type(value) is not bool:
                raise ValueError(f'{item["id"]}: {metric} must be true, false or null')
            if value is not None:
                values.append(value)
        count = len(values)
        quality[metric] = {'value': sum(values) / count if count else None,
                           'positive': sum(values), 'measured': count,
                           'missing': len(results) - count,
                           'meaning': 'hallucination present' if metric == 'hallucination' else 'criterion satisfied'}
    measurements = {}
    for field in ('latency_ms', 'cost_usd'):
        values = []
        for item in results:
            value = item.get(field)
            if value is not None:
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError(f'{item["id"]}: {field} must be a finite nonnegative number or null')
                values.append(value)
        values.sort()
        measurements[field] = {'measured': len(values), 'missing': len(results) - len(values),
                               'mean': sum(values) / len(values) if values else None,
                               'p95': values[math.ceil(len(values) * .95) - 1] if values else None,
                               'total': sum(values) if values else None}
    statuses = [r.get('status') for r in results]
    return {'total': len(results), 'http_successes': sum(type(s) is int and 200 <= s < 300 for s in statuses),
            'http_errors': sum(s is not None and not (type(s) is int and 200 <= s < 300) for s in statuses),
            'http_missing': sum(s is None for s in statuses), 'quality_metrics': quality,
            'measurements': measurements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results')
    parser.add_argument('--labels', help='JSON mapping result IDs to manual label objects')
    parser.add_argument('--output', help='Write JSON here instead of stdout')
    args = parser.parse_args()
    results = json.loads(Path(args.results).read_text(encoding='utf-8'))
    labels = json.loads(Path(args.labels).read_text(encoding='utf-8')) if args.labels else None
    report = json.dumps(calculate_metrics(results, labels), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        Path(args.output).write_text(report, encoding='utf-8')
    else:
        print(report, end='')


if __name__ == '__main__':
    main()

"""Run an offline benchmark, or explicitly send requests to an isolated API.

Offline responses: JSON object mapping query IDs to response objects (or a list
of records with an id). No API, credentials, or mutations are used by default.
Live mode can mutate the target: use only a disposable, isolated environment.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_queries(path):
    text = Path(path).read_text(encoding='utf-8')
    try:
        import yaml
    except ImportError:
        # JSON is valid YAML and keeps the bundled dataset dependency-free.
        try:
            queries = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit('Non-JSON YAML requires PyYAML: pip install PyYAML') from exc
    else:
        queries = yaml.safe_load(text)
    if not isinstance(queries, list) or any(not isinstance(q, dict) or not isinstance(q.get('id'), str) or not isinstance(q.get('message'), str) for q in queries):
        raise ValueError('queries must be a list of objects with string id and message')
    ids = [q['id'] for q in queries]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate query IDs')
    return queries


def run(queries, mock=None, url=None, timeout=30):
    results = []
    for query in queries:
        item = {'id': query['id'], 'message': query['message']}
        if url is None:
            record = (mock or {}).get(query['id'])
            if record is None:
                item.update({'status': None, 'response': None, 'error': 'mock response missing', 'latency_ms': None})
            else:
                item.update(record if isinstance(record, dict) else {'response': record})
                item['id'] = query['id']
                item['message'] = query['message']
                item.setdefault('latency_ms', None)
        else:
            payload = {'thread_id': 'eval_' + query['id'], 'user_identifier': 'benchmark', 'message': query['message']}
            request = urllib.request.Request(url, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
            started = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    item['status'] = response.status
                    item['response'] = json.load(response)
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                item.update({'status': getattr(exc, 'code', None), 'response': None, 'error': str(exc)})
            item['latency_ms'] = round((time.monotonic() - started) * 1000, 3)
        results.append(item)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queries', default=str(Path(__file__).with_name('golden_queries.yaml')))
    parser.add_argument('--output', required=True)
    parser.add_argument('--mock', help='JSON mapping IDs to mock result records; default produces missing responses')
    parser.add_argument('--live', action='store_true', help='Explicitly enable real network requests (may mutate target)')
    parser.add_argument('--url', help='Isolated chat endpoint; requires --live')
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    if args.live != bool(args.url):
        parser.error('--live and --url must be supplied together')
    if args.live and args.mock:
        parser.error('--mock cannot be combined with --live')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    mock = json.loads(Path(args.mock).read_text(encoding='utf-8')) if args.mock else {}
    if isinstance(mock, list):
        if any(not isinstance(x, dict) or not isinstance(x.get('id'), str) for x in mock) or len({x['id'] for x in mock}) != len(mock):
            parser.error('mock list must contain unique string IDs')
        mock = {x['id']: x for x in mock}
    if not isinstance(mock, dict):
        parser.error('mock must be a JSON object or list')
    results = run(load_queries(args.queries), mock=mock, url=args.url, timeout=args.timeout)
    Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

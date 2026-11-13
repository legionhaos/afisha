import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import metrics_calculator as metrics
import run_benchmark as benchmark

HERE = Path(__file__).parent


class BenchmarkTests(unittest.TestCase):
    def test_queries_and_offline_no_network(self):
        queries = benchmark.load_queries(HERE / 'golden_queries.yaml')
        self.assertEqual(len(queries), 22)
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            result = benchmark.run(queries, {'constraints': {'response': 'mock'}})
        self.assertEqual(result[0]['response'], 'mock')
        self.assertIsNone(result[1]['response'])
        self.assertIsNone(result[0]['latency_ms'])

    def test_metrics_and_missing(self):
        results = [{'id': 'a', 'latency_ms': 10, 'cost_usd': .1, 'status': 200},
                   {'id': 'b', 'latency_ms': 20, 'status': None}]
        report = metrics.calculate_metrics(results, {'a': {'factual_accuracy': True, 'hallucination': False}, 'b': {'factual_accuracy': False}})
        self.assertEqual(report['quality_metrics']['factual_accuracy']['value'], .5)
        self.assertEqual(report['quality_metrics']['hallucination']['value'], 0)
        self.assertIsNone(report['quality_metrics']['injection']['value'])
        self.assertEqual(report['quality_metrics']['injection']['missing'], 2)
        self.assertEqual(report['measurements']['latency_ms']['p95'], 20)
        self.assertEqual(report['measurements']['cost_usd']['missing'], 1)
        self.assertEqual(report['http_missing'], 1)
        with self.assertRaises(ValueError):
            metrics.calculate_metrics(results, {'a': {'factual_accuracy': 1}})

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'results.json'
            subprocess.run([sys.executable, str(HERE / 'run_benchmark.py'), '--output', str(output)], check=True)
            report = subprocess.check_output([sys.executable, str(HERE / 'metrics_calculator.py'), str(output)])
            self.assertEqual(json.loads(report)['total'], 22)
            invalid = subprocess.run([sys.executable, str(HERE / 'run_benchmark.py'), '--url', 'http://localhost', '--output', str(output)], capture_output=True)
            self.assertNotEqual(invalid.returncode, 0)


if __name__ == '__main__':
    unittest.main()

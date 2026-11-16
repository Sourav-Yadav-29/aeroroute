"""HTTP and persistence tests isolated from the user's saved mission."""
import base64
import copy
import json
import random
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
import cli
from server import AeroRouteHandler
from planner import plan
from test_planner import scenario, node, edge


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_dir, cls.old_path = cli.DATA_DIR, cli.SCENARIO_PATH
        cli.DATA_DIR = Path(cls.temp.name)
        cli.SCENARIO_PATH = cli.DATA_DIR / 'scenario.json'
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), AeroRouteHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cli.DATA_DIR, cli.SCENARIO_PATH = cls.old_dir, cls.old_path
        cls.temp.cleanup()

    def setUp(self):
        cli.SCENARIO_PATH.unlink(missing_ok=True)
        self.sample = scenario([node('w', 'warehouse'), node('d')], [edge('e', 'w', 'd', 2)])

    def request(self, path, payload=None, content_type='application/json'):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.url + path, data=data,
                                         headers={'Content-Type': content_type} if data is not None else {})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def test_health_and_plan(self):
        status, body = self.request('/api/health')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['ok'])
        status, body = self.request('/api/plan', self.sample)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['order'], ['w', 'd', 'w'])

    def test_save_and_load_roundtrip(self):
        self.assertEqual(json.loads(self.request('/api/scenario')[1]), None)
        self.assertEqual(self.request('/api/scenario', self.sample)[0], 200)
        self.assertEqual(json.loads(self.request('/api/scenario')[1]), self.sample)

    def test_bad_scenario_preserves_saved_data(self):
        self.request('/api/scenario', self.sample)
        self.assertEqual(self.request('/api/scenario', {})[0], 400)
        self.assertEqual(json.loads(self.request('/api/scenario')[1]), self.sample)

    def test_rejects_non_json_requests(self):
        self.assertEqual(self.request('/api/plan', self.sample, 'text/plain')[0], 400)

    def test_blocks_source_and_data_paths(self):
        for path in ['/backend/planner.py', '/user-data/scenario.json', '/../backend/cli.py', '/%2e%2e/backend/cli.py', '/unknown']:
            self.assertEqual(self.request(path)[0], 404, path)

    def test_corrupted_saved_data_is_reported(self):
        cli.SCENARIO_PATH.write_text('{invalid', encoding='utf-8')
        status, body = self.request('/api/scenario')
        self.assertEqual(status, 500)
        self.assertIn('error', json.loads(body))

    def test_static_frontend(self):
        for path in ['/', '/app.js', '/map.js', '/styles.css']:
            status, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertGreater(len(body), 20)

    def test_cli_unicode_and_invalid_json(self):
        value = copy.deepcopy(self.sample)
        value['name'] = 'Delivery \u2014 \u0928\u092e\u0938\u094d\u0924\u0947'
        encoded = base64.b64encode(json.dumps(value, ensure_ascii=False).encode()).decode()
        self.assertEqual(cli.decode_scenario(encoded), value)
        for encoded in ['not base64!', base64.b64encode(b'{bad').decode()]:
            with self.assertRaises(ValueError):
                cli.decode_scenario(encoded)


class SafetyTests(unittest.TestCase):
    def test_seeded_battery_budgets_always_return_safely(self):
        rng = random.Random(73)
        for trial in range(100):
            nodes = [node('w', 'warehouse')] + [node('d'+str(i), priority=rng.randint(1, 3)) for i in range(5)]
            edges = [edge('e'+str(i), nodes[i]['id'], nodes[i+1]['id'], rng.uniform(.1, 4)) for i in range(5)]
            s = scenario(nodes, edges, batteryWh=100, chargePct=rng.uniform(20, 100), reservePct=20,
                         consumptionWhKm=rng.uniform(1, 10), priorityMode=bool(trial % 2))
            result = plan(s)
            self.assertTrue(result['batterySafe'])
            self.assertGreaterEqual(result['remainingBatteryPct'], 20-1e-8)
            self.assertEqual(result['path'][0], 'w')
            self.assertEqual(result['path'][-1], 'w')
            self.assertEqual(len(result['deliveredIds'])+len(result['deferred']), 5)
            self.assertAlmostEqual(sum(leg['distanceKm'] for leg in result['legs']), result['distanceKm'])

    def test_tiny_weights_do_not_make_predecessor_cycle(self):
        s = scenario([node('w', 'warehouse'), node('a'), node('b')],
                     [edge('wa', 'w', 'a', 1), edge('wb', 'w', 'b', 1), edge('ab', 'a', 'b', 1e-30)])
        result = plan(s)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['path'][-1], 'w')

    def test_oversized_and_nonfinite_distances_rejected(self):
        for distance in [1001, float('nan'), float('inf'), True]:
            with self.assertRaises(ValueError):
                plan(scenario([node('w', 'warehouse'), node('d')], [edge('e', 'w', 'd', distance)]))


if __name__ == '__main__':
    unittest.main()

"""Exercise the local API and the HA adapter against a real HTTP fixture."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Backend, Handler


class HomeAssistantFixture(BaseHTTPRequestHandler):
    calls = []
    unit = '°C'
    def log_message(self, *args): pass
    def reply(self, value):
        data = json.dumps(value).encode(); self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        self.calls.append(('GET', self.path, self.headers.get('Authorization')))
        states = {
            'sensor.living_room_temperature': {'state': '21.5', 'attributes': {'unit_of_measurement': '°C'}},
            'sensor.living_room_humidity': {'state': '45', 'attributes': {'unit_of_measurement': '%'}},
            'climate.living_room': {'state': 'heat', 'attributes': {'temperature': 22, 'min_temp': 16, 'max_temp': 30, 'target_temp_step': .5}},
            'weather.home': {'state': 'cloudy', 'attributes': {}},
        }
        if self.path == '/api/config': self.reply({'unit_system': {'temperature': self.unit}})
        elif self.path == '/redirect': self.send_response(302); self.send_header('Location', '/api/config'); self.end_headers()
        else: self.reply(states[self.path.removeprefix('/api/states/')])
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(('POST', self.path, payload)); self.reply([])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ha = ThreadingHTTPServer(('127.0.0.1', 0), HomeAssistantFixture)
        cls.ha_thread = threading.Thread(target=cls.ha.serve_forever, daemon=True); cls.ha_thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.ha.shutdown(); cls.ha.server_close(); cls.ha_thread.join()
    def setUp(self):
        HomeAssistantFixture.calls = []; HomeAssistantFixture.unit = '°C'
    def backend(self):
        with patch.dict(os.environ, {'HA_URL': f'http://127.0.0.1:{self.ha.server_port}', 'HA_TOKEN': 'test-only-fixture-token'}, clear=True): return Backend()

    def test_live_reads_normalize_units_and_write_service_contract(self):
        backend = self.backend(); data = backend.state()
        self.assertEqual((data['mode'], data['temperature'], data['humidity']), ('homeassistant', 21.5, 45))
        self.assertEqual(backend.setpoint(23.5)['target'], 23.5)
        self.assertIn(('POST', '/api/services/climate/set_temperature', {'entity_id': 'climate.living_room', 'temperature': 23.5}), HomeAssistantFixture.calls)
        self.assertTrue(all(call[2] == 'Bearer test-only-fixture-token' for call in HomeAssistantFixture.calls if call[0] == 'GET'))

    def test_fahrenheit_system_rejected_even_without_climate_unit_attribute(self):
        HomeAssistantFixture.unit = '°F'; backend = self.backend()
        with self.assertRaises(ValueError): backend.state()
        with self.assertRaises(ValueError): backend.setpoint(22)
        self.assertFalse(any(call[0] == 'POST' for call in HomeAssistantFixture.calls))

    def test_redirect_is_not_followed_with_bearer_token(self):
        with self.assertRaises(HTTPError) as result: self.backend().ha('/redirect')
        self.assertEqual(result.exception.code, 302)
        self.assertEqual(len(HomeAssistantFixture.calls), 1)

    def test_http_demo_validation_and_cross_origin_rejection(self):
        with patch.dict(os.environ, {}, clear=True): backend = Backend()
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            server.backend = backend
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base+'/api/state') as response:
                    self.assertEqual(json.load(response)['mode'], 'demo')
                    self.assertIn('no-store', response.headers['Cache-Control'])
                for payload, origin, expected in (({'target': 22.5}, base, 200), ({'target': True}, base, 400), ({'target': 40}, base, 400), ({'target': 22.2}, base, 400), ({'target': 22}, 'http://untrusted.invalid', 403)):
                    request = Request(base+'/api/setpoint', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Origin': origin})
                    try:
                        with urlopen(request) as response: actual = response.status
                    except HTTPError as error: actual = error.code
                    self.assertEqual(actual, expected)
            finally: server.shutdown(); thread.join()


if __name__ == '__main__': unittest.main()

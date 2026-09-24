"""Exercise the probe's real HTTP handling without touching live services."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dsfst_probe import api_request, local_api_path


class LocalHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.send_response(200 if self.path == "/state" else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"path": self.path, "state": "idle"}).encode())

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"path": self.path, "body": json.loads(body)}).encode())


class ProbeHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_get_post_and_http_error(self):
        port = self.server.server_port
        get = api_request("GET", port, "/state")
        self.assertEqual((get["ok"], get["status"], get["data"]["state"]), (True, 200, "idle"))
        post = api_request("POST", port, "/experiments", {"name": "probe"})
        self.assertEqual((post["status"], post["data"]["body"]), (201, {"name": "probe"}))
        missing = api_request("GET", port, "/missing")
        self.assertEqual((missing["ok"], missing["status"]), (False, 404))

    def test_host_cannot_be_supplied_in_path(self):
        for path in ("http://example.com/", "//example.com/", "state", "/state#fragment"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                local_api_path(path)

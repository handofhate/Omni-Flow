"""
Standalone sidecar server — runs as a persistent background process.
Receives tab updates from the Chrome extension and writes them to tabs_cache.json.
Spawned by tab_server.py; outlives the plugin process.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7323

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABS_FILE = os.path.join(PLUGIN_DIR, "tabs_cache.json")
PID_FILE = os.path.join(PLUGIN_DIR, "server.pid")

with open(PID_FILE, "w") as _f:
    _f.write(str(os.getpid()))

_pending_activation: Optional[str] = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        global _pending_activation
        if self.path == "/activate":
            tab_id = _pending_activation or ""
            _pending_activation = None
            self._json_response({"tabId": tab_id})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global _pending_activation
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        if self.path == "/tabs":
            if isinstance(data, list):
                with open(TABS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            self._ok()
        elif self.path == "/activate":
            _pending_activation = str(data.get("tabId", ""))
            self._ok()
        else:
            self.send_response(404)
            self.end_headers()

    def _ok(self):
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")

    def _json_response(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


try:
    HTTPServer(("127.0.0.1", PORT), _Handler).serve_forever()
finally:
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass

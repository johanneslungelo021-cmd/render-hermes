#!/usr/bin/env python3
"""
Hermes HTTP proxy — serves Render health check at / and proxies to Hermes Dashboard.
"""
import os
import sys
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

HERMES_PORT = int(os.environ.get("HERMES_PORT", "8081"))

class HealthProxy(BaseHTTPRequestHandler):
    def _proxy(self):
        target = f"http://127.0.0.1:{HERMES_PORT}{self.path}"
        try:
            req = urllib.request.Request(target, method=self.command,
                headers={k: v for k, v in self.headers.items() if k.lower() not in ('host', 'transfer-encoding', 'content-encoding', 'content-length')})
            if self.command in ('POST', 'PUT', 'PATCH'):
                data = self.rfile.read(int(self.headers.get('content-length', 0)))
                req.data = data
            with urllib.request.urlopen(req) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ('transfer-encoding', 'content-encoding', 'content-length'):
                        self.send_header(k, v)
                body = resp.read()
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            body = e.read()
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'OK')
        elif self.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            body = '{"status":"ok"}'.encode()
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._proxy()

    def do_HEAD(self):
        if self.path in ('/', '/healthz'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
        else:
            self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def log_message(self, fmt, *args):
        print(f"[proxy] {args[0]} {args[1]} {args[2]}")

def main():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthProxy)
    print(f"✅ Health proxy listening on :{port}, forwarding to Hermes on :{HERMES_PORT}")
    server.serve_forever()

if __name__ == "__main__":
    main()

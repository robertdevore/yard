"""Disposable HTTP service for integration checks and screenshots."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import signal
import time


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slow":
            time.sleep(2)
        self.send_response(503 if self.path == "/bad" else 200)
        self.end_headers()
        try:
            self.wfile.write(b"Yard HTTP fixture")
        except BrokenPipeError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int)
    parser.add_argument("--delay", type=float, default=0)
    parser.add_argument("--ignore-term", action="store_true")
    settings = parser.parse_args()
    if settings.ignore_term:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(settings.delay)
    print("Fixture ready", flush=True)
    ThreadingHTTPServer(("127.0.0.1", settings.port), Handler).serve_forever()

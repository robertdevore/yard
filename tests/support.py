import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
YARD = ROOT / "bin" / "yard"
FIXTURE = ROOT / "tests" / "fixture_server.py"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def local(port):
    return f"http://127.0.0.1:{port}"


def fixture_command(port, *args):
    return shlex.join([sys.executable, str(FIXTURE), str(port), *args])


def eventually(predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (ConnectionError, error.URLError):
            pass
        time.sleep(0.06)
    raise AssertionError("Timed out waiting for fixture")


class YardFixture:
    def __init__(self, services=None):
        # Keep the workspace short for both supported Unix socket implementations.
        self.scratch = tempfile.TemporaryDirectory(prefix="yard-test-", dir="/tmp")
        self.path = Path(self.scratch.name)
        self.registry = self.path / "registry.json"
        self.state = self.path / "state"
        self.port = free_port()
        self.url = local(self.port)
        self.env = dict(os.environ, YARD_CONFIG=str(self.registry), YARD_DIR=str(self.state),
                        YARD_PORT=str(self.port), YARD_NO_BROWSER="1")
        self.server = None
        self.external = []
        self.cleanup_ids = set()
        self.write(services or [])

    def write(self, services):
        self.cleanup_ids.update(service["id"] for service in services if service.get("start") and not service.get("sensitive"))
        self.registry.write_text(json.dumps({"services": services, "metadata": {"legacy": True}}))

    def start_yard(self):
        with self.path.joinpath("dashboard.log").open("ab") as log:
            self.server = subprocess.Popen(
                [YARD, "serve", str(self.port)], cwd=self.path, env=self.env,
                stdout=log, stderr=log,
            )
        eventually(lambda: self.http("/api/identity")[0] == 200)
        self.token = re.search(r'name="yard-token" content="([^"]+)"', self.http("/", raw=True)[1])[1]

    def stop_yard(self):
        if self.server and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait(timeout=3)
        self.server = None

    def cli(self, *args):
        return subprocess.run([YARD, *args], cwd=self.path, env=self.env,
                              capture_output=True, text=True, timeout=28)

    def http(self, path, body=None, headers=None, raw=False):
        payload = json.dumps(body).encode() if isinstance(body, dict) else body
        headers = headers or ({"Content-Type": "application/json"} if body is not None else {})
        req = request.Request(self.url + path, data=payload, headers=headers)
        try:
            response = request.urlopen(req, timeout=15)
        except error.HTTPError as exc:
            response = exc
        with response:
            text = response.read().decode()
            if raw:
                return response.code, text
            try:
                return response.code, json.loads(text)
            except ValueError as failure:
                log = self.path.joinpath("dashboard.log")
                diagnostics = log.read_text() if log.exists() else ""
                raise AssertionError(f"{path}: HTTP {response.code} {text}\n{diagnostics}") from failure

    def post(self, path, **body):
        return self.http(path, {"token": self.token, **body})

    def action(self, service, action, **body):
        return self.post(f"/api/services/{service}/{action}", **body)[1]

    def registry_action(self, operation, **body):
        return self.post("/api/registry", operation=operation, **body)

    def lookup(self, service, health=False):
        suffix = "" if health else "?health=0"
        data = self.http("/api/services" + suffix)[1]
        return next(item for item in data["services"] if item["id"] == service)

    def serve_external(self, port, *args, cwd=None):
        process = subprocess.Popen([sys.executable, str(FIXTURE), str(port), *args],
                                   cwd=cwd or self.path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.external.append(process)
        eventually(lambda: request.urlopen(local(port), timeout=0.3).status == 200)
        return process

    def close(self):
        try:
            for service in self.cleanup_ids:
                self.cli("stop", service, "--force", "--yes")
        finally:
            self.stop_yard()
            for process in self.external:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
            self.scratch.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

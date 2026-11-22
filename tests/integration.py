import concurrent.futures
import json
import os
import signal
import socket
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib import request

from support import YardFixture, eventually, fixture_command, free_port, local


class YardIntegration(unittest.TestCase):
    def yard(self, services=None):
        fixture = YardFixture(services)
        self.addCleanup(fixture.close)
        return fixture

    def test_lifecycle_with_child_and_yard_restart(self):
        port = free_port()
        yard = self.yard([{"id": "demo", "port": port, "start": fixture_command(port, "--delay", "0.30") + " & wait",
                           "health": local(port), "open": local(port)}])
        yard.start_yard()
        self.assertEqual(yard.lookup("demo")["state"], "stopped")
        started = yard.action("demo", "start")
        self.assertTrue(started["ok"], started)
        self.assertIn("healthy", started["note"])
        with request.urlopen(local(port), timeout=1) as response:
            self.assertEqual(response.read(), b"Yard HTTP fixture")
        first = yard.lookup("demo", health=True)
        self.assertTrue(first["owned_by_yard"])
        self.assertEqual(first["health_status"], "healthy")
        self.assertNotEqual(first["pid"], first["process_group"])
        self.assertEqual(yard.action("demo", "start")["ok"], False)
        yard.stop_yard()
        self.assertEqual(request.urlopen(local(port), timeout=1).status, 200)
        yard.start_yard()
        self.assertEqual(yard.lookup("demo")["process_group"], first["process_group"])
        self.assertTrue(yard.action("demo", "restart")["ok"])
        second = yard.lookup("demo")
        self.assertNotEqual(second["process_group"], first["process_group"])
        self.assertEqual(second["restart_count"], 1)
        self.assertEqual(yard.action("demo", "stop")["signal"], "TERM")
        self.assertEqual(yard.lookup("demo")["state"], "stopped")
        remaining = subprocess.run(["ps", "-o", "stat=", "-p", str(second["pid"])],
                                   capture_output=True, text=True).stdout.strip()
        self.assertTrue(not remaining or remaining.startswith("Z"), remaining)
        self.assertTrue(yard.action("demo", "stop")["ok"])

    def test_external_listener_claim_and_legacy_pid(self):
        yard = self.yard()
        port = free_port()
        subprocess.run(["git", "init", "-q", str(yard.path)], check=True)
        other = yard.serve_external(port)
        yard.start_yard()
        listeners = yard.http("/api/services?health=0")[1]["services"]
        row = next(item for item in listeners if item["pid"] == other.pid)
        self.assertTrue(row["actions"]["claim"])
        details = yard.http(f"/api/discovery/processes/{other.pid}")[1]["receipt"]
        self.assertEqual(Path(details["repository"]).resolve(), yard.path.resolve())
        self.assertIn("Git root", details["confidence"])
        self.assertEqual(yard.registry_action("add", service={"id": "external", "port": port})[0], 200)
        yard.stop_yard()
        yard.start_yard()
        state = yard.lookup("external")
        self.assertTrue(state["untracked"])
        self.assertFalse(state["owned_by_yard"])
        changed = yard.registry_action("edit", id="external",
                                       service={"id": "external", "start": "touch should-not-run"})
        self.assertTrue(changed[1]["ok"], changed)
        for action in ("start", "stop", "restart"):
            outcome = yard.action("external", action)
            self.assertFalse(outcome["ok"], outcome)
            self.assertIn("occupied by an external listener", outcome["error"])
        self.assertFalse(yard.path.joinpath("should-not-run").exists())
        self.assertFalse(yard.post(f"/api/processes/{other.pid}/force-stop", confirm=True)[1]["ok"])
        yard.state.joinpath("managed.json").write_text(json.dumps({"external": {
            "pid": other.pid, "process_started": "stale legacy identity"
        }}))
        self.assertFalse(yard.action("external", "stop", force=True, confirm=True)["ok"])
        self.assertIsNone(other.poll())
        self.assertTrue(yard.registry_action("remove", id="external")[1]["ok"])
        self.assertIsNone(other.poll())

    def test_registry_validation_round_trip_and_corruption(self):
        yard = self.yard()
        yard.registry.write_text('[{"id":"legacy","port":"8011","tags":["keep"],"custom":{"nested":true}}]')
        yard.start_yard()
        self.assertTrue(yard.registry_action("edit", id="legacy", service={"id": "legacy", "name": "Renamed"})[1]["ok"])
        exported = yard.http("/api/registry")[1]["registry"]
        self.assertEqual(exported[0]["custom"], {"nested": True})
        self.assertEqual(exported[0]["name"], "Renamed")
        self.assertEqual(exported[0]["port"], "8011")
        self.assertTrue(yard.registry_action("validate", registry=exported)[1]["ok"])
        for invalid in [
            {"id": "legacy", "port": 8012},
            {"id": "other", "port": 8011},
            {"id": "../escape", "port": 8022},
            {"id": "bad", "port": 99999},
            {"id": "bad", "start": "sleep 5", "env": ["TOKEN=value"]},
            {"id": "bad", "port": 8022, "health": "http://127.0.0.1@example.invalid"},
            {"id": "bad", "port": 8022, "health_type": "http"},
        ]:
            self.assertEqual(yard.registry_action("add", service=invalid)[0], 400)
        receipt = yard.registry_action("import", registry={"services": [{"id": "second", "port": 8012, "enabled": False}]})
        self.assertEqual(receipt[0], 200, receipt)
        yard.stop_yard()
        yard.start_yard()
        self.assertFalse(yard.lookup("second")["enabled"])
        self.assertEqual(yard.registry_action("remove", id="legacy")[0], 200)
        original = yard.registry.read_text()
        yard.registry.with_suffix(".tmp").write_text("{interrupted")
        self.assertEqual(yard.http("/api/registry")[1]["registry"][0]["id"], "second")
        yard.registry.write_text("{interrupted")
        self.assertEqual(yard.registry_action("add", service={"id": "third", "port": 8013})[0], 400)
        self.assertEqual(yard.registry.read_text(), "{interrupted")
        yard.registry.write_text(original)
        state = yard.state.joinpath("managed.json")
        state.write_text("{interrupted")
        self.assertIn("state is invalid", yard.http("/api/services?health=0")[1]["state_error"])
        self.assertFalse(yard.action("second", "start")["ok"])
        self.assertEqual(state.read_text(), "{interrupted")

    def test_registry_writes_serialize_across_state_directories(self):
        first = self.yard()
        second = self.yard()
        second.registry = first.registry
        second.env["YARD_CONFIG"] = str(first.registry)
        first.start_yard()
        second.start_yard()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            writes = [pool.submit(yard.registry_action, "add",
                                  service={"id": f"worker-{index}", "port": free_port()})
                      for index, yard in enumerate((first, second))]
            for future in writes:
                self.assertEqual(future.result()[0], 200)
        saved = first.http("/api/registry")[1]["registry"]["services"]
        self.assertEqual({service["id"] for service in saved}, {"worker-0", "worker-1"})

    def test_shared_state_keeps_registries_from_controlling_each_other(self):
        owner = self.yard([{"id": "job", "start": "sleep 30"}])
        other = self.yard([{"id": "job", "start": "sleep 50"}])
        other.env["YARD_DIR"] = str(owner.state)
        owner.start_yard()
        other.start_yard()
        started = owner.action("job", "start")
        self.assertTrue(started["ok"], started)
        self.assertFalse(other.lookup("job")["owned_by_yard"])
        log = other.http("/api/services/job/logs")[1]
        self.assertIn("another registry", log["error"])
        self.assertIn("another registry", other.action("job", "stop")["error"])
        self.assertIn("another registry", other.registry_action("remove", id="job")[1]["error"])
        self.assertTrue(owner.lookup("job")["owned_by_yard"])
        self.assertTrue(owner.action("job", "stop")["ok"])

    def test_process_census_failure_is_visible(self):
        yard = self.yard([{"id": "worker", "start": "sleep 30"}])
        mock = yard.path / "mock"
        mock.mkdir()
        ps = mock / "ps"
        ps.write_text("#!/bin/sh\nexit 1\n")
        ps.chmod(0o755)
        original = yard.env["PATH"]
        yard.env["PATH"] = str(mock) + os.pathsep + original
        try:
            yard.start_yard()
            snapshot = yard.http("/api/services?health=0")[1]
            self.assertFalse(snapshot["ok"])
            self.assertIsNotNone(snapshot["state_error"])
            worker = next(service for service in snapshot["services"] if service["id"] == "worker")
            self.assertEqual(worker["state"], "unknown")
            self.assertFalse(worker["actions"]["start"])
        finally:
            yard.env["PATH"] = original

    def test_validation_available_when_active_registry_is_damaged(self):
        yard = self.yard()
        yard.registry.write_text("{damaged")
        yard.start_yard()
        status, result = yard.registry_action("validate", registry={"services": [{"id": "local", "port": 18020}]})
        self.assertEqual(status, 200, result)
        self.assertEqual(yard.registry.read_text(), "{damaged")

    def test_launch_failures_and_health_diagnostics(self):
        port, slow = free_port(), free_port()
        services = [
            {"id": "bad-command", "start": "yard_nonexistent_command"},
            {"id": "bad-dir", "cwd": "/no-such-yard-directory", "start": "sleep 5"},
            {"id": "missing-runtime", "start": "sleep 5", "executable": "yard_missing_runtime"},
            {"id": "missing-env", "start": "sleep 5", "env": ["YARD_NONEXISTENT_TEST_VAR"]},
            {"id": "http-unhealthy", "start": fixture_command(port), "port": port,
             "health": local(port) + "/bad", "startup_timeout": 1},
            {"id": "http-timeout", "start": fixture_command(slow), "port": slow,
             "health": local(slow) + "/slow", "startup_timeout": 1},
            {"id": "worker", "start": "sleep 2", "health_type": "process"},
        ]
        yard = self.yard(services)
        yard.start_yard()
        for key, message in [("bad-command", "exited"), ("bad-dir", "does not exist"),
                             ("missing-runtime", "executable is unavailable"), ("missing-env", "environment variables"),
                             ("http-unhealthy", "unhealthy"), ("http-timeout", "timeout")]:
            with self.subTest(service=key):
                outcome = yard.action(key, "start")
                self.assertFalse(outcome["ok"], outcome)
                self.assertIn(message, outcome["error"])
        self.assertIn("not found", str(yard.http("/api/services/bad-command/logs")[1]))
        self.assertEqual(yard.lookup("http-unhealthy", health=True)["http_status"], 503)
        self.assertTrue(yard.action("worker", "start")["ok"])
        self.assertEqual(yard.lookup("worker")["health_status"], "process")
        eventually(lambda: yard.lookup("worker")["state"] == "failed")

    def test_tcp_readiness_uses_listener_address_family(self):
        try:
            with socket.socket(socket.AF_INET6) as fixture:
                fixture.bind(("::1", 0))
                port = fixture.getsockname()[1]
        except OSError as exc:
            self.skipTest(f"IPv6 loopback is unavailable: {exc}")
        yard = self.yard([{"id": "ipv6", "port": port, "start": fixture_command(port, "--ipv6")}])
        yard.start_yard()
        outcome = yard.action("ipv6", "start")
        self.assertTrue(outcome["ok"], outcome)
        status = yard.lookup("ipv6", health=True)
        self.assertEqual(status["ip_version"], "IPv6")
        self.assertEqual(status["health_status"], "healthy")
        self.assertTrue(yard.action("ipv6", "stop")["ok"])

    def test_tcp_shutdown_failure_and_confirmation(self):
        port = free_port()
        yard = self.yard([{"id": "slow-stop", "port": port,
                           "start": fixture_command(port, "--ignore-term"), "shutdown_timeout": 1}])
        yard.start_yard()
        self.assertTrue(yard.action("slow-stop", "start")["ok"])
        before = yard.lookup("slow-stop", health=True)
        self.assertEqual(before["health_status"], "healthy")
        self.assertIn("still running after SIGTERM", yard.action("slow-stop", "restart")["error"])
        self.assertEqual(yard.lookup("slow-stop")["process_group"], before["process_group"])
        self.assertTrue(yard.action("slow-stop", "stop", force=True)["needs_confirm"])
        self.assertFalse(yard.action("slow-stop", "stop", force="true", confirm=True, target=1)["ok"])
        self.assertEqual(yard.registry_action("remove", id="slow-stop")[0], 400)
        self.assertEqual(yard.action("slow-stop", "stop", force=True, confirm=True,
                                     target=before["process_group"])["signal"], "KILL")
        self.assertEqual(yard.lookup("slow-stop")["state"], "stopped")

    def test_request_guards_and_concurrency(self):
        yard = self.yard([{"id": "job", "start": "sleep 30"}])
        yard.start_yard()
        self.assertEqual(yard.http("/", headers={"Host": "external.invalid"}, raw=True)[0], 403)
        self.assertEqual(yard.http("/api/registry", headers={"Origin": "http://external.invalid"})[0], 403)
        path = "/api/services/job/start"
        self.assertEqual(yard.http(path, {})[0], 403)
        self.assertEqual(yard.http(path, {"token": "invalid"})[0], 403)
        self.assertEqual(yard.http(path, b"{")[0], 400)
        self.assertEqual(yard.http(path, b"{}" * 140000)[0], 413)
        self.assertEqual(yard.http(path, b"{}", {"Content-Type": "text/plain"})[0], 415)
        self.assertFalse(yard.action("missing", "start")["ok"])
        self.assertEqual(yard.http("/api/services/job/unsupported", {}, raw=True)[0], 404)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            attempts = list(pool.map(lambda _: yard.action("job", "start"), range(3)))
        self.assertEqual(sum(result["ok"] for result in attempts), 1, attempts)
        self.assertTrue(yard.action("job", "stop")["ok"])

    def test_discovery_manifests_and_scan_failure(self):
        yard = self.yard()
        node = yard.path / "node-project"
        node.mkdir()
        node.joinpath("package.json").write_text('{"scripts":{"dev":"touch ../should-not-exist"}}')
        yard.path.joinpath("symlink-project").symlink_to(node, target_is_directory=True)
        yard.start_yard()
        result = yard.post("/api/discovery/projects", root=str(yard.path))[1]
        self.assertEqual([project["name"] for project in result["receipt"]], ["node-project"])
        self.assertEqual(result["receipt"][0]["start"], "npm run dev")
        self.assertFalse(yard.path.joinpath("should-not-exist").exists())
        self.assertFalse(yard.post("/api/discovery/projects", root="/no-such-yard-directory")[1]["ok"])
        mock = yard.path / "mock"
        mock.mkdir()
        lsof = mock / "lsof"
        lsof.write_text("#!/bin/sh\necho 'permission denied' >&2\nexit 1\n")
        lsof.chmod(0o755)
        yard.env["PATH"] = str(mock) + ":" + os.environ["PATH"]
        report = yard.cli("scan", "--no-health", "--json")
        self.assertEqual(report.returncode, 1)
        self.assertIn("listener scan failed", json.loads(report.stdout)["scan_error"])
        lsof.write_text("#!/bin/sh\necho 'unexpected lsof output'\n")
        self.assertIn("scan incomplete", yard.cli("scan", "--no-health", "--json").stdout)

    def test_log_limits_and_environment_redaction(self):
        command = """python3 -u -c 'import os,time; print("x"*1300000); print(os.environ["YARD_TEST_SECRET"]); time.sleep(10)'"""
        yard = self.yard([{"id": "logger", "start": command, "env": ["YARD_TEST_SECRET"]}])
        yard.env["YARD_TEST_SECRET"] = "secret-fixture-value-never-returned"
        yard.start_yard()
        self.assertTrue(yard.action("logger", "start")["ok"])
        log = yard.state / "private-logs" / "logger.log"
        self.assertLessEqual(log.stat().st_size, 1024 * 1024)
        response = yard.http("/api/services/logger/logs")[1]
        self.assertNotIn(yard.env["YARD_TEST_SECRET"], str(response))
        self.assertIn("[redacted]", str(response))
        self.assertTrue(yard.action("logger", "stop")["ok"])

    @unittest.skipUnless(shutil.which("npm"), "Node/npm is optional")
    def test_node_package_foreground_launch(self):
        yard = self.yard()
        port = free_port()
        yard.path.joinpath("package.json").write_text('{"scripts":{"dev":"node server.js"}}')
        yard.path.joinpath("server.js").write_text(
            f"require('node:http').createServer((req,res) => res.end('Yard Node fixture')).listen({port}, '127.0.0.1');")
        yard.write([{"id": "node", "name": "Node fixture", "start": "npm run dev", "executable": "npm",
                     "port": port, "health": local(port), "startup_timeout": 6}])
        yard.start_yard()
        outcome = yard.action("node", "start")
        self.assertTrue(outcome["ok"], outcome)
        with request.urlopen(local(port), timeout=1) as response:
            self.assertEqual(response.read(), b"Yard Node fixture")
        self.assertEqual(yard.action("node", "stop")["signal"], "TERM")

    def test_default_launcher_reuses_the_listening_instance(self):
        yard = self.yard()
        yard.start_yard()
        before = yard.token
        self.assertEqual(yard.cli().stdout.strip(), yard.url)
        self.assertEqual(yard.cli("open").stdout.strip(), yard.url)
        self.assertIn(before, yard.http("/", raw=True)[1])
        self.assertEqual(yard.cli("doctor", "--json").returncode, 0)
        yard.stop_yard()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            launches = list(pool.map(lambda _: yard.cli(), range(3)))
        for launched in launches:
            self.assertEqual(launched.returncode, 0, launched)
            self.assertEqual(launched.stdout.strip(), yard.url, launched)
        self.assertEqual(yard.http("/api/identity")[1]["config"], str(yard.registry))
        self.assertNotIn(before, yard.http("/", raw=True)[1])
        listener = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{yard.port}", "-sTCP:LISTEN", "-Fp"], text=True).splitlines()
        pids = [int(field[1:]) for field in listener if field.startswith("p")]
        self.assertEqual(len(pids), 1, listener)
        pid = pids[0]
        command = subprocess.check_output(["ps", "-o", "command=", "-p", str(pid)], text=True)
        self.assertIn(f"/yard.kujo serve {yard.port}", command)
        try:
            self.assertEqual(yard.cli().stdout.strip(), yard.url)
        finally:
            os.kill(pid, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main(verbosity=2)

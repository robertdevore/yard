#!/usr/bin/env python3
"""POSIX session supervisor. Only a live session leader can signal its group."""
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeout
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

LOG_LIMIT = 1024 * 1024


def members(group):
    output = subprocess.check_output(["ps", "-axo", "pid=,pgid=,stat="], text=True, timeout=1, start_new_session=True)
    return [int(pid) for pid, pgid, state in map(str.split, output.splitlines())
            if int(pgid) == group and int(pid) != group and not state.startswith("Z")]


def private_directory(path):
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("Yard control directory must be owned by this user with mode 0700")


def open_log(path, require_private=True):
    if require_private:
        private_directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
        os.close(fd)
        raise ValueError("Unsafe service log path")
    os.fchmod(fd, 0o600)
    os.ftruncate(fd, 0)
    return os.fdopen(fd, "wb", buffering=0)


def drain(pipe, log, secrets):
    # Redact configured environment values even across read boundaries.
    pattern = re.compile(b"|".join(map(re.escape, sorted(secrets, key=len, reverse=True)))) if secrets else None
    keep = max(map(len, secrets), default=1) - 1
    pending = b""
    with pipe, log:
        while True:
            chunk = pipe.read1(16384)
            pending += chunk
            end = len(pending) if not chunk else max(0, len(pending) - keep)
            if pattern:
                pieces = []
                cursor = 0
                for match in pattern.finditer(pending):
                    if match.start() >= end:
                        break
                    pieces.extend((pending[cursor:match.start()], b"[redacted]"))
                    cursor = match.end()
                end = max(end, cursor)
                pieces.append(pending[cursor:end])
                output = b"".join(pieces)
            else:
                output = pending[:end]
            pending = pending[end:]
            if log.tell() + len(output) > LOG_LIMIT:
                log.truncate(0)
                log.seek(0)
            log.write(output)
            if not chunk:
                break


def supervise(spec):
    group = os.getpid()
    if os.getpgrp() != group:
        raise ValueError("Yard supervisor requires its own process group")
    stopping = False
    sock = spec["socket"]
    try:
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(sock)
            server.listen(8)
            server.settimeout(0.25)
            signal.signal(signal.SIGTERM, lambda *_: None)
            env = dict(os.environ)
            env["PWD"] = spec["cwd"]
            names = set(spec["env"])
            names.update(name for name, value in env.items() if len(value) >= 6 and
                         re.search(r"SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|DATABASE_URL", name, re.I))
            secrets = [env[name].encode() for name in names if env.get(name)]
            log = open_log(Path(spec["log"]))
            try:
                child = subprocess.Popen(
                    ["/bin/sh", "-c", spec["start"]], cwd=spec["cwd"], env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
            except BaseException:
                log.close()
                raise
            writer = threading.Thread(target=drain, args=(child.stdout, log, secrets), daemon=True)
            writer.start()
            while child.poll() is None or members(group):
                try:
                    client, _ = server.accept()
                except socket.timeout:
                    continue
                with client:
                    client.settimeout(0.25)
                    try:
                        with client.makefile("rb") as stream:
                            request = json.loads(stream.readline(4096))
                        if not hmac.compare_digest(request["token"], spec["token"]):
                            continue
                        action = request["action"]
                        if action in ("stop", "force"):
                            stopping = True
                        receipt = {"pid": group, "child": child.pid, "stopping": stopping}
                        client.sendall(json.dumps(receipt).encode())
                    except (OSError, ValueError, KeyError, TypeError):
                        continue
                    if action in ("stop", "force"):
                        # The supervisor is the process-group leader. It never sends a
                        # signal to an arbitrary numeric group received from a client.
                        os.killpg(group, signal.SIGKILL if action == "force" else signal.SIGTERM)
            writer.join(timeout=0.5)
    finally:
        Path(sock).unlink(missing_ok=True)


def request(spec, action):
    address = spec["socket"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]{24,64}\.sock", address):
        raise ValueError("Invalid supervisor address")
    for _ in range(3):
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(0.6)
                client.connect(address)
                client.sendall(json.dumps({"token": spec["token"], "action": action}).encode() + b"\n")
                with client.makefile("rb") as stream:
                    raw = stream.read(4096)
                    if raw:
                        return json.loads(raw)
        except (FileNotFoundError, ConnectionRefusedError):
            return None
        except (ConnectionResetError, BrokenPipeError):
            pass
        # The server can exit after a connect enters its accept backlog.
        time.sleep(0.02)
    raise ValueError("Supervisor did not verify this ownership record")


def command(action, spec):
    if action == "launch":
        runtime = spec.get("executable")
        if runtime:
            executable = str(Path(spec["cwd"]) / runtime) if "/" in runtime else runtime
            if not shutil.which(executable):
                raise ValueError(f"Required executable is unavailable: {runtime}")
        missing = [name for name in spec["env"] if not os.environ.get(name)]
        if missing:
            raise ValueError("Missing required environment variables: " + ", ".join(missing))
        if spec.get("port"):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    probe.bind(("127.0.0.1", spec["port"]))
                except OSError as error:
                    raise ValueError(f"Port {spec['port']} is unavailable: {error.strerror}") from error
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "supervise", json.dumps(spec)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(40):
            if proc.poll() is not None:
                raise ValueError("Startup command exited immediately. Check the service log.")
            receipt = request(spec, "status")
            if receipt:
                return receipt
            time.sleep(0.025)
        raise ValueError("Supervisor did not confirm startup. Check the service log.")
    receipt = request(spec, action)
    if action == "status" or receipt is None:
        return receipt
    deadline = time.monotonic() + spec["shutdown_timeout"]
    while time.monotonic() < deadline:
        if request(spec, "status") is None and not members(receipt["pid"]):
            Path(spec["socket"]).unlink(missing_ok=True)
            return receipt
        time.sleep(0.075)
    raise ValueError(f"Process group {receipt['pid']} is still running after "
                     f"{'SIGKILL' if action == 'force' else 'SIGTERM'}")


def probe(spec):
    started = time.monotonic()
    timeout = spec["timeout"]
    if spec["kind"] == "tcp":
        try:
            with socket.create_connection(("127.0.0.1", spec["port"]), timeout=timeout):
                return {"status": "healthy", "response_ms": round((time.monotonic() - started) * 1000)}
        except socket.timeout:
            return {"status": "timeout"}
        except OSError:
            return {"status": "connection_failed"}
    try:
        result = subprocess.run(
            ["curl", "-q", "-g", "-s", "-o", "/dev/null", "-w", "%{http_code} %{time_total}",
             "--proto", "=http,https", "--noproxy", "*", "--max-time", str(timeout), "--", spec["url"]],
            capture_output=True, text=True, timeout=timeout + 0.15,
        )
        return {"exitcode": result.returncode, "stdout": result.stdout}
    except subprocess.TimeoutExpired:
        return {"exitcode": 28, "stdout": ""}
    except OSError:
        return {"status": "unknown"}


def discover(root):
    root = Path(root).expanduser()
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Select an existing absolute project directory")
    root = root.resolve()
    candidates = [root]
    with os.scandir(root) as children:
        for index, child in enumerate(children):
            if index >= 500:
                break
            if child.is_dir(follow_symlinks=False) and not child.name.startswith(".") and child.name not in ("node_modules", "vendor"):
                candidates.append(Path(child.path))
    projects = []
    manifests = {"package.json": "Node.js", "pyproject.toml": "Python", "requirements.txt": "Python",
                 "kujo.toml": "Kujo", "Cargo.toml": "Rust", "compose.yaml": "Containers",
                 "docker-compose.yml": "Containers", "Procfile": "Procfile"}
    for directory in candidates:
        for name, runtime in manifests.items():
            manifest = directory / name
            if manifest.is_symlink() or not manifest.is_file():
                continue
            command = None
            if name == "package.json" and manifest.stat().st_size <= 131072:
                try:
                    scripts = json.loads(manifest.read_text()).get("scripts", {})
                    for script in ("dev", "start"):
                        if isinstance(scripts.get(script), str):
                            command = f"npm run {script}"
                            break
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
            projects.append({"name": directory.name, "cwd": str(directory), "runtime": runtime,
                             "start": command, "evidence": name, "confidence": "Manifest candidate"})
            break
        if len(projects) >= 75:
            break
    return sorted(projects, key=lambda project: project["name"].casefold())


def inspect_process(pid):
    result = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        capture_output=True, text=True, timeout=1,
    )
    cwd = next((line[1:] for line in result.stdout.splitlines() if line.startswith("n/")), None)
    repository = None
    if cwd:
        try:
            git = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, timeout=1)
            if git.returncode == 0:
                repository = git.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"cwd": cwd, "repository": repository,
            "confidence": "Verified working directory and Git root" if repository else
                          "Verified working directory" if cwd else "Working directory unavailable"}


def diagnostics(action, spec):
    if action == "discover":
        return discover(spec["root"])
    if action == "inspect":
        return inspect_process(spec["pid"])
    if action == "health":
        results = {}
        items = list(spec.items())
        if len(items) > 16:
            # Rotate the first batch between dashboard refreshes so expensive
            # targets late in a long list still receive probe time.
            offset = (int(time.time() / 4) * 16) % len(items)
            items = items[offset:] + items[:offset]
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {pool.submit(probe, target): key for key, target in items}
            try:
                for complete in as_completed(futures, timeout=1.05):
                    results[futures[complete]] = complete.result()
            except FutureTimeout:
                for pending in futures:
                    pending.cancel()
        return results
    if action == "snapshot":
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,pgid=,ppid=,stat=,comm="], text=True, timeout=1)
        processes = {}
        for line in output.splitlines():
            fields = line.split(maxsplit=4)
            if len(fields) == 5 and not fields[3].startswith("Z"):
                pid, group, parent, _, executable = fields
                processes[pid] = {"group": int(group), "parent": int(parent), "executable": executable}
        owned = {}
        for key, service in spec["entries"].items():
            try:
                os.chdir(service["control_dir"])
                receipt = request(service, "status")
                if receipt and str(receipt["pid"]) in processes:
                    owned[key] = receipt
            except (OSError, ValueError):
                pass
        return {"processes": processes, "owned": owned}
    if action == "groups":
        output = subprocess.check_output(["ps", "-axo", "pid=,pgid=,stat="], text=True, timeout=1)
        return {pid: int(group) for pid, group, state in map(str.split, output.splitlines())
                if not state.startswith("Z")}
    raise ValueError("Unknown supervisor operation")


def main():
    if sys.argv[1] == "dashboard":
        kujo, script, port, path = sys.argv[2:]
        with open_log(Path(path), require_private=False) as log:
            subprocess.Popen(
                [kujo, "run", script, "serve", port],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return
    action, raw = sys.argv[1:]
    spec = json.loads(raw)
    if action in ("groups", "snapshot", "health", "discover", "inspect"):
        print(json.dumps({"ok": True, "receipt": diagnostics(action, spec)}))
        return
    private_directory(Path(spec["control_dir"]))
    os.chdir(spec["control_dir"])
    if action == "supervise":
        supervise(spec)
    else:
        print(json.dumps({"ok": True, "receipt": command(action, spec)}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        sys.exit(1)

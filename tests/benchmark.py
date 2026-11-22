"""Measure Yard launch, dashboard response, status polling and macOS/Linux RSS."""
from contextlib import ExitStack
import json
import socket
import statistics
import subprocess
import time

from support import YardFixture, local


def median_ms(operation, repeats=5, interval=0):
    results = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        results.append(round((time.perf_counter() - started) * 1000, 1))
        if interval:
            time.sleep(interval)
    return {"median_ms": statistics.median(results), "samples_ms": results}


def sample(services):
    with YardFixture(services) as yard:
        started = time.perf_counter()
        yard.start_yard()
        cold = round((time.perf_counter() - started) * 1000, 1)
        html = median_ms(lambda: yard.http("/", raw=True))
        status = median_ms(lambda: yard.http("/api/services"), interval=1.1)
        time.sleep(1)
        usage = subprocess.check_output(
            ["ps", "-o", "rss=,%cpu=", "-p", str(yard.server.pid)], text=True).split()
        return {"registered_services": len(services), "cold_to_first_page_ms": cold, "dashboard_html": html,
                "uncached_refresh": status, "idle_rss_kib": int(usage[0]), "idle_cpu_percent": float(usage[1])}


def main():
    print(json.dumps({"idle_registry": sample([{"id": "worker", "start": "sleep 100"}])}), flush=True)
    with ExitStack() as stack:
        services = [{"id": f"stopped-{index}", "port": 18000 + index} for index in range(40)]
        for index in range(24):
            sock = stack.enter_context(socket.socket())
            sock.bind(("127.0.0.1", 0))
            sock.listen(128)
            port = sock.getsockname()[1]
            services.append({"id": f"hung-{index}", "port": port,
                             "health": local(port) + "/health", "probe_timeout_ms": 400})
        print(json.dumps({"mixed_registry": sample(services)}), flush=True)


if __name__ == "__main__":
    main()

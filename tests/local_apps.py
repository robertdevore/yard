"""Optional smoke test for inspected local RepoRadar and Cron Control Surface checkouts."""
import os
from pathlib import Path
from urllib.request import urlopen

from support import YardFixture, local


def run():
    projects = Path(os.environ.get("YARD_PROJECTS_HOME", Path.home() / "2026"))
    services = [
        {"id": "reporadar", "cwd": str(projects / "reporadar"), "executable": "kujo",
         "start": "kujo run src/main.kujo serve 8080", "port": 8080, "health": local(8080), "startup_timeout": 8},
        {"id": "cron-control", "cwd": str(projects / "crontrol-surface"), "executable": "kujo",
         "start": "./run.command", "port": 8765, "health": local(8765), "startup_timeout": 8},
    ]
    with YardFixture(services) as yard:
        home = yard.path / "home"
        home.mkdir()
        yard.env.update(HOME=str(home), REPORADAR_DB=str(yard.path / "reporadar.db"),
                        CRON_CONTROL_PORT="8765", CRON_CONTROL_HOST="127.0.0.1", CRON_CONTROL_ENABLE_RUN="0")
        yard.start_yard()
        for service in services:
            sid = service["id"]
            started = yard.action(sid, "start")
            assert started["ok"], (started, yard.http(f"/api/services/{sid}/logs")[1])
            with urlopen(service["health"], timeout=1) as response:
                assert response.status == 200 and response.read(100)
            assert yard.lookup(sid, health=True)["health_status"] == "healthy"
            stopped = yard.action(sid, "stop")
            assert stopped["ok"], stopped
            assert yard.lookup(sid)["state"] == "stopped"
            print(f"{sid}: HTTP 200, verified Yard ownership, graceful stop", flush=True)


if __name__ == "__main__":
    run()

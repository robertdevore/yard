"""End-to-end browser checks. Requires the Playwright Python package and Chrome/Chromium."""
import os
from pathlib import Path
import subprocess

from playwright.sync_api import expect, sync_playwright

from support import ROOT, YardFixture, fixture_command, free_port, local


def run():
    expect.set_options(timeout=12000)
    output = Path(os.environ.get("YARD_SCREENSHOTS", ROOT / "docs" / "screenshots"))
    output.mkdir(parents=True, exist_ok=True)
    demo, external, backend = free_port(), free_port(), free_port()
    services = [
        {"id": "dashboard", "name": "Local Dashboard", "group": "Developer tools",
         "description": "Python dashboard used for Yard verification", "favorite": True,
         "start": fixture_command(demo) + " & wait", "port": demo, "open": local(demo), "health": local(demo)},
        {"id": "jobs", "name": "Background Worker", "group": "Developer tools",
         "description": "Process-only task worker", "start": "sleep 300"},
        {"id": "docs", "name": "Documentation Preview", "group": "Web",
         "description": "Local preview server", "port": backend, "start": fixture_command(backend)},
        {"id": "missing", "name": "Offline API", "group": "Web",
         "description": "Fixture with a missing startup dependency", "start": "yard_browser_missing_command"},
    ]
    with YardFixture(services) as yard, sync_playwright() as playwright:
        repo = yard.path / "discovered-project"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        repo.joinpath("package.json").write_text('{"scripts":{"dev":"never-run-this"}}')
        listener = yard.serve_external(external, cwd=repo)
        yard.start_yard()
        mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        executable = os.environ.get("YARD_CHROMIUM") or (str(mac_chrome) if mac_chrome.exists() else None)
        browser = playwright.chromium.launch(executable_path=executable)
        context = browser.new_context(viewport={"width": 1280, "height": 850}, reduced_motion="reduce")
        page = context.new_page()
        page.set_default_timeout(12000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(yard.url)

        def row(name):
            return page.locator("li.service-row").filter(has=page.get_by_role("button", name=name, exact=True))

        expect(page.get_by_role("heading", name="Your localhost control center")).to_be_visible()
        expect(row("Local Dashboard")).to_contain_text("Stopped")
        add = page.get_by_role("button", name="Add Service")
        add.focus()
        expect(add).to_be_focused()
        assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "solid"
        page.keyboard.press("Enter")
        expect(page.get_by_label("Application name")).to_be_focused()
        page.keyboard.press("Escape")
        expect(add).to_be_focused()

        page.get_by_role("searchbox").fill("background")
        expect(row("Background Worker")).to_be_visible()
        expect(row("Local Dashboard")).to_have_count(0)
        page.get_by_role("searchbox").clear()
        page.locator("#group").select_option("Web")
        expect(row("Documentation Preview")).to_be_visible()
        expect(row("Local Dashboard")).to_have_count(0)
        page.locator("#group").select_option("")
        page.locator("#sort").select_option("name")
        expect(page.locator(".name-button").first).to_have_text("Background Worker")
        page.locator("#sort").select_option("favorite")
        expect(page.locator(".name-button").first).to_have_text("Local Dashboard")

        page.get_by_role("button", name="Start Local Dashboard").click()
        expect(row("Local Dashboard")).to_contain_text("Healthy")
        with page.expect_popup() as popup:
            page.get_by_role("link", name="Open Local Dashboard").click()
        child_page = popup.value
        expect(child_page.get_by_text("Yard HTTP fixture")).to_be_visible()
        child_page.close()
        page.get_by_role("button", name="More actions for Local Dashboard").click()
        page.get_by_text("Recent logs", exact=True).click()
        expect(page.get_by_text("Fixture ready", exact=False)).to_be_visible()
        page.get_by_role("button", name="Restart", exact=True).click()
        expect(page.get_by_role("status").first).to_contain_text("Readiness confirmed")
        expect(row("Local Dashboard")).to_contain_text("Healthy")
        assert yard.lookup("dashboard")["restart_count"] == 1

        add.click()
        page.get_by_label("Application name").fill("Temporary Service")
        page.get_by_label("Startup command", exact=True).fill("sleep 30")
        page.get_by_text("I reviewed the startup command").click()
        page.get_by_role("button", name="Save service").click()
        expect(row("Temporary Service")).to_be_visible()
        row("Temporary Service").get_by_role("button", name="Temporary Service", exact=True).click()
        page.get_by_role("button", name="Edit Service").click()
        page.get_by_label("Application name").fill("Updated Service")
        page.get_by_role("button", name="Save service").click()
        expect(row("Updated Service")).to_be_visible()
        assert yard.http("/api/registry")[1]["registry"]["services"][-1]["id"] == "temporary-service"
        row("Updated Service").get_by_role("button", name="Updated Service", exact=True).click()
        page.get_by_role("button", name="Remove", exact=True).click()
        page.get_by_role("button", name="Remove", exact=True).click()
        expect(row("Updated Service")).to_have_count(0)

        page.get_by_role("button", name="Discovery").click()
        discovered = page.locator("#listeners li").filter(has_text=f"PID {listener.pid}")
        discovered.get_by_role("button", name="Inspect").click()
        expect(page.get_by_text("Verified working directory and Git root")).to_be_visible()
        page.get_by_role("button", name="Register listener").click()
        page.get_by_label("Application name").fill("Externally Started Preview")
        page.get_by_role("button", name="Save service").click()
        expect(row("Externally Started Preview")).to_contain_text("External listener")
        assert yard.lookup(f"service-{external}")["owned_by_yard"] is False
        page.get_by_role("button", name="Discovery").click()
        page.get_by_label("Directory to scan").fill(str(yard.path))
        page.get_by_role("button", name="Scan directory").click()
        expect(page.locator("#projects")).to_contain_text("discovered-project")
        page.get_by_role("button", name="Services").click()

        page.get_by_role("button", name="Start Offline API").click()
        expect(row("Offline API")).to_contain_text("Failed")
        expect(page.get_by_role("status").first).to_contain_text("exited")
        page.locator("#status").select_option("attention")
        expect(row("Local Dashboard")).to_have_count(0)
        expect(row("Offline API")).to_be_visible()
        page.locator("#status").select_option("")
        page.get_by_role("button", name="Start Background Worker").click()
        expect(row("Background Worker")).to_contain_text("Process verified")
        page.locator("#notice").evaluate("node => node.hidden = true")

        page.screenshot(path=output / "yard-laptop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_role("button", name="Add Service")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=output / "yard-narrow.png", full_page=True)

        page.get_by_role("button", name="Stop Local Dashboard").click()
        expect(row("Local Dashboard")).to_contain_text("Stopped")
        assert yard.lookup("dashboard")["owned_by_yard"] is False
        page.get_by_role("button", name="Stop Background Worker").click()
        expect(row("Background Worker")).to_contain_text("Stopped")
        assert not errors, errors
        browser.close()
    print(f"Yard browser workflow passed. Screenshots: {output}")


if __name__ == "__main__":
    run()

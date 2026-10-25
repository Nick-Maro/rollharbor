"""Exercise a fresh original demo in Chromium, without reading a real save."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import StateStore
from server import LocalServer
from tools.setup_demo import initialize


def run(screenshots: Path) -> dict:
    from playwright.sync_api import sync_playwright

    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="il-tavolo-public-") as temporary:
        root = Path(temporary)
        shutil.copytree(ROOT / "web", root / "web")
        shutil.copytree(ROOT / "examples/demo", root / "examples/demo")
        initialize(root)
        store = StateStore(root)
        server = LocalServer(("127.0.0.1", 0), root)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        errors, failed_requests = [], []
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: failed_requests.append(f"{response.status} {response.url}")
                        if response.status >= 400 else None)
                page.goto(base, wait_until="networkidle")
                page.wait_for_function("document.querySelector('#connection').classList.contains('online')")
                assert page.locator("#campaign-title").inner_text() == "Le lanterne di Portolume"
                assert page.locator("#map-pins .map-pin").count() == 4
                assert store.read()["party"] == []
                page.locator('nav [data-view="personaggio"]').click()
                page.screenshot(path=str(screenshots / "characters.png"), full_page=False, animations="disabled")
                # Fictional fixtures exist only inside this temporary demo.
                for name, class_id, species_id in (("Ada", "fighter", "human"), ("Bruno", "cleric", "hill_dwarf"),
                                                   ("Cleo", "rogue", "lightfoot_halfling"), ("Dario", "wizard", "high_elf")):
                    store.create_character({"name": name, "class_id": class_id, "species_id": species_id})
                before = store.read()
                assert len(before["party"]) == 4 and not StateStore.has_started(before)
                page.reload(wait_until="networkidle")
                page.wait_for_function("document.querySelector('#connection').classList.contains('online')")
                page.locator('nav [data-view="atlante"]').click()
                page.screenshot(path=str(screenshots / "table.png"), full_page=False, animations="disabled")
                assert store.read()["location_id"] == "portolume"
                assert page.request.get(base + "/master/CURRENT.md").status == 404
                assert page.request.get(base + "/data/campaign.json").status == 404
                for url, heading in (("/maps.html", "Cartoteca"), ("/artworks.html", "Illustrazioni")):
                    page.goto(base + url, wait_until="networkidle")
                    assert page.locator("h1").count() == 1
                    if url == "/maps.html":
                        page.wait_for_function("document.querySelector('#map-image').naturalWidth > 0")
                    assert page.locator("img").evaluate_all("images => images.every(img => !img.complete || img.naturalWidth > 0)")
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(base, wait_until="networkidle")
                page.wait_for_function("document.querySelector('#connection').classList.contains('online')")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2"), "Horizontal overflow on mobile"
                page.screenshot(path=str(screenshots / "mobile.png"), full_page=False, animations="disabled")
                assert store.read() == before, "Viewing the table changed game state"
                assert not errors, errors
                assert not failed_requests, failed_requests
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    return {"ok": True, "desktop": True, "mobile": True, "private_routes_blocked": True,
            "screenshots": str(screenshots), "real_campaign_read": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, default=ROOT / "tests/.artifacts/public-demo")
    args = parser.parse_args()
    print(json.dumps(run(args.screenshots), ensure_ascii=False))

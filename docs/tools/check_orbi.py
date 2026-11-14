"""Check Orbi (the AI assistant) in a real browser, with screenshots.

The AI relay is ALWAYS mocked here: the real endpoint is never called (it has a small free daily quota).

Run from the docs/ folder:
    python3 -m http.server 8765 --bind 127.0.0.1      (in another terminal)
    python3 tools/check_orbi.py [folder for the screenshots]
Needs: pip install playwright && playwright install chromium
"""
import json
import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/index.html"
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
failures = []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)


class Relay:
    """Fake AI relay: answers every request to *.workers.dev itself and remembers what was sent."""

    def __init__(self, page):
        self.status = 200
        self.bodies = []
        page.route("**/*workers.dev/**", self.handle)
        page.route("**/*workers.dev", self.handle)

    def handle(self, route):
        self.bodies.append(json.loads(route.request.post_data or "{}"))
        if self.status == 429:
            route.fulfill(status=429, content_type="application/json", body='{"error":"quota"}')
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"answer": "MOCKED AI ANSWER: this text comes from the test, not from a real model."}))


# Rectangles [left, top, right, bottom] of things on the page, and "does A touch B?"
RECTS_JS = """() => {
  const rect = sel => { const e = document.querySelector(sel); if (!e) return null;
    const b = e.getBoundingClientRect(); return b.width && b.height ? [b.left, b.top, b.right, b.bottom] : null; };
  return { fab: rect('#orbi-fab'), chat: rect('#orbi-chat'), char: rect('#orbi-char'), bubble: rect('#orbi-bubble'),
           panel: rect('#panel'), topbar: rect('#topbar'), legend: rect('#legend'),
           zoom: rect('.leaflet-control-zoom'), layers: rect('.leaflet-control-layers'), attribution: rect('.leaflet-control-attribution') };
}"""


def touches(a, b):
    return bool(a and b and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


def no_overlap(page, mine, others, label):
    r = page.evaluate(RECTS_JS)
    for m in mine:
        for o in others:
            check(not touches(r[m], r[o]), f"{label}: Orbi's {m} does not cover the {o}")


def ask(page, text):
    """Type a question, send it, wait until Orbi has finished typing his answer. Returns the answer."""
    page.fill("#orbi-chat input", text)
    page.press("#orbi-chat input", "Enter")
    return wait_answer(page)


def chip(page, text):
    page.click(f"#orbi-chat .orbi-chips button:has-text(\"{text}\")")
    return wait_answer(page)


def wait_answer(page):
    page.wait_for_function("!document.querySelector('#orbi-chat .orbi-form button').disabled")
    # the answer is typed letter by letter: wait until its length stops growing
    last = -1
    while True:
        page.wait_for_timeout(500)
        text = page.evaluate("[...document.querySelectorAll('#orbi-chat .orbi-msg.bot .body')].pop().textContent")
        if len(text) == last:
            return text
        last = len(text)


CONTROLS = ["panel", "topbar", "legend", "zoom", "layers", "attribution"]

with sync_playwright() as p:
    browser = p.chromium.launch()

    # ------------------------------------------------------------------ desktop, full flow
    print("DESKTOP 1366x768")
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # ("Failed to load resource" lines are not JavaScript errors: the mocked 429, or a map tile that did not download)
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    relay = Relay(page)
    page.goto(URL)
    page.wait_for_selector("#legend .legend-title")
    page.wait_for_timeout(1200)
    page.screenshot(path=f"{OUT}/1_intro.png")
    check(page.evaluate("!document.querySelector('#orbi-char').classList.contains('in') && !document.querySelector('#orbi-fab').classList.contains('show')"),
          "Orbi is hidden while the intro is open")

    page.click("#intro-explore")
    page.wait_for_selector("#orbi-bubble.show")
    page.wait_for_timeout(3200)
    page.screenshot(path=f"{OUT}/2_greeting.png")
    check("Hi, Earthling" in page.inner_text("#orbi-bubble"), "greeting bubble after 'Explore the map'")
    no_overlap(page, ["char", "bubble"], CONTROLS, "greeting")

    page.wait_for_selector("#orbi-fab.show", timeout=15000)
    page.wait_for_timeout(600)
    page.screenshot(path=f"{OUT}/3_docked.png")
    no_overlap(page, ["fab"], CONTROLS, "docked")

    page.click("#orbi-fab")
    page.wait_for_selector("#orbi-chat.show")
    page.wait_for_timeout(3500)
    page.screenshot(path=f"{OUT}/4_chat_open.png")
    no_overlap(page, ["chat", "char"], CONTROLS, "chat open")

    # typing in the chat must not move or zoom the map
    zoom_before = page.evaluate("map.getZoom()")
    page.fill("#orbi-chat input", "")
    page.type("#orbi-chat input", "+-+")
    page.press("#orbi-chat input", "ArrowLeft")
    page.wait_for_timeout(400)
    check(page.evaluate("map.getZoom()") == zoom_before, "typing + and - in the chat does not zoom the map")
    page.fill("#orbi-chat input", "")

    # 1) data answer: no AI call
    a = chip(page, "Best site for Mars?")
    check("the best match is" in a and len(relay.bodies) == 0, "data answer ('Best site for Mars?') without calling the AI")
    page.click("#orbi-chat .orbi-msg .act")
    page.wait_for_timeout(2600)
    page.screenshot(path=f"{OUT}/5_show_on_map.png")
    check(page.evaluate("selectedSiteId !== null && currentTab === 'site' && document.querySelector('#panel-content h2') !== null"),
          "'Show it on the map' selects the site and opens its card")
    best = page.evaluate("getRanking()[0].site.id === selectedSiteId")
    check(best, "the opened site is the best one for the selection")
    no_overlap(page, ["chat", "char"], CONTROLS, "chat open + card open")

    a = chip(page, "Tell me about this site")
    check("scores" in a and "/100" in a and len(relay.bodies) == 0, "data answer about the selected site (context is wired)")

    # 2) FAQ answer: no AI call
    a = chip(page, "What is this project?")
    check("We scan the whole Earth" in a and len(relay.bodies) == 0, "FAQ answer without calling the AI")
    a = ask(page, "Where does the analogy break?")
    check("gravity" in a and len(relay.bodies) == 0, "FAQ answer (analogy breaks) without calling the AI")

    # 3) neither: the (mocked) AI, with the rich context
    a = ask(page, "How long is a day on Mars?")
    check("MOCKED AI ANSWER" in a and len(relay.bodies) == 1, "unknown question goes to the AI relay (mocked), once")
    body = relay.bodies[-1]
    c = body.get("context", {})
    print("  context sent:", json.dumps(c)[:600])
    site = c.get("site") or {}
    check(body.get("question") == "How long is a day on Mars?", "the question is sent as typed")
    check(c.get("target") == "jezero" and c.get("profile") == "rover", "context: target and profile")
    check(bool(site.get("region")) and site.get("lat") is not None and site.get("lon") is not None
          and isinstance(site.get("total"), (int, float)) and len(site.get("dims", {})) > 0,
          "context: selected site with region, coordinates, total and per-dimension scores")
    tops = c.get("top_sites", [])
    check(len(tops) == 5 and all("region" in t and isinstance(t.get("score"), (int, float)) for t in tops),
          "context: top 5 sites (region + score)")
    page.screenshot(path=f"{OUT}/6_ai_answer.png")

    # a change of target and profile reaches Orbi
    page.click("#target-select label:nth-of-type(2)")
    page.click("#profile-select label:nth-of-type(2)")
    ask(page, "Is there wind over there?")
    c = relay.bodies[-1]["context"]
    check(len(relay.bodies) == 2 and c["target"] == "lunar_south_pole" and c["profile"] == "geology",
          "context follows the target and profile selectors")
    check(len(c["top_sites"]) == 5, "context: top 5 sites for the new selection")

    # 4) quota reached: 429
    relay.status = 429
    a = ask(page, "What colour is the sky at noon over there?")
    check(a.startswith("Too many questions today, my antenna needs a break!"), "429 -> 'Too many questions today…'")
    check(page.evaluate("document.querySelector('#orbi-chat .orbi-chips').classList.contains('nudge')"), "429 -> the suggestion chips flash")
    page.screenshot(path=f"{OUT}/7_quota_429.png")
    n = len(relay.bodies)
    a = ask(page, "And how thick is the dust layer on the ground?")
    check(a.startswith("Too many questions today") and len(relay.bodies) == n, "after a 429 the relay is not called again")
    a = chip(page, "What's a hidden gem?")
    check("hidden gem" in a.lower() and len(relay.bodies) == n, "data answers still work after a 429")

    page.keyboard.press("Escape")
    page.wait_for_selector("#orbi-fab.show")
    check(True, "Escape closes the chat and brings the docked button back")
    check(errors == [], "no JavaScript error on the page " + str(errors[:3]))
    page.close()

    # ------------------------------------------------------------------ narrow desktop window
    print("NARROW WINDOW 800x600 (#map)")
    page = browser.new_page(viewport={"width": 800, "height": 600})
    relay = Relay(page)
    page.goto(URL + "#map")
    page.wait_for_selector("#legend .legend-title")
    page.wait_for_selector("#orbi-fab.show")
    page.click("#orbi-fab")
    page.wait_for_selector("#orbi-chat.show")
    page.wait_for_timeout(3500)
    page.screenshot(path=f"{OUT}/8_narrow_chat.png")
    no_overlap(page, ["chat"], CONTROLS, "narrow window")
    page.close()

    # ------------------------------------------------------------------ phone
    print("PHONE 390x844 (#map: intro skipped)")
    page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    relay = Relay(page)
    page.goto(URL + "#map")
    page.wait_for_selector("#legend .legend-title")
    page.wait_for_selector("#orbi-fab.show")
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/9_phone_docked.png")
    check(page.evaluate("!document.querySelector('#orbi-bubble').classList.contains('show')"), "#map: no greeting, only the docked button")
    no_overlap(page, ["fab"], CONTROLS, "phone docked")

    page.tap("#orbi-fab")
    page.wait_for_selector("#orbi-chat.show")
    page.wait_for_timeout(3500)
    page.screenshot(path=f"{OUT}/10_phone_sheet.png")
    r = page.evaluate(RECTS_JS)
    check(r["chat"][0] == 0 and round(r["chat"][2]) == 390 and round(r["chat"][3]) == 844, "phone: the chat is a bottom sheet (full width, stuck to the bottom)")

    a = ask(page, "How long is a day on Mars?")
    check("MOCKED AI ANSWER" in a and len(relay.bodies) == 1, "phone: unknown question goes to the mocked relay")
    a = chip(page, "Best site for Mars?")
    page.screenshot(path=f"{OUT}/11_phone_answer.png")
    page.tap("#orbi-chat .orbi-msg .act")
    page.wait_for_selector("#orbi-fab.show")
    page.wait_for_timeout(2600)
    page.screenshot(path=f"{OUT}/12_phone_show_on_map.png")
    check(page.evaluate("selectedSiteId !== null && !document.querySelector('#orbi-chat').classList.contains('show')"),
          "phone: 'Show it on the map' closes the sheet and opens the site card")
    no_overlap(page, ["fab"], CONTROLS, "phone, card open")
    check(errors == [], "phone: no JavaScript error " + str(errors[:3]))
    page.close()

    # ------------------------------------------------------------------ phone, greeting
    print("PHONE 390x844 (with the intro)")
    page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    Relay(page)
    page.goto(URL)
    page.wait_for_selector("#legend .legend-title")
    page.wait_for_timeout(1000)
    page.tap("#intro-explore")
    page.wait_for_selector("#orbi-bubble.show")
    page.wait_for_timeout(3200)
    page.screenshot(path=f"{OUT}/13_phone_greeting.png")
    no_overlap(page, ["char", "bubble"], CONTROLS, "phone greeting")
    page.close()

    browser.close()

print()
print("ALL CHECKS PASSED" if not failures else f"{len(failures)} CHECK(S) FAILED:\n  - " + "\n  - ".join(failures))
sys.exit(1 if failures else 0)

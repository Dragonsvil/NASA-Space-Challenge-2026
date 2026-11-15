"""Stress-test the site with realistic worst-case data, in a real browser.

data/results.json is NEVER modified: each test variant is built in memory from a copy of it,
and given to the page in place of the real file (the browser's request is intercepted).
The AI relay is ALWAYS mocked: the real endpoint is never called.

Run from the docs/ folder (the script starts its own local server on port 8766):
    python3 tools/stress_ui.py [folder for the screenshots] [only these variants…]
Needs: pip install playwright && playwright install chromium
"""
import copy
import functools
import http.server
import json
import os
import random
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # the docs/ folder
PORT = 8766
URL = f"http://127.0.0.1:{PORT}/index.html#map"                        # #map: skip the intro
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
ONLY = sys.argv[2:]
failures = []

with open(os.path.join(ROOT, "data", "results.json"), encoding="utf-8") as f:
    REAL = json.load(f)

LONG_TOWN = "Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch"    # a real town in Wales
LONG_REGION = "United Kingdom of Great Britain and Northern Ireland, near " + LONG_TOWN
LONG_ANALOG = "Haughton–Mars Project Research Station (Devon Island impact structure)"
LONG_NOTE = "excluded: vegetated tile (NDVI 0.78), nearest barren tile is 212 km away across the Strait of Gibraltar"
LONG_SOURCE = ("Mars 2020 MEDA (Rodriguez-Manfredi et al. 2021), "
               "https://doi.org/10.1007/s11214-021-00816-9/supplementary-material-table-4 — mean of sols 1–400")


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)


def ranked(data, target, profile):
    """Sites that have a total for target × profile, best first (same order as the site)."""
    def total(s):
        return (((s.get("scores") or {}).get(target) or {}).get(profile) or {}).get("total")
    return sorted([s for s in data["sites"] if total(s) is not None], key=total, reverse=True)


# ---------------------------------------------------------------- the variants

def worst():
    """One file that mixes many realistic worst cases, on the sites that are on screen first."""
    d = copy.deepcopy(REAL)
    d["meta"]["tiles_scored"]["jezero"] = 200000
    top = ranked(d, "jezero", "rover")[:14]
    for s in top:
        s["hidden_gem"] = {"jezero": False, "lunar_south_pole": False}
        s["known_analog"] = None

    # 1: very long region with a word that cannot break, gem AND known analog, perfect score
    a = top[0]
    a["region"] = LONG_REGION
    a["hidden_gem"] = {"jezero": True, "lunar_south_pole": True}
    a["known_analog"] = LONG_ANALOG
    a["cluster"] = 7
    for p in a["scores"]["jezero"].values():
        p["total"] = 100
    dims = a["scores"]["jezero"]["rover"]["dims"]
    keys = list(dims)
    dims[keys[0]], dims[keys[1]], dims[keys[2]] = 0, 100, 39.99999
    # every other known-analog tile is in the same cluster: a long "Same terrain family as…" sentence
    for s in d["sites"]:
        if s.get("known_analog") and s is not a:
            s["cluster"] = 7

    # 2: every value and every dimension score is null (the total exists)
    b = top[1]
    b["values"] = {k: None for k in b["values"]}
    for t in b["scores"].values():
        for p in t.values():
            p["dims"] = {k: None for k in p.get("dims", {})}
    b["hidden_gem"] = {"jezero": True}

    # 3: no "values" and no "dims" at all
    c = top[2]
    c["values"] = None
    for t in c["scores"].values():
        for p in t.values():
            p.pop("dims", None)

    # 4: total null for one profile only
    top[3]["scores"]["jezero"]["rover"]["total"] = None
    top[3]["region"] = "Chile, near San Pedro de Atacama"

    # 5-7: empty, blank and HTML-looking region names
    top[4]["region"] = ""
    top[5]["region"] = "   "
    top[6]["region"] = "<img src=x onerror=alert(1)> & Côte d'Ivoire"

    # 8: numbers the pipeline forgot to round
    e = top[7]
    e["scores"]["jezero"]["rover"]["total"] = 71.46666666666667
    for k in e["scores"]["jezero"]["rover"]["dims"]:
        e["scores"]["jezero"]["rover"]["dims"][k] = round(random.Random(k).uniform(5, 95), 9)
    e["values"]["albedo"] = 0.30000000000000004
    e["values"]["aridity"] = 12345.678
    e["values"]["temp_min"] = -89.19999999999999

    # 9: other scripts
    top[8]["region"] = "Saudi Arabia, near الربع الخالي (Rub' al Khali)"
    top[9]["region"] = "Việt Nam, near Đồng Hới"
    # 11: no coordinates
    top[10]["lat"] = None
    top[10]["lon"] = None
    # 12: one-letter region, score 0 on purpose is impossible in a top list: use a short name
    top[11]["region"] = "Chad"

    # target values: long citation, missing target value
    d["targets"]["jezero"]["sources"]["temp_range"] = LONG_SOURCE
    d["targets"]["jezero"]["values"]["albedo"] = None

    # known analogs: best rank, last rank, not scored with a long note, half-scored, missing texts
    ka = d["known_analogs"]
    ka[0]["scores"]["jezero"]["rover"] = {"total": 100, "global_rank": 1}
    ka[0]["name"] = LONG_ANALOG
    ka[0]["used_for"] = "astrobiology, drilling tests, EVA simulations, rover traverses, crew training, sample-return rehearsals"
    ka[1]["scores"]["jezero"]["rover"] = {"total": 3, "global_rank": 200000}
    ka[1]["tile_note"] = "nearest valid tile, 12 km away"
    ka[2]["scores"] = None
    ka[2]["tile_note"] = LONG_NOTE
    ka[3]["scores"]["jezero"]["rover"] = {"total": 55.55555, "global_rank": None}
    ka[4]["analog_for"] = None
    ka[4]["used_for"] = None
    ka[5]["analog_for"] = "Mars, Moon"
    ka[5]["lat"] = None
    ka[5]["lon"] = None
    return d


def three_dims():
    """The Moon target only uses 3 dimensions."""
    d = copy.deepcopy(REAL)
    keep = ["temp_min", "slope", "sun_angle"]
    d["targets"]["lunar_south_pole"]["dims"] = keep
    for s in d["sites"]:
        for p in ((s.get("scores") or {}).get("lunar_south_pole") or {}).values():
            p["dims"] = {k: v for k, v in (p.get("dims") or {}).items() if k in keep}
    return d


def one_dim():
    """One single dimension (a radar chart cannot draw a shape)."""
    d = three_dims()
    d["targets"]["lunar_south_pole"]["dims"] = ["sun_angle"]
    return d


LONG_REASON = ("the aerosol product has no valid retrieval over bright desert surfaces for 2019–2024, "
               "so the pipeline could not compare it with the Mars 2020 MEDA measurements")


def dropped_dims():
    """meta.dropped_dimensions: 'dust' and 'albedo' are not scored in this version of the file.
    The file still holds scores for them, and they would be named in "Works for…" (huge weight) and in
    "Where the analogy breaks" (low score on the best site) if the site did not ignore them."""
    d = copy.deepcopy(REAL)
    d["meta"]["dropped_dimensions"] = [
        {"id": "dust", "reason": "no data"},
        {"id": "albedo", "reason": LONG_REASON},     # a long reason
        {"id": "sun_angle"},                         # no reason, and not a dimension of Jezero
        {"id": "ghost", "reason": None},             # an id the file does not describe
    ]
    for p in d["meta"]["profiles"]:
        if p["id"] == "rover":
            p.setdefault("weights", {})["dust"] = 1000
    best = ranked(d, "jezero", "rover")[0]
    best["scores"]["jezero"]["rover"]["dims"]["albedo"] = 5
    return d


def dropped_most():
    """So many dropped dimensions that only 2 of Jezero's are still scored: no radar."""
    d = dropped_dims()
    keep = d["targets"]["jezero"]["dims"][:2]
    d["meta"]["dropped_dimensions"] = [{"id": x, "reason": "no data"} for x in d["targets"]["jezero"]["dims"] if x not in keep]
    return d


UNAVAILABLE_REASON = ("available weight 7 of 12 (< 67%): no target value or no data for "
                      "mafic, aridity, dust, sun_angle, roughness, albedo")


def unavailable_profiles():
    """meta.unavailable_profiles: 'rover' (the FIRST profile) cannot be scored for Jezero, and
    'geology' cannot be scored for the Moon. As in the real file, every total and rank is then null."""
    d = copy.deepcopy(REAL)
    pairs = [("jezero", "rover"), ("lunar_south_pole", "geology")]
    d["meta"]["unavailable_profiles"] = [
        {"target": "jezero", "profile": "rover", "reason": UNAVAILABLE_REASON},
        {"target": "lunar_south_pole", "profile": "geology"},      # no reason given
        {"target": "ghost", "profile": "polar", "reason": None},   # a target the file does not have
    ]
    for t, p in pairs:
        for s in d["sites"]:
            score = ((s.get("scores") or {}).get(t) or {}).get(p)
            if score:
                score["total"] = None
        for a in d["known_analogs"]:
            score = ((a.get("scores") or {}).get(t) or {}).get(p)
            if score:
                score["total"] = score["global_rank"] = None
    return d


def validated_profiles():
    """known_analogs[].validated_profiles: each analog counts only for the profiles it is used for.
    One analog has an empty list (used for none), and none is used for 'polar' on the Moon."""
    d = copy.deepcopy(REAL)
    lists = [["rover", "geology"], ["polar"], ["rover", "geology", "polar"], ["geology"], [], ["rover", "polar"],
             ["polar"], ["polar", "geology"], ["rover"], ["geology", "rover"]]
    for i, a in enumerate(d["known_analogs"]):
        a["validated_profiles"] = list(lists[i % len(lists)])
        if "Moon" in a.get("analog_for", ""):
            a["validated_profiles"] = [p for p in a["validated_profiles"] if p != "polar"]
    return d


def validated_mixed():
    """Same, but the pipeline gave no validated_profiles for two analogs (one null, one absent)."""
    d = validated_profiles()
    d["known_analogs"][0]["validated_profiles"] = None
    del d["known_analogs"][5]["validated_profiles"]
    return d


def expected_validation(d, target, profile):
    """The rule, computed here: what the Validation tab and Orbi must both say."""
    body = d["targets"][target]["body"]
    same = [a for a in d["known_analogs"] if body in [b.strip() for b in (a.get("analog_for") or "").split(",")]]
    missing = [a for a in same if not isinstance(a.get("validated_profiles"), list)]
    counted = [a for a in same if a in missing or profile in a["validated_profiles"]]
    ranks = [(((a.get("scores") or {}).get(target) or {}).get(profile) or {}).get("global_rank") for a in counted]
    scored = [r for r in ranks if r is not None]
    top = [r for r in scored if r / d["meta"]["tiles_scored"][target] * 100 <= 10]
    return {"body": body, "top": len(top), "scored": len(scored), "unscored": len(ranks) - len(scored),
            "off": len(same) - len(counted), "missing": len(missing), "same": len(same)}


def empty_profile():
    """No site and no analog has a score for the 'polar' profile."""
    d = copy.deepcopy(REAL)
    for s in d["sites"]:
        for t in (s.get("scores") or {}).values():
            if "polar" in t:
                t["polar"]["total"] = None
    for a in d["known_analogs"]:
        for t in (a.get("scores") or {}).values():
            t.pop("polar", None)
    return d


def no_gems():
    """Zero hidden gems, written in the different ways the pipeline could write it."""
    d = copy.deepcopy(REAL)
    for i, s in enumerate(d["sites"]):
        s["hidden_gem"] = [False, None, {}, {"jezero": False}][i % 4]
        s["cluster"] = None
    return d


def no_sites():
    """An empty file: no site, no known analog."""
    d = copy.deepcopy(REAL)
    d["sites"] = []
    d["known_analogs"] = []
    return d


def five_thousand():
    """5,000 sites, with hundreds of hidden gems (like the older files)."""
    d = copy.deepcopy(REAL)
    rnd = random.Random(1)
    base = d["sites"]
    sites = list(base)
    while len(sites) < 5000:
        s = copy.deepcopy(rnd.choice(base))
        s["id"] = "x_" + str(len(sites))
        s["lat"] = max(-85, min(85, s["lat"] + rnd.uniform(-6, 6)))
        s["lon"] = s["lon"] + rnd.uniform(-6, 6)
        s["known_analog"] = None
        s["hidden_gem"] = {"jezero": rnd.random() < 0.12, "lunar_south_pole": rnd.random() < 0.12}
        sites.append(s)
    d["sites"] = sites
    return d


def long_labels():
    """Longer target and profile names, a third target and a fourth profile."""
    d = copy.deepcopy(REAL)
    d["targets"]["lunar_south_pole"]["name"] = "Shackleton–de Gerlache connecting ridge"
    d["targets"]["arsia_mons"] = copy.deepcopy(d["targets"]["jezero"])
    d["targets"]["arsia_mons"]["name"] = "Arsia Mons lava-tube skylight"
    d["meta"]["tiles_scored"]["arsia_mons"] = 1
    d["meta"]["profiles"].append({"id": "isru", "label": "Sample return & in-situ resource use"})
    for s in d["sites"]:
        sc = s.get("scores") or {}
        if "jezero" in sc:
            sc["arsia_mons"] = copy.deepcopy(sc["jezero"])
        for t in sc.values():
            if "rover" in t:
                t["isru"] = copy.deepcopy(t["rover"])
    return d


VARIANTS = {
    "real": lambda: REAL, "worst": worst, "three_dims": three_dims, "one_dim": one_dim,
    "dropped_dims": dropped_dims, "dropped_most": dropped_most, "unavailable_profiles": unavailable_profiles,
    "validated_profiles": validated_profiles, "validated_mixed": validated_mixed,
    "empty_profile": empty_profile, "no_gems": no_gems, "no_sites": no_sites,
    "five_thousand": five_thousand, "long_labels": long_labels,
}

# A very long answer from the (mocked) AI: paragraphs, a list, a long link, markdown marks.
LONG_ANSWER = (
    "A day on Mars, called a sol, lasts 24 hours, 39 minutes and 35 seconds. " * 6 + "\n\n"
    "Here is what that means for a field test on Earth:\n"
    "• **Power**: solar panels see about the same day length as here.\n"
    "• **Thermal**: the night is long enough for the ground to cool by tens of degrees.\n"
    "• **Planning**: mission teams live on 'Mars time', drifting 40 minutes a day.\n\n"
    "Source: https://mars.nasa.gov/all-about-mars/facts/a-very-long-path/with_no_spaces_at_all/"
    "that_goes_on_and_on_and_on_and_on_and_on_and_on_and_on_and_on_and_on.html?utm_source=orbi&utm_medium=chat\n\n"
    + "The analogy is never perfect: gravity, air pressure and radiation are different on Earth. " * 12
)
# No word of Orbi's data answers or FAQ in it: it must go to the (mocked) AI.
LONG_QUESTION = ("Sooooo if my friends and I wanted to rehearse a 30-sol traverse with a six-wheeled prototype, a drill "
                 "and a ground-penetrating radar, in winter, on almost no budget, "
                 "whatkindofweatherandwindshouldweexpectovertheremostnightsandearlymornings, "
                 "and what should we absolutely not forget to pack before leaving?")[:300]

# ---------------------------------------------------------------- browser helpers

# Things that stick out of their box, or text cut without the user being able to read it.
OVERFLOW_JS = """() => {
  const out = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > window.innerWidth + 1) out.push('page scrolls sideways: ' + doc.scrollWidth + ' > ' + window.innerWidth);
  for (const boxSel of ['#panel-content', '#topbar', '#sheet-head', '#legend', '#orbi-chat', '#panel-tabs']) {
    const box = document.querySelector(boxSel);
    if (!box) continue;
    const b = box.getBoundingClientRect();
    if (!b.width) continue;
    if (box.scrollWidth > box.clientWidth + 1) out.push(boxSel + ' scrolls sideways: ' + box.scrollWidth + ' > ' + box.clientWidth);
    for (const el of box.querySelectorAll('*')) {
      if (el.closest('canvas, svg, .thumb, .orbi-typing') || el.tagName === 'INPUT') continue;
      // inside a strip that scrolls sideways on purpose (the selectors of the top bar on phones)
      const strip = el.closest('.control');
      if (strip && getComputedStyle(strip).overflowX === 'auto') continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (r.right > b.right + 1 || r.left < b.left - 1) {
        out.push(boxSel + ': <' + el.tagName.toLowerCase() + ' class="' + el.className + '"> sticks out by ' +
                 Math.round(Math.max(r.right - b.right, b.left - r.left)) + 'px: ' + (el.textContent || '').slice(0, 40));
      }
    }
  }
  return out.slice(0, 12);
}"""

# Texts that should never be shown to a visitor.
BAD_TEXT_JS = """() => {
  const text = document.body.innerText;
  const bad = ['undefined', 'NaN', 'object Object', 'null'].filter(w => new RegExp('(^|[^a-z])' + w + '([^a-z]|$)').test(text));
  const unrounded = text.match(/[0-9][.][0-9]{6,}/);            // 39.99999, 0.30000000000000004
  if (unrounded) bad.push('unrounded number ' + unrounded[0]);
  if (/Top 0%/.test(text)) bad.push('Top 0%');
  return bad;
}"""


class Session:
    """One browser page that receives a variant in place of data/results.json."""

    def __init__(self, browser, variant, width=1366, height=768, delay=0, **kw):
        self.name = f"{variant}_{width}"
        self.page = browser.new_page(viewport={"width": width, "height": height}, **kw)
        self.errors = []
        self.relay_calls = []
        self.relay_answer = "MOCKED AI ANSWER: this text comes from the test, not from a real model."
        body = json.dumps(VARIANTS[variant]()) if variant in VARIANTS else variant   # raw text = broken file
        page = self.page
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: self.errors.append(m.text)
                if m.type == "error" and "Failed to load resource" not in m.text else None)

        def data_route(route):
            if delay:      # slow network: our local server waits, then sends the real file
                route.continue_(url=f"http://127.0.0.1:{PORT}/data/results.json?slow={delay}")
            else:
                route.fulfill(status=200, content_type="application/json", body=body)

        def relay_route(route):
            self.relay_calls.append(route.request.post_data)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"answer": self.relay_answer}))

        page.route("**/data/results.json", data_route)
        page.route("**/*workers.dev/**", relay_route)
        page.route("**/*workers.dev", relay_route)

    def open(self, wait=True):
        self.page.goto(URL)
        if wait:
            for attempt in range(3):
                try:
                    self.page.wait_for_selector("#legend .legend-title", timeout=30000)
                    break
                except Exception:
                    # Leaflet or Chart.js did not download (they come from a CDN): a network hiccup, not a bug
                    # of the site. Load the page again, twice at most. Anything else is a real failure.
                    cdn_missing = self.page.evaluate("typeof L === 'undefined' || typeof Chart === 'undefined'")
                    if attempt == 2 or not cdn_missing:
                        raise
                    print("  (a CDN library did not load: network hiccup, loading the page again)")
                    self.errors.clear()
                    self.page.reload()
            self.page.wait_for_timeout(700)

    def shot(self, label):
        self.page.wait_for_timeout(700)      # let the fades and the radar animation finish
        self.page.screenshot(path=f"{OUT}/{self.name}_{label}.png")

    def look(self, label):
        """Screenshot + the automatic checks on what is on screen now."""
        self.shot(label)
        over = self.page.evaluate(OVERFLOW_JS)
        check(over == [], f"{self.name} / {label}: nothing sticks out of its box " + str(over[:4] if over else ""))
        bad = self.page.evaluate(BAD_TEXT_JS)
        check(bad == [], f"{self.name} / {label}: no raw 'undefined' / 'NaN' / 'null' on screen " + str(bad if bad else ""))

    def done(self):
        check(self.errors == [], f"{self.name}: no JavaScript error " + str(self.errors[:3] if self.errors else ""))
        self.page.close()

    # --- actions
    def tab(self, tab_id):
        # Phones: the tabs are in the bottom sheet (js/sheet.js). Closed sheet: open it first, as a user would.
        if self.page.evaluate("document.querySelector('#panel').dataset.sheet === 'peek'"):
            self.page.click("#sheet-grip")
            self.page.wait_for_timeout(400)
        self.page.click(f'#panel-tabs label:has(input[value="{tab_id}"])')

    def pick(self, control, value):
        self.page.click(f'#{control} label:has(input[value="{value}"])')

    def site(self, site_id):
        self.page.evaluate("id => openSite(id, false)", site_id)

    def open_orbi(self):
        self.page.click("#orbi-fab")
        self.page.wait_for_selector("#orbi-chat.show")
        self.wait_typing()

    def ask(self, text):
        self.page.fill("#orbi-chat input", text)
        self.page.press("#orbi-chat input", "Enter")
        self.page.wait_for_function("!document.querySelector('#orbi-chat .orbi-form button').disabled")
        return self.wait_typing()

    def wait_typing(self):
        """Wait until Orbi's last message stops growing. Returns (text, seconds it took)."""
        start, last = time.time(), -1
        while True:
            self.page.wait_for_timeout(400)
            text = self.page.evaluate("[...document.querySelectorAll('#orbi-chat .orbi-msg.bot .body')].pop().textContent")
            if len(text) == last:
                return text, time.time() - start - 0.4
            last = len(text)


def walk_tabs(s, site_ids, profiles=("rover",), targets=("jezero",)):
    """Open each site card, then the two other tabs, for each target × profile."""
    for t in targets:
        s.pick("target-select", t)
        for p in profiles:
            s.pick("profile-select", p)
            for i, sid in enumerate(site_ids):
                s.site(sid)
                s.look(f"{t}_{p}_site{i + 1}")
            s.tab("top")
            s.look(f"{t}_{p}_top")
            if s.page.query_selector(".filter-gems"):
                s.page.click(".filter-gems")
                s.look(f"{t}_{p}_gems")
                s.page.click('[data-filter="all"]')
            s.tab("validation")
            s.look(f"{t}_{p}_validation")


def run(name):
    return not ONLY or name in ONLY


# ---------------------------------------------------------------- the tests

def main(browser):
    if run("worst"):
        print("WORST CASE (long names, null values, unrounded numbers…)")
        ids = [x["id"] for x in ranked(worst(), "jezero", "rover")[:12]]
        null_total = [x["id"] for x in worst()["sites"] if x.get("region") == "Chile, near San Pedro de Atacama"
                      and x["scores"]["jezero"]["rover"]["total"] is None][:1]
        for width, height, kw in [(1366, 768, {}), (800, 600, {}), (390, 844, {"has_touch": True, "is_mobile": True}),
                                  (320, 568, {"has_touch": True, "is_mobile": True}), (2560, 1300, {})]:
            s = Session(browser, "worst", width, height, **kw)
            s.open()
            s.look("map")
            walk_tabs(s, (ids + null_total) if width == 1366 else ids[:3] + null_total)
            # hover label of the long-named site
            s.pick("target-select", "lunar_south_pole")
            s.tab("validation")
            s.look("moon_validation")
            s.done()

    if run("three_dims"):
        print("A TARGET WITH 3 DIMENSIONS, THEN 1")
        for variant in ["three_dims", "one_dim"]:
            s = Session(browser, variant)
            s.open()
            s.pick("target-select", "lunar_south_pole")
            s.site(ranked(VARIANTS[variant](), "lunar_south_pole", "rover")[0]["id"])
            s.look("card")
            check((s.page.query_selector("#radar") is not None) == (variant == "three_dims"),
                  f"{variant}: radar chart with 3 dimensions, no radar with 1")
            s.done()

    if run("dropped_dims"):
        print("DROPPED DIMENSIONS (meta.dropped_dimensions)")
        best = ranked(REAL, "jezero", "rover")[0]["id"]
        scored = len(REAL["targets"]["jezero"]["dims"]) - 2      # dust and albedo are dropped
        for width, height, kw in [(1366, 768, {}), (390, 844, {"has_touch": True, "is_mobile": True})]:
            s = Session(browser, "dropped_dims", width, height, **kw)
            s.open()
            s.site(best)
            s.look("card")
            card = s.page.inner_text("#panel-content")
            check(s.page.evaluate("radarChart ? radarChart.data.labels.length : 0") == scored,
                  f"{s.name}: the radar has one axis per scored dimension ({scored}), none for a dropped one")
            check(s.page.locator(".dim-dropped").count() == 2 and s.page.locator(".dim .bar-fill").count() == scored,
                  f"{s.name}: the 2 dropped dimensions are listed as 'no data' with their reason, without a bar")
            check("Not scored in this version: no data" in card and LONG_REASON in card,
                  f"{s.name}: the reasons are shown in the dimension list")
            check("dust" not in s.page.inner_text(".works").lower(),
                  f"{s.name}: 'Works for…' does not name a dropped dimension (even with a huge weight)")
            check("albedo" not in s.page.inner_text(".breaks").lower(),
                  f"{s.name}: 'Where the analogy breaks' does not list a dropped dimension (even with a low score)")
            line = s.page.inner_text(".sources-dropped")
            check(line.startswith("Not scored in this version: ") and "dust (no data)" in line and "albedo (" in line
                  and "sun angle" not in line and "ghost" not in line,
                  f"{s.name}: the Sources section names the dropped dimensions of this target only")
            s.open_orbi()
            text, _ = s.ask("Tell me about this site")
            check("/100" in text and "dust" not in text.lower() and "albedo" not in text.lower(),
                  f"{s.name}: Orbi's data answer does not use a dropped dimension")
            s.ask("How would a dust storm change a rover traverse planned for this exact place?")
            context = json.loads(s.relay_calls[-1])["context"] if s.relay_calls else {}
            gone = [x.get("id") for x in context.get("dropped_dimensions", [])]
            dims = (context.get("site") or {}).get("dims", {})
            check(gone == ["dust", "albedo", "sun_angle", "ghost"] and context["dropped_dimensions"][0].get("reason") == "no data",
                  f"{s.name}: the AI context lists the dropped dimensions with their reason")
            check(len(dims) == scored and "dust" not in dims and "albedo" not in dims
                  and "dust" not in context.get("dim_labels", {}),
                  f"{s.name}: the AI context has no score for a dropped dimension")
            s.look("orbi")
            s.done()
        s = Session(browser, "dropped_most")
        s.open()
        s.site(best)
        s.look("card")
        check(s.page.query_selector("#radar") is None, "dropped_most: no radar with only 2 scored dimensions")
        s.done()

    if run("unavailable_profiles"):
        print("UNAVAILABLE PROFILES (meta.unavailable_profiles)")
        state = """() => { const o = {};
            for (const i of document.querySelectorAll('#profile-select input'))
                o[i.value] = { off: i.disabled, on: i.checked, tip: i.parentElement.title };
            o.current = currentProfile; o.sites = getRanking().length;
            const thumb = document.querySelector('#profile-select .thumb').getBoundingClientRect();
            const label = document.querySelector('#profile-select input:checked').parentElement.getBoundingClientRect();
            o.thumbOnChecked = Math.abs(thumb.left - label.left) < 2 && Math.abs(thumb.width - label.width) < 2;
            return o; }"""
        for width, height, kw in [(1366, 768, {}), (390, 844, {"has_touch": True, "is_mobile": True})]:
            s = Session(browser, "unavailable_profiles", width, height, **kw)
            s.open()
            o = s.page.evaluate(state)
            check(o["current"] == "geology" and o["geology"]["on"] and o["sites"] > 0,
                  f"{s.name}: the unavailable first profile is not the default (the next one is selected, with sites)")
            check(o["rover"]["off"] and not o["geology"]["off"] and not o["polar"]["off"],
                  f"{s.name}: only the unavailable profile is disabled")
            check(o["rover"]["tip"] == "Not available for Jezero Crater: " + UNAVAILABLE_REASON and o["geology"]["tip"] == "",
                  f"{s.name}: the reason is the tooltip of the disabled option")
            s.page.click('#profile-select label:has(input[value="rover"])', force=True)
            s.page.wait_for_timeout(300)
            check(s.page.evaluate("currentProfile") == "geology", f"{s.name}: a click on the disabled option changes nothing")
            s.look("jezero")
            # Moon: the selected profile (geology) is the unavailable one there
            s.pick("target-select", "lunar_south_pole")
            s.page.wait_for_timeout(500)
            o = s.page.evaluate(state)
            check(o["current"] == "rover" and o["rover"]["on"] and not o["rover"]["off"] and o["sites"] > 0,
                  f"{s.name}: switching target moves the selection off a profile that is unavailable there")
            check(o["geology"]["off"] and o["geology"]["tip"] == "Not available for Lunar south pole" and o["rover"]["tip"] == "",
                  f"{s.name}: disabled options follow the target (no reason given: short tooltip)")
            check(o["thumbOnChecked"], f"{s.name}: the red thumb sits behind the selected profile")
            s.site(ranked(unavailable_profiles(), "lunar_south_pole", "rover")[0]["id"])
            s.look("moon_card")
            s.tab("validation")
            s.look("moon_validation")
            s.done()

    if run("validated_profiles"):
        print("VALIDATION RULE (known_analogs[].validated_profiles)")
        words = {"rover": "rover navigation", "geology": "geology and science work", "polar": "polar and thermal operations"}
        for variant, width, height, kw in [("validated_profiles", 1366, 768, {}), ("validated_mixed", 1366, 768, {}),
                                           ("real", 1366, 768, {}),      # the real file: no validated_profiles at all
                                           ("validated_profiles", 390, 844, {"has_touch": True, "is_mobile": True})]:
            d = VARIANTS[variant]()
            s = Session(browser, variant, width, height, **kw)
            s.name = f"{variant}_{width}"
            s.open()
            s.tab("validation")
            s.open_orbi() if width == 1366 else None
            for t in ["jezero", "lunar_south_pole"]:
                s.pick("target-select", t)
                for p in ["rover", "geology", "polar"]:
                    s.pick("profile-select", p)
                    s.page.wait_for_timeout(300)
                    e = expected_validation(d, t, p)
                    summary = s.page.inner_text(".validation-summary")
                    tab = s.page.inner_text("#panel-content")
                    if e["scored"] > 0:
                        want = (f"{e['top']} of {e['scored']} {'scored' if e['unscored'] else 'known'} {e['body']} analogs"
                                + (f" used for {words[p]}" if e["missing"] == 0 else "") + " rank in the top 10% of Earth’s barren land")
                        check(summary.startswith(want), f"{s.name} {t} × {p}: summary '{want[:60]}…' (got '{summary[:70]}')")
                    else:
                        check(summary.startswith(f"No known {e['body']} analog is used for {words[p]}"),
                              f"{s.name} {t} × {p}: no analog for this profile -> a calm sentence, not '0 of 0' (got '{summary[:70]}')")
                    check(("Matching profiles not provided" in tab) == (e["missing"] > 0 and e["scored"] > 0),
                          f"{s.name} {t} × {p}: 'matching profiles not provided' only when the field is missing")
                    off = s.page.evaluate("""() => { const rows = [...document.querySelectorAll('.validation tr.off-profile')];
                        return { n: rows.length, noted: rows.filter(r => r.textContent.includes('Not used for this profile')).length,
                                 lit: rows.filter(r => r.classList.contains('top') || r.querySelector('.badge-top')).length,
                                 all: document.querySelectorAll('.validation tbody tr').length }; }""")
                    check(off["n"] == e["off"] and off["noted"] == e["off"] and off["lit"] == 0 and off["all"] == len(d["known_analogs"]),
                          f"{s.name} {t} × {p}: {e['off']} analogs greyed with 'Not used for this profile', none highlighted, all {len(d['known_analogs'])} listed")
                    if width == 1366:
                        text, _ = s.ask("Is the method validated?")
                        if e["scored"] > 0:
                            ok = (f"{e['top']} of {e['scored']} known {e['body']} analogs" in text
                                  and (" used for " in text) == (e["missing"] == 0))
                        else:
                            ok = f"No known {e['body']} analog is used for" in text
                        check(ok, f"{s.name} {t} × {p}: Orbi gives the same count as the tab (got '{text[:90]}')")
                    if (t, p) in [("jezero", "rover"), ("lunar_south_pole", "polar")]:
                        s.look(f"{t}_{p}")
            check(len(s.relay_calls) == 0, f"{s.name}: Orbi answered from the data, without the AI relay")
            s.done()

    if run("empty_profile"):
        print("0 SITES FOR A PROFILE")
        for width, kw in [(1366, {}), (390, {"has_touch": True, "is_mobile": True})]:
            s = Session(browser, "empty_profile", width, 844 if width == 390 else 768, **kw)
            s.open()
            s.site(ranked(REAL, "jezero", "rover")[0]["id"])
            s.pick("profile-select", "polar")
            s.look("card")
            check(s.page.evaluate("markerLayer.getLayers().filter(l => l instanceof L.CircleMarker).length") == 0,
                  f"{s.name}: no site circle is drawn")
            s.tab("top")
            s.look("top")
            s.tab("validation")
            s.look("validation")
            s.open_orbi()
            text, _ = s.ask("Best site for polar ops?")
            check("don't have scored sites" in text, f"{s.name}: Orbi says there is no scored site")
            s.ask("What's a hidden gem?")
            s.look("orbi")
            s.done()

    if run("no_gems"):
        print("0 HIDDEN GEMS / EMPTY FILE")
        s = Session(browser, "no_gems")
        s.open()
        check(s.page.query_selector("#legend .gem-dot") is None, "no_gems: no gem key in the legend")
        s.site(ranked(REAL, "jezero", "rover")[0]["id"])
        s.look("card")
        s.tab("top")
        check(s.page.query_selector(".filter") is None, "no_gems: no 'Hidden gems' choice in Top sites")
        s.look("top")
        s.done()
        s = Session(browser, "no_sites")
        s.open()
        s.look("card")
        s.tab("top")
        s.look("top")
        s.tab("validation")
        s.look("validation")
        s.open_orbi()
        s.ask("Best site for Mars?")
        s.ask("How many sites?")
        s.look("orbi")
        s.done()

    if run("five_thousand"):
        print("5,000 SITES")
        s = Session(browser, "five_thousand")
        start = time.time()
        s.open()
        print(f"  page ready in {time.time() - start:.1f} s")
        timing = s.page.evaluate("""() => { const t = {};
            let a = performance.now(); renderMap(); t.renderMap = performance.now() - a;
            a = performance.now(); renderPanel(); t.renderPanel = performance.now() - a;
            a = performance.now(); renderLegend(); t.renderLegend = performance.now() - a;
            currentTab = 'top'; a = performance.now(); renderPanel(); t.top = performance.now() - a;
            a = performance.now(); openSite(data.sites[4999].id, false); t.openSite = performance.now() - a;
            return t; }""")
        print("  timings (ms):", {k: round(v) for k, v in timing.items()})
        check(timing["renderMap"] < 1500, "five_thousand: the map redraws in under 1.5 s")
        check(timing["openSite"] < 200, "five_thousand: opening a site card takes under 0.2 s")
        s.look("card")
        s.tab("top")
        s.page.click(".filter-gems")
        s.look("gems")
        s.pick("target-select", "lunar_south_pole")
        s.pick("profile-select", "polar")
        s.look("moon")
        s.done()

    if run("long_labels"):
        print("LONG TARGET AND PROFILE NAMES, 3 TARGETS, 4 PROFILES")
        for width, height, kw in [(1366, 768, {}), (1000, 700, {}), (390, 844, {"has_touch": True, "is_mobile": True})]:
            s = Session(browser, "long_labels", width, height, **kw)
            s.open()
            s.pick("target-select", "arsia_mons")
            s.pick("profile-select", "isru")
            s.site(ranked(REAL, "jezero", "rover")[0]["id"])
            s.look("card")
            s.tab("validation")
            s.look("validation")
            s.open_orbi()
            s.ask("Best site?")
            s.look("orbi")
            s.done()

    if run("slow"):
        print("SLOW NETWORK (the file takes 4 s), THEN A BROKEN FILE")
        for width, kw in [(1366, {}), (390, {"has_touch": True, "is_mobile": True})]:
            s = Session(browser, "real", width, 844 if width == 390 else 768, delay=4, **kw)
            s.name = f"slow_{width}"
            s.open(wait=False)
            s.page.wait_for_selector("#loading")
            # use the page while it loads: tabs, Orbi
            s.tab("top")
            s.tab("validation")
            s.look("loading")
            check(not s.page.is_visible("#target-select") and not s.page.is_visible("#profile-select"),
                  f"{s.name}: no empty selector in the top bar while loading")
            check(s.page.is_visible("#loading"), f"{s.name}: 'Loading the sites…' is visible on the map")
            s.open_orbi()
            text, _ = s.ask("Best site for Mars?")
            s.look("loading_orbi")
            s.page.wait_for_selector("#legend .legend-title", timeout=30000)
            check(s.page.query_selector("#loading") is None, f"{s.name}: the loading message is removed")
            check(s.page.evaluate("currentTab") == "validation" and s.page.query_selector("table.validation") is not None,
                  f"{s.name}: the tab picked while loading is the one shown after")
            s.look("loaded")
            s.done()
        for label, body in [("not_json", "<html>502 Bad Gateway</html>"), ("wrong_shape", '{"error": "pipeline failed"}')]:
            s = Session(browser, body)
            s.name = label
            s.open(wait=False)
            s.page.wait_for_timeout(1500)
            s.shot("error")
            check(s.page.query_selector("#loading") is None, f"{label}: the loading message is removed")
            check("Could not load" in s.page.inner_text("#panel-content"), f"{label}: the panel says the data could not be loaded")
            s.tab("top")
            s.tab("site")
            s.errors = [e for e in s.errors if "Could not load" not in e]      # the one console.error the site writes on purpose
            s.done()

    if run("fast"):
        print("CLICKING FAST BETWEEN SITES, TABS, TARGETS AND PROFILES")
        s = Session(browser, "worst")
        s.open()
        ids = [x["id"] for x in ranked(worst(), "jezero", "rover")[:40]]
        rnd = random.Random(3)
        for i in range(150):
            action = rnd.choice(["site", "site", "site", "fly", "tab", "target", "profile", "filter"])
            if action == "site":
                s.site(rnd.choice(ids))
            elif action == "fly":
                s.page.evaluate("id => openSite(id, true)", rnd.choice(ids))
            elif action == "tab":
                s.tab(rnd.choice(["site", "top", "validation"]))
            elif action == "target":
                s.pick("target-select", rnd.choice(["jezero", "lunar_south_pole"]))
            elif action == "profile":
                s.pick("profile-select", rnd.choice(["rover", "geology", "polar"]))
            elif s.page.query_selector("[data-filter]"):
                s.page.click(f'[data-filter="{rnd.choice(["all", "gems"])}"]')
            s.page.wait_for_timeout(rnd.choice([0, 0, 15, 40]))
        # real mouse clicks on the list rows, as fast as possible
        s.pick("target-select", "jezero")
        s.pick("profile-select", "rover")
        for i in range(12):
            s.tab("top")
            s.page.click(f".rank-list li:nth-child({i % 10 + 1}) .rank-row")
        s.page.wait_for_timeout(2500)
        state = s.page.evaluate("""() => ({ tab: currentTab, checked: document.querySelector('#panel-tabs input:checked').value,
            selected: selectedSiteId, title: (document.querySelector('#panel-content h2') || {}).textContent,
            expected: siteName(data.sites.find(x => x.id === selectedSiteId)),
            cards: document.querySelectorAll('#panel-content .card').length,
            canvases: document.querySelectorAll('#panel-content canvas').length,
            rings: ringLayer.getLayers().length,
            charts: Object.keys(Chart.instances).length })""")
        print("  final state:", state)
        check(state["tab"] == state["checked"] == "site", "fast: the tab shown is the tab selected")
        check(state["title"] == state["expected"], "fast: the card shows the selected site")
        check(state["cards"] == 1 and state["canvases"] <= 1 and state["charts"] <= 1 and state["rings"] in (0, 2),
              "fast: one card, one radar chart, one ring (nothing left behind)")
        s.look("end")
        s.done()

    if run("orbi"):
        print("ORBI: VERY LONG QUESTION, VERY LONG ANSWER (mocked relay)")
        for width, height, kw in [(1366, 768, {}), (800, 600, {}), (390, 844, {"has_touch": True, "is_mobile": True}),
                                  (320, 568, {"has_touch": True, "is_mobile": True})]:
            s = Session(browser, "worst", width, height, **kw)
            s.name = f"orbi_{width}"
            s.relay_answer = LONG_ANSWER
            s.open()
            s.site(ranked(worst(), "jezero", "rover")[0]["id"])
            s.open_orbi()
            # the box accepts 300 characters: try to give it more
            s.page.fill("#orbi-chat input", LONG_QUESTION + " and more and more and more")
            sent = s.page.input_value("#orbi-chat input")
            check(s.page.inner_text("#orbi-chat .orbi-count") == "300 / 300", f"{s.name}: the counter shows 300 / 300")
            s.look("counter")
            s.page.press("#orbi-chat input", "Enter")
            s.page.wait_for_function("!document.querySelector('#orbi-chat .orbi-form button').disabled")
            # while the long answer is typed: can the user scroll back up to read its start?
            s.page.wait_for_timeout(1500)
            box = s.page.locator(".orbi-log").bounding_box()
            s.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            s.page.mouse.wheel(0, -5000)
            s.page.wait_for_timeout(900)
            stayed = s.page.evaluate("document.querySelector('.orbi-log').scrollTop") < 40
            typing = s.page.evaluate("[...document.querySelectorAll('.orbi-msg.bot .body')].pop().textContent.length") < len(LONG_ANSWER.strip())
            check(stayed or not typing, f"{s.name}: the user can scroll up while Orbi is still typing")
            text, seconds = s.wait_typing()
            print(f"  question sent: {len(sent)} characters; answer: {len(text)} characters typed in {seconds + 2.1:.0f} s")
            check(len(s.relay_calls) == 1, f"{s.name}: the long question went to the mocked relay, once")
            check(text == LONG_ANSWER.strip(), f"{s.name}: the whole long answer is shown")
            check(seconds + 2.1 < 12, f"{s.name}: a long answer is fully typed in under 12 s")
            check(not s.page.is_visible("#orbi-chat .orbi-chips") and s.page.is_visible("#orbi-chat .orbi-suggest")
                  and not s.page.is_visible("#orbi-chat .orbi-count"),
                  f"{s.name}: chips hidden after the first question, 'Suggestions' button shown, counter gone")
            s.look("long_answer_end")
            s.page.evaluate("document.querySelector('.orbi-log').scrollTop = 0")
            s.look("long_answer_start")
            # data answers with the long names
            s.ask("Tell me about this site")
            s.look("this_site")
            s.ask("Best site for Mars?")
            s.look("best")
            s.ask("What's a hidden gem?")
            s.look("gems")
            check(s.page.evaluate("""() => { const c = document.querySelector('#orbi-chat').getBoundingClientRect();
                const f = document.querySelector('.orbi-form').getBoundingClientRect();
                const h = document.querySelector('.orbi-head').getBoundingClientRect();
                return f.height > 30 && h.height > 30 && f.bottom <= c.bottom + 1 && h.top >= c.top - 1 && c.top >= 0; }"""),
                  f"{s.name}: the chat header and the question box stay visible")
            s.done()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if "?slow=" in self.path:                      # used by the slow-network test
            time.sleep(float(self.path.split("?slow=")[1]))
        super().do_GET()


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(QuietHandler, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        main(browser)
        browser.close()
    server.shutdown()
    print()
    print("ALL CHECKS PASSED" if not failures else f"{len(failures)} CHECK(S) FAILED:\n  - " + "\n  - ".join(failures))
    sys.exit(1 if failures else 0)

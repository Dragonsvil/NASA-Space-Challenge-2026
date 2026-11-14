// Planetary Analog Finder — the side panel as a bottom sheet (phones only)
//
// On screens 700px wide or less, the side panel (#panel) slides up from the bottom of the screen.
// It has three positions, written in data-sheet on #panel (the CSS does the rest, see "Phones"
// in css/style.css):
//   "peek": only the top part shows: the grip and the two selectors (target, mission profile)
//   "half": about half the screen: the tabs and a site card or a list; the map shows above
//   "full": up to the top bar
// The user drags the top part up or down, or taps the grip. The sheet also opens by itself
// when a site is selected, and closes when Orbi's chat opens (two sheets must not fight).
//
// This file is loaded BEFORE js/app.js and js/panel.js: it only uses their functions
// (moveThumb, hasCoords, map) later, when the user does something.

const phoneLayout = window.matchMedia("(max-width: 700px)");   // same limit as the CSS
const SHEET_HALF = 0.56;      // "half" = 56% of the screen height (same as --sheet-half in the CSS)

const sheet = document.getElementById("panel");
const sheetHead = document.getElementById("sheet-head");
const sheetGrip = document.getElementById("sheet-grip");

// ---- Position ----

// Put the sheet in one of its three positions.
function setSheet(position) {
  if (!phoneLayout.matches) return;      // larger screens: the panel is a normal side panel
  sheet.dataset.sheet = position;
  // Closed sheet: the tabs and the content are below the screen. `inert` keeps the keyboard
  // and screen readers out of them.
  const closed = position === "peek";
  document.getElementById("panel-tabs").inert = closed;
  document.getElementById("panel-content").inert = closed;
  sheetGrip.setAttribute("aria-expanded", String(!closed));
}

// How many pixels of the sheet are on screen in a position (default: where it is now).
// Used here for the drag, and by js/app.js to know which part of the map is hidden.
function sheetCover(position) {
  if (!phoneLayout.matches) return 0;
  position = position || sheet.dataset.sheet;
  if (position === "full") return sheet.offsetHeight;
  if (position === "half") return Math.round(window.innerHeight * SHEET_HALF);
  // peek: the top part, plus the area of the iPhone home bar under it
  return sheetHead.offsetHeight + safeBottom();
}

// Height of the phone's home bar area (0 on most phones), read from the CSS (--safe-bottom).
function safeBottom() {
  const probe = document.createElement("div");
  probe.style.cssText = "position:fixed;height:var(--safe-bottom,0px);visibility:hidden";
  document.body.appendChild(probe);
  const height = probe.offsetHeight;
  probe.remove();
  return height;
}

// Called by openSite() (js/panel.js) each time a site is selected.
//   fly = true : the map is about to fly to the site (it will land above the sheet, see visibleOffset in app.js)
//   fly = false: the user tapped the site on the map. The map does not move, unless the sheet
//                is about to cover that site: then the map slides up just enough.
function openSheetForSite(site, fly) {
  if (!phoneLayout.matches) return;
  setSheet("half");
  if (fly || !hasCoords(site)) return;
  const point = map.latLngToContainerPoint([site.lat, site.lon]);
  const top = document.getElementById("topbar").offsetHeight;
  const bottom = map.getSize().y - sheetCover("half");      // first pixel hidden by the sheet
  if (point.y > bottom - 40) map.panBy([0, point.y - (top + bottom) / 2]);
}

// ---- The two selectors live in the sheet on phones, in the top bar otherwise ----

const selectorBoxes = Array.from(document.querySelectorAll("#topbar .control"));

function placeSelectors() {
  const home = phoneLayout.matches ? sheetHead : document.getElementById("topbar");
  selectorBoxes.forEach(function (box) { home.appendChild(box); });

  if (phoneLayout.matches) {
    setSheet(sheet.dataset.sheet || "peek");
  } else {                               // back to a normal side panel
    delete sheet.dataset.sheet;
    document.getElementById("panel-tabs").inert = false;
    document.getElementById("panel-content").inert = false;
  }

  // The options changed width: put every red thumb back behind its selected option
  document.querySelectorAll(".segmented").forEach(function (control) {
    if (control.querySelector("input:checked")) moveThumb(control);
  });
}
placeSelectors();
phoneLayout.addEventListener("change", placeSelectors);      // window resized, phone rotated

// Tell the CSS how tall the top part is: the legend, Orbi and the map credits sit just above it.
new ResizeObserver(function () {
  document.body.style.setProperty("--sheet-peek", sheetHead.offsetHeight + "px");
}).observe(sheetHead);

// ---- Dragging the top part ----

let drag = null;              // the drag in progress: where it started, how fast the finger moves
let justDragged = false;      // true for a moment after a drag (its "click" must be ignored)

// Where the sheet is now: how far it is pushed down, in pixels (0 = fully open).
function sheetY() {
  return new DOMMatrix(getComputedStyle(sheet).transform).m42;
}

sheetHead.addEventListener("pointerdown", function (event) {
  if (!phoneLayout.matches) return;
  drag = { startPointer: event.clientY, startSheet: sheetY(), moved: false,
           onGrip: event.target === sheetGrip,
           lowest: sheet.offsetHeight - sheetCover("peek"),      // the sheet cannot go below "peek"
           lastPointer: event.clientY, lastTime: event.timeStamp, speed: 0 };
});

sheetHead.addEventListener("pointermove", function (event) {
  if (!drag) return;
  const distance = event.clientY - drag.startPointer;
  if (!drag.moved) {
    if (Math.abs(distance) < 6) return;          // a tap that trembles is not a drag
    drag.moved = true;
    sheetHead.setPointerCapture(event.pointerId);   // keep receiving the moves, even outside the top part
    sheet.classList.add("dragging");                // CSS: no animation, follow the finger
  }
  // Speed of the finger in pixels per millisecond (positive = going down)
  const elapsed = event.timeStamp - drag.lastTime;
  if (elapsed > 0) drag.speed = (event.clientY - drag.lastPointer) / elapsed;
  drag.lastPointer = event.clientY;
  drag.lastTime = event.timeStamp;

  const y = Math.max(0, Math.min(drag.lowest, drag.startSheet + distance));
  sheet.style.transform = "translateY(" + y + "px)";
});

function endDrag() {
  if (!drag) return;
  const wasMoved = drag.moved;
  const wasOnGrip = drag.onGrip;
  const speed = drag.speed;
  drag = null;
  if (!wasMoved) {                                // it was a tap, not a drag
    if (wasOnGrip) toggleSheet();                 // on the grip: open halfway, or close
    return;                                       // on a selector: its own listener picks the option
  }

  // Where the sheet would stop if it kept sliding a little: a quick flick goes further than a slow drag.
  const landing = sheetY() + speed * 180;
  // Go to the closest of the three positions.
  let best = "peek";
  for (const position of ["half", "full"]) {
    const y = sheet.offsetHeight - sheetCover(position);
    const bestY = sheet.offsetHeight - sheetCover(best);
    if (Math.abs(landing - y) < Math.abs(landing - bestY)) best = position;
  }
  sheet.classList.remove("dragging");
  sheet.style.transform = "";                     // the CSS animates from here to the chosen position
  setSheet(best);

  justDragged = true;
  setTimeout(function () { justDragged = false; }, 60);
}
sheetHead.addEventListener("pointerup", endDrag);
sheetHead.addEventListener("pointercancel", endDrag);

// A drag that started on a selector must not also select that option when the finger lifts.
// (`true` = this listener runs before the selector's own.)
sheetHead.addEventListener("click", function (event) {
  if (!justDragged) return;
  event.preventDefault();
  event.stopPropagation();
}, true);

// The grip opens the sheet halfway, or closes it.
function toggleSheet() {
  setSheet(sheet.dataset.sheet === "peek" ? "half" : "peek");
}
// A tap on the grip is handled in endDrag() above (as soon as the finger lifts). This listener is
// for the keyboard only: Enter or Space on the grip gives a "click" with detail 0 (no real press).
sheetGrip.addEventListener("click", function (event) {
  if (event.detail === 0) toggleSheet();
});

// Orbi's chat is a bottom sheet too: when it opens, ours steps aside.
document.getElementById("orbi-fab").addEventListener("click", function () {
  setSheet("peek");
});

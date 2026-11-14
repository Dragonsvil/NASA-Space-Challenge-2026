// Planetary Analog Finder — main script
// Loads the results file, fills the selectors and draws the sites on the map.

// ---------------------------------------------------------------------------
// DATA SWITCH: change this ONE line when the real file arrives.
//   true  -> data/results.mock.json (fake data, for development)
//   false -> data/results.json      (real data from the pipeline)
// ---------------------------------------------------------------------------
const USE_MOCK_DATA = true;

const DATA_URL = USE_MOCK_DATA ? "data/results.mock.json" : "data/results.json";

// Score colors: from NASA blue (low score) to white (high score).
// Scores at or below RAMP_START are all pure NASA blue.
// The colors themselves live in css/style.css (--nasa-blue, --white).
const RAMP_START = 30;

// ---- State: what the user has selected, and the loaded data ----
let data = null;            // content of the results file
let currentTarget = null;   // e.g. "jezero"
let currentProfile = null;  // e.g. "rover"
let selectedSiteId = null;  // id of the site open in the side panel (null = none)

// ---- Map setup ----
const map = L.map("map", { worldCopyJump: true, minZoom: 2, maxZoom: 14 }).setView([20, 10], 2);

// On normal and wide screens the map also lies UNDER the top bar and the side panel
// (they are see-through glass, see css/style.css). Two small things keep that invisible:
const topbar = document.getElementById("topbar");
const glassLayout = window.matchMedia("(min-width: 701px)");

// 1) Tell the CSS how tall the top bar is, so the map controls sit just below it.
function syncTopbarHeight() {
  document.body.style.setProperty("--topbar-h", topbar.offsetHeight + "px");
}
syncTopbarHeight();
window.addEventListener("resize", syncTopbarHeight);

// 2) The visible part of the map is smaller than the map itself: the side panel hides
//    its right edge and the top bar hides its top edge. This returns how far (in pixels)
//    the map center must be moved so that a point lands in the middle of the VISIBLE part.
function visibleOffset() {
  if (!glassLayout.matches) return [0, 0];   // small screens: nothing covers the map
  const panelWidth = document.getElementById("panel").offsetWidth;
  return [panelWidth / 2, -topbar.offsetHeight / 2];
}

// Shift the start view, so the world is centered in the visible part of the map.
map.panBy(visibleOffset(), { animate: false });

// Zoom level used when flying to a site (a 0.25° tile is easy to see at this zoom).
const FLY_ZOOM = 6;

// Fly the map to a place, so it lands in the center of the visible map area
// (not behind the side panel). Uses the same offset as the start view.
function flyToVisibleCenter(lat, lon) {
  const zoom = Math.max(map.getZoom(), FLY_ZOOM);       // never zoom out
  // Work in pixels at the final zoom: the place, then the shifted map center.
  const placePoint = map.project([lat, lon], zoom);
  const center = map.unproject(placePoint.add(visibleOffset()), zoom);
  // People who asked their system for less motion get a direct jump.
  const lessMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (lessMotion) map.setView(center, zoom, { animate: false });
  else map.flyTo(center, zoom, { duration: 1.4 });
}

// Background maps: all free, no API key.
//
// NASA GIBS tiles (https://gibs.earthdata.nasa.gov), Web Mercator version (EPSG:3857).
// URL format: .../wmts/epsg3857/best/{layer}/default/{tile matrix set}/{z}/{y}/{x}.jpeg
// (note the order: row {y} comes before column {x}).
// Both layers below use the "GoogleMapsCompatible_Level8" tile matrix set: their tiles
// stop at zoom 8. maxNativeZoom: 8 tells Leaflet to stretch the zoom-8 tiles when the
// user zooms further, instead of asking for tiles that do not exist (blank map).
const GIBS_URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";
const GIBS_ATTRIBUTION = 'Imagery: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> (Global Imagery Browse Services), NASA EOSDIS';

const baseLayers = {
  // Default: natural-color Earth with relief and sea floor
  "Blue Marble (NASA)": L.tileLayer(GIBS_URL, {
    layer: "BlueMarble_ShadedRelief_Bathymetry",
    attribution: GIBS_ATTRIBUTION,
    maxNativeZoom: 8,
    maxZoom: 14,
  }),
  // Detailed satellite imagery, to zoom into one site
  "Satellite (Esri)": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    maxZoom: 14,
  }),
  // Dark style: city lights at night (VIIRS, 2012)
  "Earth at Night (NASA)": L.tileLayer(GIBS_URL, {
    layer: "VIIRS_CityLights_2012",
    attribution: GIBS_ATTRIBUTION,
    maxNativeZoom: 8,
    maxZoom: 14,
  }),
};

baseLayers["Blue Marble (NASA)"].addTo(map);        // shown at start
L.control.layers(baseLayers).addTo(map);            // layer switcher, top-right corner

// All markers go in this group, so we can remove them all at once before redrawing.
const markerLayer = L.layerGroup().addTo(map);

// ---- Helpers ----

// Color for a score between 0 and 100: a mix of NASA blue and white (the browser does the mixing).
function scoreColor(score) {
  let percent = (score - RAMP_START) / (100 - RAMP_START) * 100;
  percent = Math.round(Math.max(0, Math.min(100, percent)));
  return "color-mix(in oklab, var(--white) " + percent + "%, var(--nasa-blue))";
}

// Total score of a site for the selected target and profile.
// Returns null when the site has no score for this combination
// (the file only contains the top tiles of each target × profile).
function getTotal(site) {
  const targetScores = site.scores ? site.scores[currentTarget] : null;
  const profileScores = targetScores ? targetScores[currentProfile] : null;
  if (!profileScores || profileScores.total == null) return null;
  return profileScores.total;
}

// Ranking for the selected target and profile: every site that has a score,
// best first, as a list of { site, total, rank }. Sites with the same score share
// the same rank (1, 2, 2, 4…). Used by the "Top sites" and "Validation" tabs.
function getRanking() {
  const scored = data.sites
    .filter(function (site) { return getTotal(site) !== null; })
    .sort(function (a, b) { return getTotal(b) - getTotal(a); });
  const ranking = [];
  scored.forEach(function (site, index) {
    const total = getTotal(site);
    const previous = ranking[index - 1];
    const rank = previous && previous.total === total ? previous.rank : index + 1;
    ranking.push({ site: site, total: total, rank: rank });
  });
  return ranking;
}

// Protect text coming from the data file before putting it in HTML.
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

// ---- Selectors (segmented controls) ----

// Fill a segmented control with a list of { id, label, tag } options.
// Each option is a radio button; onChange(id) is called when the user picks one.
// The first option starts selected.
function fillSegmented(container, name, options, onChange) {
  // The red block behind the active option (moved by moveThumb)
  container.innerHTML = '<div class="thumb"></div>';
  options.forEach(function (option, index) {
    const label = document.createElement("label");

    const input = document.createElement("input");
    input.type = "radio";
    input.name = name;
    input.value = option.id;
    input.checked = index === 0;
    input.addEventListener("change", function () {
      moveThumb(container);
      onChange(option.id);
    });

    const text = document.createElement("span");
    text.textContent = option.label;
    if (option.tag) {
      const tag = document.createElement("small");   // small tag after the name, e.g. "Mars"
      tag.textContent = option.tag;
      text.appendChild(tag);
    }

    label.appendChild(input);
    label.appendChild(text);
    container.appendChild(label);
  });

  // Place the thumb now (no animation), and again when sizes change:
  // when the IBM Plex fonts finish loading, and when the window is resized.
  moveThumb(container);
  document.fonts.ready.then(function () {
    moveThumb(container);
    // From now on, the thumb slides when the selection changes (see .ready in the CSS).
    requestAnimationFrame(function () { container.classList.add("ready"); });
  });
  window.addEventListener("resize", function () { moveThumb(container); });
}

// Put the red thumb of a segmented control exactly behind its selected option.
function moveThumb(container) {
  const option = container.querySelector("input:checked").parentElement;   // the <label>
  const thumb = container.querySelector(".thumb");
  thumb.style.width = option.offsetWidth + "px";
  thumb.style.transform = "translateX(" + option.offsetLeft + "px)";
}

// Soft fade of the markers after their colors changed (new target or profile),
// so the map does not "jump" from one set of colors to the other.
function fadeInMarkers() {
  const panes = [map.getPane("overlayPane"), map.getPane("markerPane")];
  for (const pane of panes) {
    pane.animate([{ opacity: 0.25 }, { opacity: 1 }], { duration: 320, easing: "ease-out" });
  }
}

// Small label in the top bar showing the selected target, e.g. "MARS · JEZERO CRATER"
// (the CSS shows it in capitals).
function updateTargetReadout() {
  const target = data.targets[currentTarget];
  document.getElementById("target-readout").textContent = target.body + " · " + target.name;
}

function setupSelectors() {
  // Targets come from data.targets: { jezero: { name, body, ... }, ... }
  const targetOptions = Object.keys(data.targets).map(function (id) {
    const target = data.targets[id];
    return { id: id, label: target.name, tag: target.body };
  });

  currentTarget = targetOptions[0].id;
  currentProfile = data.meta.profiles[0].id;
  updateTargetReadout();

  // Redraw the map and the open site card every time a selection changes.
  fillSegmented(document.getElementById("target-select"), "target", targetOptions, function (id) {
    currentTarget = id;
    updateTargetReadout();
    renderMap();
    fadeInMarkers();
    renderPanel();
  });
  fillSegmented(document.getElementById("profile-select"), "profile", data.meta.profiles, function (id) {
    currentProfile = id;
    renderMap();
    fadeInMarkers();
    renderPanel();
  });
}

// ---- Map drawing ----

function renderMap() {
  markerLayer.clearLayers();

  // 0) NASA red ring around the site open in the side panel.
  const selected = data.sites.find(function (site) { return site.id === selectedSiteId; });
  if (selected) {
    L.circleMarker([selected.lat, selected.lon], {
      radius: 11,
      color: "#FFFFFF",     // white ring under the red one: the red stays visible on deserts
      weight: 5,
      fill: false,
      interactive: false,   // clicks go through to the site under it
    }).addTo(markerLayer);
    L.circleMarker([selected.lat, selected.lon], {
      radius: 11,
      color: "#FC3D21",     // NASA red
      weight: 2.5,
      fill: false,
      interactive: false,
    }).addTo(markerLayer);
  }

  // 1) Sites. Sorted by score so the best ones are drawn last (on top).
  const sites = data.sites
    .filter(function (site) { return getTotal(site) !== null; })
    .sort(function (a, b) { return getTotal(a) - getTotal(b); });

  for (const site of sites) {
    const total = getTotal(site);
    const color = scoreColor(total);
    let marker;

    if (site.hidden_gem) {
      // Hidden gem: a NASA red star (its score is in the hover label and the side panel)
      marker = L.marker([site.lat, site.lon], {
        icon: L.divIcon({
          className: "gem-marker",
          html: "★",
          iconSize: [20, 20],
        }),
      });
    } else {
      // Normal site: a circle, colored by score
      marker = L.circleMarker([site.lat, site.lon], {
        radius: 4.5,
        color: "#FFFFFF",   // thin white edge (the CSS adds a dark glow around it)
        weight: 1,
        opacity: 0.9,
        fillOpacity: 1,
        className: "site-dot",
      });
    }

    // Small label on hover
    let label = escapeHtml(site.region) + ' — score <span class="num">' + total + "</span>";
    if (site.hidden_gem) label += " ★ hidden gem";
    if (site.known_analog) label += "<br>Known analog: " + escapeHtml(site.known_analog);
    marker.bindTooltip(label);

    // Click: open this site in the side panel (see js/panel.js)
    marker.on("click", function () {
      openSite(site.id, false);   // false = do not move the map
    });

    marker.addTo(markerLayer);

    // Circles get their fill color here (as a CSS style), because the ramp color
    // uses CSS variables, which Leaflet's own fillColor option cannot read.
    if (!site.hidden_gem) marker.getElement().style.fill = color;
  }

  // 2) Known analogs: white diamonds at their real location.
  for (const analog of data.known_analogs) {
    // The site (tile) that carries this analog, if it is drawn on the map right now.
    const analogSite = sites.find(function (site) { return site.known_analog === analog.name; });
    const marker = L.marker([analog.lat, analog.lon], {
      icon: L.divIcon({
        className: "analog-marker",
        html: "<span></span>",
        iconSize: [16, 16],
      }),
      interactive: true,
      zIndexOffset: -100,  // stay under the stars so both can be clicked
    });
    marker.bindTooltip(
      "<b>" + escapeHtml(analog.name) + "</b><br>" +
      "Known analog for: " + escapeHtml(analog.analog_for) + "<br>" +
      "Used for: " + escapeHtml(analog.used_for)
    );
    // The diamond sits on top of its site circle and would steal the click:
    // so a click on the diamond opens that site (its card shows the analog as a badge).
    if (analogSite) {
      marker.on("click", function () { openSite(analogSite.id, false); });
    }
    marker.addTo(markerLayer);
  }
}

// ---- Legend ----

function renderLegend() {
  // The star is only explained when at least one site is a hidden gem
  // (the pipeline delivers them late: until then hidden_gem is false everywhere).
  const hasGems = data.sites.some(function (site) { return site.hidden_gem; });
  const gemKey = hasGems ? '<span><span class="star">★</span> Hidden gem</span>' : "";

  document.getElementById("legend").innerHTML =
    '<div class="legend-title">Total score</div>' +
    '<div class="legend-bar"></div>' +                       // gradient: NASA blue -> white
    '<div class="legend-scale num"><span>≤ ' + RAMP_START + "</span><span>100</span></div>" +
    '<div class="legend-keys">' + gemKey + "<span>◇ Known analog</span></div>";
}

// ---- Start: load the data, then draw everything ----

fetch(DATA_URL)
  .then(function (response) {
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  })
  .then(function (json) {
    data = json;
    setupSelectors();
    renderLegend();
    renderMap();
  })
  .catch(function (error) {
    console.error("Could not load " + DATA_URL, error);
    document.getElementById("panel-content").innerHTML =
      '<p class="placeholder">Could not load ' + DATA_URL + ". " +
      "Open the site through a local server (for example: <code>python3 -m http.server</code>), " +
      "not by double-clicking index.html.</p>";
  });

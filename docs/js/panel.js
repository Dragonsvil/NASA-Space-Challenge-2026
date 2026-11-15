// Planetary Analog Finder — side panel
// Three tabs: "Site" (card of the clicked site), "Top sites" (top 10) and
// "Validation" (do the known analogs come out with a high rank?).
// Uses the variables and helpers of app.js: data, currentTarget, currentProfile,
// selectedSiteId, scoreColor(), cssColor(), escapeHtml(), siteName(), formatCoords(), formatScore(), hasCoords(),
// analogBodies(), isHiddenGem(), lacksData(), getRanking(), flyToVisibleCenter(), fillSegmented(), moveThumb(), renderRing().

// A dimension scoring below this is listed in "Where the analogy breaks".
const BREAK_THRESHOLD = 40;

// Plain words for each dimension, used to build the "Works for…" sentence:
// "Good for testing rover navigation: <words> and <words> similar to Jezero Crater."
// The words must stay NEUTRAL: a high score means "close to the target", not "a lot of it"
// (a site with a high roughness score is as smooth or as rough as the target, whatever that is).
// The only exception is "dry ground": both targets get 0 mm of rain a year.
// If the pipeline adds a new dimension, its label from the data file is used instead.
const DIMENSION_WORDS = {
  temp_range: "day–night temperature swings",
  temp_min:   "night temperatures",
  albedo:     "surface brightness",
  slope:      "slopes",
  roughness:  "terrain roughness",
  mafic:      "basaltic rock",
  aridity:    "dry ground",
  dust:       "dust levels",
  sun_angle:  "low sun angles",
};

// What each mission profile tests, used in the "Works for…" sentence.
const PROFILE_WORDS = {
  rover:   "rover navigation",
  geology: "geology and science work",
  polar:   "polar and thermal operations",
};

// How many dimensions the "Works for…" sentence names (the best ones).
const WORKS_COUNT = 2;

// Limits that no place on Earth can reproduce (text from CLAUDE.md), per body.
const ALWAYS_BREAKS = {
  Moon: [
    "Gravity: the Moon has about 1/6 of Earth's gravity.",
    "Atmosphere: the Moon is in vacuum.",
    "Radiation: Earth is shielded by its atmosphere and magnetic field.",
  ],
  Mars: [
    "Gravity: Mars has about 0.38 of Earth's gravity.",
    "Atmosphere: Mars has thin CO2 air, about 1% of Earth's pressure.",
    "Radiation: Earth is shielded by its atmosphere and magnetic field.",
  ],
};

// How many sites the "Top sites" tab lists.
const TOP_COUNT = 10;

// A known analog is highlighted in the "Validation" tab when it is in
// the best 10% of all the barren-land tiles scored for the selected target and profile.
const TOP_PERCENT = 10;

// "Top sites" tab: false = list the best sites, true = list only the hidden gems.
let topGemsOnly = false;

// The tab on screen: "site", "top" or "validation".
let currentTab = "site";
let shownTab = null;        // tab drawn by the last renderPanel() call

// The radar chart currently on screen (we must destroy it before drawing a new one).
let radarChart = null;

// The site shown by the last renderPanel() call. Used to know if the user opened
// a NEW site (the card rises in) or only changed target/profile (bars slide, no jump).
let shownSiteId = null;

// People who asked their system for less motion get fades only, no movement.
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

// Put new content in the panel, with a short fade.
//   isNewSite = true : the card also rises a few pixels, and the panel scrolls back to the top
//   isNewSite = false: quick fade only, the scroll position is kept
function showCard(html, isNewSite) {
  const panel = document.getElementById("panel-content");
  panel.innerHTML = '<div class="card">' + html + "</div>";
  if (isNewSite) panel.scrollTop = 0;

  const rise = isNewSite && !reducedMotion.matches ? "translateY(8px)" : "none";
  panel.firstElementChild.animate(
    [{ opacity: isNewSite ? 0 : 0.5, transform: rise }, { opacity: 1, transform: "none" }],
    { duration: isNewSite ? 280 : 200, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }
  );
}

// ---- Small helpers ----

// "4.1 °" / "0.17" / "no data" — a real value with its unit.
function formatValue(value, unit) {
  if (value == null) return "no data";
  // At most 3 decimals, even if the file holds 0.30000000000000004
  if (typeof value === "number") value = Math.round(value * 1000) / 1000;
  if (!unit) return String(value);
  // Degrees stick to the number ("4.1°"), other units get a space ("38 °C")
  return unit === "°" ? value + unit : value + " " + unit;
}

// Cut a long label into short lines, so it fits around the radar chart.
function wrapLabel(label) {
  const lines = [];
  let line = "";
  for (const word of label.split(" ")) {
    if (line && (line + " " + word).length > 16) {
      lines.push(line);
      line = word;
    } else {
      line = line ? line + " " + word : word;
    }
  }
  lines.push(line);
  return lines;
}

// "A" / "A and B" / "A, B and C"
function joinNames(names) {
  if (names.length <= 1) return names.join("");
  return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
}

// A label from the data file, turned into words for the middle of a sentence:
// lower case, no bracket part, no "/" or "&".
//   "Basaltic rock (mafic index)" -> "basaltic rock"     "Polar & thermal ops" -> "polar and thermal ops"
function plainWords(label) {
  return String(label)
    .replace(/\s*\([^)]*\)/g, "")       // drop "(mafic index)": no brackets inside the sentence
    .replace(/\s*[\/&]\s*/g, " and ")
    .trim()
    .toLowerCase();
}

// A target name in the middle of a sentence. A proper name stays as it is ("Jezero Crater");
// a description gets "the" and a small first letter ("Lunar south pole" -> "the lunar south pole").
// A description is recognised by its second word, which starts with a small letter.
function nameInSentence(name) {
  name = String(name);
  if (/^[A-Z][a-z]+ [a-z]/.test(name)) return "the " + name[0].toLowerCase() + name.slice(1);
  return name;
}

// How much a dimension counts for a mission profile (meta.profiles[].weights in the data file).
// Returns null when the file gives no usable weight for it.
// The weights are read ONLY here, to choose which dimensions the "Works for…" sentence names:
// the site never recomputes a score with them.
function profileWeight(profile, dimId) {
  const weight = profile.weights ? profile.weights[dimId] : null;
  return typeof weight === "number" && isFinite(weight) && weight >= 0 ? weight : null;
}

// The "Works for…" sentence, in plain words and without any number:
//   "Good for testing rover navigation: dry ground and terrain roughness similar to Jezero Crater."
// It names the dimensions of the site that matter most for the selected profile (WORKS_COUNT at most):
// they are ranked by score × profile weight. Never named:
//   - a dimension scoring below BREAK_THRESHOLD (it is listed in "Where the analogy breaks" instead),
//   - a dimension with weight 0 (the profile does not use it).
// If the file has no weights for this profile, the best scores are named, whatever the profile.
function worksSentence(rows, target, profile) {
  const good = rows.filter(function (row) { return row.score != null && row.score >= BREAK_THRESHOLD; });
  // Weights are used only when the file gives one for every dimension in the running
  const hasWeights = good.length > 0 &&
    good.every(function (row) { return profileWeight(profile, row.id) !== null; });

  const best = good
    .map(function (row) {
      const weight = hasWeights ? profileWeight(profile, row.id) : 1;
      return { row: row, weight: weight, rank: row.score * weight };
    })
    .filter(function (entry) { return entry.weight > 0; })
    .sort(function (a, b) { return b.rank - a.rank || b.row.score - a.row.score; })   // equal: best score first
    .slice(0, WORKS_COUNT)
    .map(function (entry) { return entry.row; });
  const where = nameInSentence(target.name);

  // Nothing that matters for this profile is close to the target: do not pretend something works.
  if (best.length === 0) return "No dimension of this site is a close match to " + where + ".";

  const words = best.map(function (row) { return DIMENSION_WORDS[row.id] || plainWords(row.label); });
  const activity = PROFILE_WORDS[profile.id] || plainWords(profile.label);
  return "Good for testing " + activity + ": " + joinNames(words) + " similar to " + where + ".";
}

// One sentence saying WHY a site is a hidden gem. The clustering puts tiles that look
// alike in the same `cluster` ("terrain family"). So we look for the known analogs whose
// own tile is in the same cluster as this site.
function gemReason(site) {
  const names = [];
  if (site.cluster != null) {
    for (const other of data.sites) {
      if (other.id !== site.id && other.known_analog && other.cluster === site.cluster &&
          !names.includes(other.known_analog)) {
        names.push(other.known_analog);
      }
    }
  }
  // No known analog in this cluster (or no cluster at all)
  if (names.length === 0) return "Unstudied site with a high match.";
  return "Same terrain family as " + joinNames(names) +
         (site.known_analog ? "." : ", but not a known analog site.");
}

// Where the target value of one dimension comes from (targets[target].sources), or null.
function getSource(target, dimId) {
  const source = target.sources ? target.sources[dimId] : null;
  return typeof source === "string" && source !== "" ? source : null;
}

// The dimensions the pipeline did not score in this version of the file
// (meta.dropped_dimensions, e.g. [{"id": "dust", "reason": "no data"}]; an older file has no such key).
function droppedDimensions() {
  const list = data.meta.dropped_dimensions;
  if (!Array.isArray(list)) return [];
  return list.filter(function (entry) { return entry && typeof entry.id === "string"; });
}

// Why a dimension was dropped: its reason ("" when the file gives none), or null when it is NOT dropped.
function droppedReason(dimId) {
  const entry = droppedDimensions().find(function (d) { return d.id === dimId; });
  if (!entry) return null;
  return typeof entry.reason === "string" ? entry.reason.trim() : "";
}

// One row per dimension used by the selected target, with everything the card needs.
function getDimensionRows(site, target, profileScores) {
  const rows = [];
  for (const dimId of target.dims) {
    // Label and unit come from meta.dimensions
    const info = data.meta.dimensions.find(function (d) { return d.id === dimId; })
              || { id: dimId, label: dimId, unit: "" };
    // A dropped dimension is not scored: a score left in the file for it is ignored. With no score,
    // it stays out of the radar, of "Works for…" and of "Where the analogy breaks" (like any "no data").
    const dropped = droppedReason(dimId);
    const score = profileScores.dims && dropped === null ? profileScores.dims[dimId] : null;
    rows.push({
      id: dimId,
      label: info.label,
      unit: info.unit,
      score: score == null ? null : score,              // 0–100, or null
      siteValue: site.values ? site.values[dimId] : null,
      targetValue: target.values ? target.values[dimId] : null,
      source: getSource(target, dimId),                 // where the target value comes from, or null
      dropped: dropped,                                 // null, or the reason it is not scored ("" = no reason given)
    });
  }
  return rows;
}

// ---- The panel ----

// Draw the tab that is selected. Called on every click on a site or a tab,
// and every time the target or profile changes.
function renderPanel() {
  syncOrbi();   // keep Orbi up to date with the target, profile and selected site (js/app.js)

  // Remove the old chart first: its <canvas> is about to disappear.
  if (radarChart) {
    radarChart.destroy();
    radarChart = null;
  }

  const isNewTab = currentTab !== shownTab;   // tab just opened: its content rises in
  shownTab = currentTab;

  if (currentTab === "top") {
    shownSiteId = null;
    renderTopSites(isNewTab);
  } else if (currentTab === "validation") {
    shownSiteId = null;
    renderValidation(isNewTab);
  } else {
    renderSiteCard();
  }
}

// Select a site: red ring on the map, card in the "Site" tab.
//   fly = true: the map also flies to the site (used by the lists; a click on the
//   map itself passes false, the site is already under the mouse).
function openSite(siteId, fly) {
  const site = data.sites.find(function (s) { return s.id === siteId; });
  if (!site) return;
  selectedSiteId = siteId;
  // Phones: the panel is a bottom sheet, open it halfway BEFORE moving the map (js/sheet.js),
  // so the site lands in the part of the map that stays visible above the sheet.
  openSheetForSite(site, fly);
  if (fly && hasCoords(site)) flyToVisibleCenter(site.lat, site.lon);
  showTab("site");
  renderRing();      // moves the red ring (the other markers do not change)
  renderPanel();
}

// Switch the tab control to a tab from the code (the user did not click the tab itself).
function showTab(tabId) {
  const tabs = document.getElementById("panel-tabs");
  tabs.querySelector('input[value="' + tabId + '"]').checked = true;
  moveThumb(tabs);
  currentTab = tabId;
}

// "Site" tab: the card of the selected site (or the placeholder when nothing is selected).
function renderSiteCard() {
  const panel = document.getElementById("panel-content");

  const site = data.sites.find(function (s) { return s.id === selectedSiteId; });
  if (!site) {
    panel.innerHTML = '<p class="placeholder">Select a site on the map to see its details.</p>';
    shownSiteId = null;
    return;
  }

  // Same site as before (only the target or profile changed)? Then remember where each
  // score bar is now, so the new bars can start from there instead of jumping.
  const isNewSite = site.id !== shownSiteId;
  shownSiteId = site.id;
  const oldBars = {};
  if (!isNewSite) {
    for (const bar of panel.querySelectorAll(".bar-fill")) {
      oldBars[bar.dataset.dim] = bar.style.transform;
    }
  }

  const target = data.targets[currentTarget];
  const profile = data.meta.profiles.find(function (p) { return p.id === currentProfile; });
  const targetScores = site.scores ? site.scores[currentTarget] : null;
  const profileScores = targetScores ? targetScores[currentProfile] : null;

  // ---- 1) Header: region, coordinates, badges, big score ----
  const gem = isHiddenGem(site);
  let badges = "";
  if (gem) badges += '<span class="badge badge-gem">★ Hidden gem</span>';
  if (site.known_analog) {
    badges += '<span class="badge badge-known">◇ Known analog: ' + escapeHtml(site.known_analog) + "</span>";
  }

  const hasScore = profileScores && profileScores.total != null;
  // Too much data missing for this profile: the pipeline gave no total (the site is not ranked).
  // The card then shows a sentence instead of the big score.
  const tooLittleData = lacksData(site);
  let html =
    '<div class="site-header">' +
      "<div>" +
        "<h2>" + escapeHtml(siteName(site)) + "</h2>" +
        '<div class="coords num">' + formatCoords(site.lat, site.lon) + "</div>" +
        '<div class="badges">' + badges + "</div>" +
      "</div>" +
      (tooLittleData ? "" :
        '<div class="big-score' + (hasScore ? "" : " no-score") + '">' +
          (hasScore ? formatScore(profileScores.total) : "–") + "<small>/ 100</small>" +
        "</div>") +
    "</div>" +
    // Hidden gem: one sentence saying why (same cluster as which known analogs)
    (gem ? '<p class="gem-why">' + escapeHtml(gemReason(site)) + "</p>" : "") +
    '<p class="context">Compared to <b>' + escapeHtml(target.name) + "</b> (" + escapeHtml(target.body) +
    ") — " + escapeHtml(profile.label) + "</p>";

  // Not enough data: say so calmly (this is not an error), and stop here.
  if (tooLittleData) {
    html += '<p class="no-score-note">Not enough data to score this site for this profile.</p>';
    showCard(html, isNewSite);
    return;
  }

  // The file only holds the top tiles of each target × profile:
  // this site may have no score for the new selection.
  if (!hasScore) {
    html += '<p class="placeholder">This site is not among the top sites for this target and ' +
            "mission profile, so it has no score here. Pick another target or profile, or another site.</p>";
    showCard(html, isNewSite);
    return;
  }

  const rows = getDimensionRows(site, target, profileScores);

  // ---- 2) Radar chart (drawn after the HTML is in the page, see below) ----
  // A radar needs at least 3 scored dimensions to draw a shape: with fewer
  // (target with 1 or 2 dimensions, site with no data) the list below says it all.
  const scoredRows = rows.filter(function (row) { return row.score != null; });
  const hasRadar = scoredRows.length >= 3;
  if (hasRadar) html += '<div class="radar-box"><canvas id="radar"></canvas></div>';

  // ---- 3) Dimension list: label, score bar, real value vs target value ----
  html += "<h3>Dimensions</h3>";
  for (const row of rows) {
    // Dropped dimension: its name, "no data" and the reason. No bar and no values to compare.
    if (row.dropped !== null) {
      html +=
        '<div class="dim">' +
          '<div class="dim-top">' +
            "<span>" + escapeHtml(row.label) + "</span>" +
            '<span class="dim-score num no-data">no data</span>' +
          "</div>" +
          '<div class="dim-dropped">Not scored in this version' +
            (row.dropped ? ": " + escapeHtml(row.dropped) : "") + "</div>" +
        "</div>";
      continue;
    }
    const hasDimScore = row.score != null;
    html +=
      '<div class="dim">' +
        '<div class="dim-top">' +
          "<span>" + escapeHtml(row.label) + "</span>" +
          '<span class="dim-score num' + (hasDimScore ? "" : " no-data") + '">' + (hasDimScore ? formatScore(row.score) : "no data") + "</span>" +
        "</div>" +
        // The bar starts where the old one was (or empty), then slides to data-score (see below)
        '<div class="bar"><div class="bar-fill" data-dim="' + escapeHtml(row.id) + '"' +
          ' data-score="' + (hasDimScore ? row.score : 0) + '"' +
          ' style="transform:' + (oldBars[row.id] || "scaleX(0)") + ";" +
          "background:" + (hasDimScore ? scoreColor(row.score) : "transparent") + '"></div></div>' +
        '<div class="dim-values">' +
          '<span>This site <span class="num">' + escapeHtml(formatValue(row.siteValue, row.unit)) + "</span></span>" +
          "<span>" + escapeHtml(target.name) + ' <span class="num">' + escapeHtml(formatValue(row.targetValue, row.unit)) + "</span></span>" +
        "</div>" +
        // Citation for the target value, small and muted
        (row.source ? '<div class="dim-source">Source: ' + escapeHtml(row.source) + "</div>" : "") +
      "</div>";
  }

  // ---- 4) "Works for…": one plain sentence (see worksSentence() above) ----
  html += "<h3>Works for…</h3>";
  if (scoredRows.length === 0) {
    html += '<p class="placeholder">No dimension score available for this site.</p>';
  } else {
    html += '<p class="works">' + escapeHtml(worksSentence(rows, target, profile)) + "</p>";
  }

  // ---- 5) "Where the analogy breaks": always gravity, atmosphere, radiation,
  //         plus every dimension of this site scoring below 40 ----
  html += '<div class="breaks"><h3>Where the analogy breaks</h3><ul>';
  for (const text of ALWAYS_BREAKS[target.body] || []) {
    html += "<li>" + escapeHtml(text) + "</li>";
  }
  for (const row of rows) {
    if (row.score != null && row.score < BREAK_THRESHOLD) {
      html += "<li>" + escapeHtml(row.label) + ': <span class="num">' +
              escapeHtml(formatValue(row.siteValue, row.unit)) + '</span> here, <span class="num">' +
              escapeHtml(formatValue(row.targetValue, row.unit)) + "</span> at " + escapeHtml(nameInSentence(target.name)) +
              ' (score <span class="num">' + formatScore(row.score) + "</span>).</li>";
    }
  }
  html += "</ul></div>";

  // ---- 6) Sources of the target values (only the dimensions that have one) ----
  //         plus one line naming the dimensions of this target that are not scored in this version of the file
  const sourced = rows.filter(function (row) { return row.source && row.dropped === null; });
  const droppedNames = rows
    .filter(function (row) { return row.dropped !== null; })
    .map(function (row) {
      return plainWords(row.label) + (row.dropped ? " (" + row.dropped + ")" : "");   // "dust (no data)"
    });
  if (sourced.length > 0 || droppedNames.length > 0) html += "<h3>Sources</h3>";
  if (sourced.length > 0) {
    html += '<p class="sources-intro">Where the ' + escapeHtml(target.name) + " values come from.</p>" +
            '<dl class="sources">';
    for (const row of sourced) {
      html += "<dt>" + escapeHtml(row.label) + "</dt><dd>" + escapeHtml(row.source) + "</dd>";
    }
    html += "</dl>";
  }
  if (droppedNames.length > 0) {
    html += '<p class="sources-dropped">Not scored in this version: ' + escapeHtml(droppedNames.join(", ")) + ".</p>";
  }

  showCard(html, isNewSite);

  // Slide every score bar to its score (the CSS transition does the animation).
  // Reading offsetWidth first makes the browser draw the start position.
  for (const bar of panel.querySelectorAll(".bar-fill")) {
    bar.offsetWidth;
    bar.style.transform = "scaleX(" + bar.dataset.score / 100 + ")";
  }

  // The radar has no axis for a dropped dimension
  if (hasRadar) drawRadar(rows.filter(function (row) { return row.dropped === null; }), target);
}

// Radar chart: the site's scores against the target (100 on every axis).
function drawRadar(rows, target) {
  const blue = cssColor("--nasa-blue");
  const white = cssColor("--white");
  radarChart = new Chart(document.getElementById("radar"), {
    type: "radar",
    data: {
      labels: rows.map(function (row) { return wrapLabel(row.label); }),
      datasets: [
        {
          label: target.name + " (target)",
          data: rows.map(function () { return 100; }),
          borderColor: white,          // target outline: white dashed
          borderDash: [3, 4],
          borderWidth: 1,
          backgroundColor: "transparent",
          pointRadius: 0,
        },
        {
          label: "This site",
          // A missing score (null) leaves a gap in the shape
          data: rows.map(function (row) { return row.score; }),
          borderColor: white,          // site shape: NASA blue fill, white edge
          borderWidth: 1.5,
          backgroundColor: blue + "cc",   // NASA blue, slightly transparent
          pointBackgroundColor: white,
          pointBorderColor: white,
          pointRadius: 2.5,
        },
      ],
    },
    options: {
      animation: { duration: reducedMotion.matches ? 0 : 450, easing: "easeOutQuart" },
      scales: {
        r: {
          min: 0,
          max: 100,
          // rings every 25 points; no numbers on them (they would sit on top of the shape)
          ticks: { stepSize: 25, display: false },
          grid: { color: "rgba(255, 255, 255, 0.13)" },
          angleLines: { color: "rgba(255, 255, 255, 0.13)" },
          pointLabels: { color: "rgba(255, 255, 255, 0.74)", font: { family: "IBM Plex Sans", size: 10.5 } },
        },
      },
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "rgba(255, 255, 255, 0.74)", usePointStyle: true, pointStyle: "line", boxWidth: 18, font: { family: "IBM Plex Sans", size: 11 } },
        },
      },
    },
  });
}

// The chart is drawn on a canvas: if the IBM Plex fonts finish loading after
// the chart was drawn, redraw it once so its labels use the right font.
document.fonts.ready.then(function () {
  if (radarChart) radarChart.update();
});


// ---- "Top sites" tab ----

// Small line under a tab title: what the list is about.
function contextLine(text) {
  const target = data.targets[currentTarget];
  const profile = data.meta.profiles.find(function (p) { return p.id === currentProfile; });
  return '<p class="context">' + text + " <b>" + escapeHtml(target.name) + "</b> (" +
         escapeHtml(target.body) + ") — " + escapeHtml(profile.label) + "</p>";
}

// The 10 best sites for the selected target and profile. Click = fly there + open the card.
function renderTopSites(isNewTab) {
  const ranking = getRanking();
  const gems = ranking.filter(function (entry) { return isHiddenGem(entry.site); });
  // The "hidden gems only" choice is only offered when this target has gems.
  const gemsOnly = topGemsOnly && gems.length > 0;
  const top = (gemsOnly ? gems : ranking).slice(0, TOP_COUNT);

  // "Top 10 sites", or "Top 3 hidden gems" when the list is shorter than 10
  let html = "<h2>Top " + (top.length > 0 ? top.length + " " : "") + (gemsOnly ? "hidden gems" : "sites") + "</h2>" +
             contextLine("Closest to");

  // Two buttons: all the sites, or only the hidden gems (with how many there are).
  if (gems.length > 0) {
    html +=
      '<div class="filter" role="group" aria-label="Sites to list">' +
        '<button type="button" data-filter="all" aria-pressed="' + !gemsOnly + '">All sites</button>' +
        '<button type="button" class="filter-gems" data-filter="gems" aria-pressed="' + gemsOnly + '">★ Hidden gems' +
          '<span class="num">' + gems.length.toLocaleString("en-US") + "</span></button>" +
      "</div>";
    // In the gems list, the number on the left is still the rank among ALL the sites.
    if (gemsOnly) html += '<p class="rank-note">The number on the left is the rank among all the sites on the map.</p>';
  }

  if (top.length === 0) {
    html += '<p class="placeholder">No site has a score for this target and mission profile.</p>';
    showCard(html, isNewTab);
    return;
  }

  html += '<ol class="rank-list">';
  for (const entry of top) {
    const site = entry.site;
    let marks = "";
    if (isHiddenGem(site)) marks += '<span class="badge badge-gem">★ Hidden gem</span>';
    if (site.known_analog) marks += '<span class="badge">◇ ' + escapeHtml(site.known_analog) + "</span>";

    html +=
      "<li>" +
        // A real <button>: works with the mouse and the keyboard
        '<button type="button" class="rank-row' + (site.id === selectedSiteId ? " selected" : "") +
          '" data-site="' + escapeHtml(site.id) + '">' +
          '<span class="rank num">' + entry.rank + "</span>" +
          '<span class="rank-main">' +
            '<span class="rank-name">' + escapeHtml(siteName(site)) + "</span>" +
            '<span class="coords num">' + formatCoords(site.lat, site.lon) + "</span>" +
            (marks ? '<span class="badges">' + marks + "</span>" : "") +
          "</span>" +
          '<span class="rank-score num">' + formatScore(entry.total) + "</span>" +
          // Same score bar as on the site card
          '<span class="bar"><span class="bar-fill" style="transform:scaleX(' + entry.total / 100 +
            ");background:" + scoreColor(entry.total) + '"></span></span>' +
        "</button>" +
      "</li>";
  }
  html += "</ol>";
  showCard(html, isNewTab);
}

// ---- "Validation" tab ----

// Used for "top X% of Earth's barren land":
// "3.2" / "12" / "0.04": a percentile, short enough to read at a glance.
function formatPercent(percentile) {
  if (percentile < 0.01) return "<0.01";      // rank 1 of 200,000 must not read "Top 0%"
  if (percentile < 0.1) return String(Number(percentile.toFixed(2)));
  if (percentile < 10) return String(Number(percentile.toFixed(1)));
  return String(Math.round(percentile));
}

// The site (tile) of a known analog, if it is drawn on the map for the current
// target and profile. Returns null when the analog's tile is not in `sites`.
function findAnalogSite(analog) {
  const site = data.sites.find(function (s) { return s.known_analog === analog.name; });
  return site && getTotal(site) !== null ? site : null;
}

// Table of the known analogs with their score and their rank among ALL the tiles
// of barren land (global_rank in known_analogs[].scores, from the pipeline): if the method works,
// places that space agencies already use should come out near the top.
function renderValidation(isNewTab) {
  const target = data.targets[currentTarget];
  // How many barren-land tiles the pipeline scored for this target (null if the file does not say).
  const tilesScored = data.meta.tiles_scored ? data.meta.tiles_scored[currentTarget] : null;

  // One row per known analog. `index` is its position in data.known_analogs.
  const rows = data.known_analogs.map(function (analog, index) {
    // analog.scores is null when its tile was not scored (e.g. vegetated tile):
    // analog.tile_note then says why.
    const targetScores = analog.scores ? analog.scores[currentTarget] : null;
    const score = (targetScores ? targetScores[currentProfile] : null) || {};
    const globalRank = score.global_rank == null ? null : score.global_rank;
    // "Top X% of Earth's barren land" (lower = better). Always computed here from the rank:
    // the file's own "percentile" field is ignored, its convention may differ.
    const percentile = globalRank !== null && tilesScored
      ? globalRank / tilesScored * 100
      : null;
    return {
      index: index,
      analog: analog,
      total: score.total == null ? null : score.total,
      globalRank: globalRank,
      isScored: globalRank !== null,                            // false = left out of the summary
      note: analog.tile_note || null,                           // short remark from the pipeline
      percentile: percentile,                                   // "top X% of barren land", or null
      tilesScored: tilesScored || null,                         // M in "#N of M"
      isTop: percentile !== null && percentile <= TOP_PERCENT,
      site: findAnalogSite(analog),                             // null = no site card to open
      // The profiles this analog is really used for (known_analogs[].validated_profiles), or null
      // when the file does not say. It only counts in the summary for those profiles.
      profiles: Array.isArray(analog.validated_profiles) ? analog.validated_profiles : null,
    };
  });

  // Best rank first; analogs without a rank go last.
  rows.sort(function (a, b) {
    if (a.globalRank === null) return b.globalRank === null ? 0 : 1;
    if (b.globalRank === null) return -1;
    return a.globalRank - b.globalRank;
  });

  // Analogs of the selected body (e.g. Mars analogs for Jezero) are the real test.
  // The others are listed under them, for information.
  // An analog can stand for several bodies ("Mars, Moon"): it then counts for each of them.
  const sameBody = rows.filter(function (row) { return analogBodies(row.analog).includes(target.body); });
  const otherBody = rows.filter(function (row) { return !analogBodies(row.analog).includes(target.body); });

  // Rule from the pipeline: an analog of this body counts ONLY for the profiles it is really used for
  // (validated_profiles). The others stay in the table, greyed, with "Not used for this profile".
  // An analog whose profiles are not given counts on every profile (the rule before this field existed).
  const missing = sameBody.filter(function (row) { return row.profiles === null; }).length;
  for (const row of sameBody) {
    row.offProfile = row.profiles !== null && !row.profiles.includes(currentProfile);
    // Some analogs have their profiles and some do not: say which ones (when none has them,
    // one sentence under the summary is enough)
    row.profilesMissing = row.profiles === null && missing < sameBody.length;
  }
  // The analogs that count go first (the order by rank is kept inside each group)
  sameBody.sort(function (a, b) { return a.offProfile - b.offProfile; });
  const counted = sameBody.filter(function (row) { return !row.offProfile; });
  const topCount = counted.filter(function (row) { return row.isTop; }).length;
  // "used for rover navigation": only when the file gives the profiles of every analog of this body
  const profile = data.meta.profiles.find(function (p) { return p.id === currentProfile; });
  const profileWords = PROFILE_WORDS[currentProfile] || plainWords(profile.label);
  const usedFor = missing === 0 ? " used for " + profileWords : "";

  // Analogs without a rank do not count in "X of N". Say how many were left out, and why:
  // "vegetated" when the pipeline's note says so, "not scored" otherwise.
  const scored = counted.filter(function (row) { return row.isScored; });
  const unscored = counted.filter(function (row) { return !row.isScored; });
  const vegetated = unscored.filter(function (row) { return row.note && /vegetated/i.test(row.note); }).length;
  const leftOut = [];
  if (vegetated > 0) leftOut.push(vegetated + " excluded: vegetated");
  if (unscored.length - vegetated > 0) leftOut.push((unscored.length - vegetated) + " not scored");

  let html = "<h2>Validation</h2>" + contextLine("Known analogs, scored against");

  if (tilesScored && scored.length > 0) {
    html += '<p class="validation-summary"><span class="num">' + topCount + "</span> of " +
            '<span class="num">' + scored.length + "</span> " + (unscored.length > 0 ? "scored " : "known ") +
            escapeHtml(target.body) + " analogs" + escapeHtml(usedFor) +
            " rank in the top " + TOP_PERCENT + "% of Earth’s barren land" +
            (leftOut.length > 0 ? ' <span class="left-out">(' + leftOut.join(", ") + ")</span>" : "") + ".</p>" +
            // Fallback: the file does not say which profiles some analogs are used for
            (missing === 0 ? "" :
              '<p class="validation-note">Matching profiles not provided' +
              (missing === sameBody.length
                ? ": every " + escapeHtml(target.body) + " analog is counted on all profiles."
                : ' for <span class="num">' + missing + "</span> of them: " +
                  (missing === 1 ? "it is" : "they are") + " counted on all profiles.") + "</p>") +
            // tiles_scored counts barren land only (rule from the pipeline, see CLAUDE.md)
            '<p class="validation-note">Rank among the <span class="num">' + tilesScored.toLocaleString("en-US") +
            "</span> barren-land tiles scored for " + escapeHtml(target.name) +
            '. Vegetated tiles (NDVI <span class="num">&gt; 0.3</span>) are excluded before scoring.</p>';
  } else if (tilesScored && counted.length === 0 && sameBody.length > 0) {
    // Analogs of this body exist, but none is used for the selected profile: nothing to count
    html += '<p class="validation-summary unavailable">No known ' + escapeHtml(target.body) + " analog is used for " +
            escapeHtml(profileWords) + ": nothing to count for this profile.</p>";
  } else {
    // Without the number of tiles scored (or without any scored analog), "top X% of
    // Earth's barren land" cannot be computed: say so calmly instead of a misleading "0 of 9".
    html += '<p class="validation-summary unavailable">Validation data not available for this target yet.</p>';
  }

  html += "<h3>Known " + escapeHtml(target.body) + " analogs</h3>" + validationTable(sameBody);
  if (otherBody.length > 0) {
    html += "<h3>Analogs for other bodies</h3>" + validationTable(otherBody);
  }
  showCard(html, isNewTab);
}

// The HTML of one validation table.
function validationTable(rows) {
  if (rows.length === 0) return '<p class="placeholder">None in the data file.</p>';

  let html = '<table class="validation"><thead><tr>' +
             "<th>Analog</th><th>Score</th><th>Rank</th></tr></thead><tbody>";
  for (const row of rows) {
    const analog = row.analog;
    const canOpen = row.site !== null;

    // Rows with a site on the map are clickable (data-site, like the "Top sites" rows).
    // The others only show their information, also as a tooltip on hover.
    // An analog that is not used for the selected profile is greyed and never highlighted.
    const isTop = row.isTop && !row.offProfile;
    let rowClass = row.offProfile ? "off-profile" : isTop ? "top" : "";
    let rowStart;
    let name;
    if (canOpen) {
      rowStart = '<tr class="' + rowClass + ' clickable" data-site="' + escapeHtml(row.site.id) + '">';
      // A real <button> on the name, so the row also works with the keyboard
      name = '<button type="button" class="row-link">' + escapeHtml(analog.name) + "</button>";
    } else {
      const tooltip = analog.name + (analog.analog_for ? " — known analog for: " + analog.analog_for : "") +
                      (analog.used_for ? " — used for: " + analog.used_for : "");
      rowStart = '<tr class="' + rowClass + '" title="' + escapeHtml(tooltip) + '">';
      name = '<span class="row-link">' + escapeHtml(analog.name) + "</span>";
    }

    html +=
      rowStart +
        "<td>" +
          name +
          (isTop ? '<span class="badge badge-top">Top ' + TOP_PERCENT + "%</span>" : "") +
          (row.offProfile ? '<span class="used-for off-note">Not used for this profile</span>' : "") +
          (row.profilesMissing ? '<span class="used-for">Matching profiles not provided</span>' : "") +
          (analog.used_for ? '<span class="used-for">' + escapeHtml(analog.used_for) + "</span>" : "") +
          (canOpen ? "" : '<span class="used-for">Not among the sites on the map</span>') +
        "</td>" +
        '<td class="num">' + (row.total === null ? "–" : formatScore(row.total)) + "</td>" +
        validationRankCell(row) +
      "</tr>";
  }
  return html + "</tbody></table>";
}

// The last cell of a validation row: "Top 0.8%" + exact rank + the pipeline's note.
// In the bottom half of the ranking (percentile above 50), "Top 82%" would read oddly:
// the cell then says "Lower half" with the exact rank, "#5,363 of 6,514".
function validationRankCell(row) {
  const note = row.note ? '<span class="tile-note">' + escapeHtml(row.note) + "</span>" : "";

  // Not scored: the note takes the place of the rank (or "no data" when there is no note).
  if (!row.isScored) {
    return '<td class="not-scored">' + (note || '<span class="tile-note">no data</span>') + "</td>";
  }
  const rank = "#" + row.globalRank.toLocaleString("en-US");
  let headline;       // first line of the cell
  let exactRank;      // second line, smaller
  if (row.percentile === null) {
    headline = '<span class="of">no data</span>';
    exactRank = rank;
  } else if (row.percentile > 50) {
    headline = "Lower half";
    exactRank = rank + " of " + row.tilesScored.toLocaleString("en-US");
  } else {
    headline = "Top " + escapeHtml(formatPercent(row.percentile)) + "%";
    exactRank = rank;
  }
  return '<td class="num">' +
           headline +
           '<span class="of">' + exactRank + "</span>" +
           note +      // scored, with a remark (e.g. "nearest valid tile, 12 km away"): small, under the rank
         "</td>";
}

// ---- Tabs and clicks inside the panel ----

// The three tabs reuse the segmented control of the top bar (fillSegmented in app.js).
fillSegmented(
  document.getElementById("panel-tabs"),
  "panel-tab",
  [
    { id: "site", label: "Site" },
    { id: "top", label: "Top sites" },
    { id: "validation", label: "Validation" },
  ],
  function (tabId) {
    currentTab = tabId;
    if (data) renderPanel();     // nothing to draw before the data file is loaded
  }
);

// One click listener for the whole panel: it looks at what was clicked.
document.getElementById("panel-content").addEventListener("click", function (event) {
  // A row of the "Top sites" list, or a row of the "Validation" table whose analog
  // has a site on the map: fly there and open its card.
  // (Validation rows without a site have no data-site: clicking them does nothing.)
  const siteRow = event.target.closest("[data-site]");
  if (siteRow) openSite(siteRow.dataset.site, true);

  // The "All sites" / "Hidden gems" buttons of the "Top sites" tab.
  const filterButton = event.target.closest("[data-filter]");
  if (filterButton) {
    topGemsOnly = filterButton.dataset.filter === "gems";
    renderPanel();
  }
});

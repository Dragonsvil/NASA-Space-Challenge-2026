// Planetary Analog Finder — side panel
// Three tabs: "Site" (card of the clicked site), "Top sites" (top 10) and
// "Validation" (do the known analogs come out with a high rank?).
// Uses the variables and helpers of app.js: data, currentTarget, currentProfile,
// selectedSiteId, scoreColor(), cssColor(), escapeHtml(), siteName(), formatCoords(),
// analogBodies(), getRanking(), flyToVisibleCenter(), fillSegmented(), moveThumb(), renderRing().

// A dimension scoring below this is listed in "Where the analogy breaks".
const BREAK_THRESHOLD = 40;

// Plain words for each dimension, used to build the "Works for…" sentence.
// If the pipeline adds a new dimension, its label from the data file is used instead.
const DIMENSION_WORDS = {
  temp_range: "day–night temperature swings",
  temp_min:   "minimum temperatures",
  albedo:     "surface brightness (albedo)",
  slope:      "slopes",
  roughness:  "terrain roughness",
  mafic:      "basaltic rock",
  aridity:    "dryness",
  dust:       "dust levels",
  sun_angle:  "low sun angles",
};

// What each mission profile tests, used in the "Works for…" sentence.
const PROFILE_WORDS = {
  rover:   "rover navigation",
  geology: "geology and science work",
  polar:   "polar and thermal operations",
};

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

// Where the target value of one dimension comes from (targets[target].sources), or null.
function getSource(target, dimId) {
  const source = target.sources ? target.sources[dimId] : null;
  return typeof source === "string" && source !== "" ? source : null;
}

// One row per dimension used by the selected target, with everything the card needs.
function getDimensionRows(site, target, profileScores) {
  const rows = [];
  for (const dimId of target.dims) {
    // Label and unit come from meta.dimensions
    const info = data.meta.dimensions.find(function (d) { return d.id === dimId; })
              || { id: dimId, label: dimId, unit: "" };
    const score = profileScores.dims ? profileScores.dims[dimId] : null;
    rows.push({
      id: dimId,
      label: info.label,
      unit: info.unit,
      score: score == null ? null : score,              // 0–100, or null
      siteValue: site.values ? site.values[dimId] : null,
      targetValue: target.values ? target.values[dimId] : null,
      source: getSource(target, dimId),                 // where the target value comes from, or null
    });
  }
  return rows;
}

// ---- The panel ----

// Draw the tab that is selected. Called on every click on a site or a tab,
// and every time the target or profile changes.
function renderPanel() {
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
  if (fly) flyToVisibleCenter(site.lat, site.lon);
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
    panel.innerHTML = '<p class="placeholder">Click a site on the map to see its details.</p>';
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
  let badges = "";
  if (site.hidden_gem) badges += '<span class="badge badge-gem">★ Hidden gem</span>';
  if (site.known_analog) {
    badges += '<span class="badge badge-known">◇ Known analog: ' + escapeHtml(site.known_analog) + "</span>";
  }

  const hasScore = profileScores && profileScores.total != null;
  let html =
    '<div class="site-header">' +
      "<div>" +
        "<h2>" + escapeHtml(siteName(site)) + "</h2>" +
        '<div class="coords num">' + formatCoords(site.lat, site.lon) + "</div>" +
        '<div class="badges">' + badges + "</div>" +
      "</div>" +
      '<div class="big-score' + (hasScore ? "" : " no-score") + '">' +
        (hasScore ? profileScores.total : "–") + "<small>/ 100</small>" +
      "</div>" +
    "</div>" +
    '<p class="context">Compared to <b>' + escapeHtml(target.name) + "</b> (" + escapeHtml(target.body) +
    ") — " + escapeHtml(profile.label) + "</p>";

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
  html += '<div class="radar-box"><canvas id="radar"></canvas></div>';

  // ---- 3) Dimension list: label, score bar, real value vs target value ----
  html += "<h3>Dimensions</h3>";
  for (const row of rows) {
    const hasDimScore = row.score != null;
    html +=
      '<div class="dim">' +
        '<div class="dim-top">' +
          "<span>" + escapeHtml(row.label) + "</span>" +
          '<span class="dim-score num' + (hasDimScore ? "" : " no-data") + '">' + (hasDimScore ? row.score : "no data") + "</span>" +
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

  // ---- 4) "Works for…": the 2 best dimensions, as a sentence ----
  const best = rows
    .filter(function (row) { return row.score != null; })
    .sort(function (a, b) { return b.score - a.score; })
    .slice(0, 2);

  html += "<h3>Works for…</h3>";
  if (best.length === 0) {
    html += '<p class="placeholder">No dimension score available for this site.</p>';
  } else {
    const words = best.map(function (row) { return DIMENSION_WORDS[row.id] || row.label.toLowerCase(); });
    const scores = best.map(function (row) { return row.score; });
    const activity = PROFILE_WORDS[profile.id] || profile.label.toLowerCase();
    html += '<p class="works">Good for testing ' + escapeHtml(activity) + " with " +
            escapeHtml(words.join(" and ")) + " similar to " + escapeHtml(target.name) +
            " (" + (best.length === 2 ? "scores " : "score ") +
            scores.map(function (score) { return '<span class="num">' + score + "</span>"; }).join(" and ") + ").</p>";
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
              escapeHtml(formatValue(row.targetValue, row.unit)) + "</span> at " + escapeHtml(target.name) +
              ' (score <span class="num">' + row.score + "</span>).</li>";
    }
  }
  html += "</ul></div>";

  // ---- 6) Sources of the target values (only the dimensions that have one) ----
  const sourced = rows.filter(function (row) { return row.source; });
  if (sourced.length > 0) {
    html += "<h3>Sources</h3>" +
            '<p class="sources-intro">Where the ' + escapeHtml(target.name) + " values come from.</p>" +
            '<dl class="sources">';
    for (const row of sourced) {
      html += "<dt>" + escapeHtml(row.label) + "</dt><dd>" + escapeHtml(row.source) + "</dd>";
    }
    html += "</dl>";
  }

  showCard(html, isNewSite);

  // Slide every score bar to its score (the CSS transition does the animation).
  // Reading offsetWidth first makes the browser draw the start position.
  for (const bar of panel.querySelectorAll(".bar-fill")) {
    bar.offsetWidth;
    bar.style.transform = "scaleX(" + bar.dataset.score / 100 + ")";
  }

  drawRadar(rows, target);
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
  const top = getRanking().slice(0, TOP_COUNT);

  let html = "<h2>Top " + TOP_COUNT + " sites</h2>" + contextLine("Closest to");

  if (top.length === 0) {
    html += '<p class="placeholder">No site has a score for this target and mission profile.</p>';
    showCard(html, isNewTab);
    return;
  }

  html += '<ol class="rank-list">';
  for (const entry of top) {
    const site = entry.site;
    let marks = "";
    if (site.hidden_gem) marks += '<span class="badge badge-gem">★ Hidden gem</span>';
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
          '<span class="rank-score num">' + entry.total + "</span>" +
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
      isTop: percentile !== null && percentile <= TOP_PERCENT,
      site: findAnalogSite(analog),                             // null = no site card to open
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
  const topCount = sameBody.filter(function (row) { return row.isTop; }).length;

  // Analogs without a rank do not count in "X of N". Say how many were left out, and why:
  // "vegetated" when the pipeline's note says so, "not scored" otherwise.
  const scored = sameBody.filter(function (row) { return row.isScored; });
  const unscored = sameBody.filter(function (row) { return !row.isScored; });
  const vegetated = unscored.filter(function (row) { return row.note && /vegetated/i.test(row.note); }).length;
  const leftOut = [];
  if (vegetated > 0) leftOut.push(vegetated + " excluded: vegetated");
  if (unscored.length - vegetated > 0) leftOut.push((unscored.length - vegetated) + " not scored");

  let html = "<h2>Validation</h2>" + contextLine("Known analogs, scored against");

  if (tilesScored && scored.length > 0) {
    html += '<p class="validation-summary"><span class="num">' + topCount + "</span> of " +
            '<span class="num">' + scored.length + "</span> " + (unscored.length > 0 ? "scored " : "known ") +
            escapeHtml(target.body) + " analogs rank in the top " + TOP_PERCENT + "% of Earth’s barren land" +
            (leftOut.length > 0 ? ' <span class="left-out">(' + leftOut.join(", ") + ")</span>" : "") + ".</p>" +
            // tiles_scored counts barren land only (rule from the pipeline, see CLAUDE.md)
            '<p class="validation-note">Rank among the <span class="num">' + tilesScored.toLocaleString("en-US") +
            "</span> barren-land tiles scored for " + escapeHtml(target.name) +
            '. Vegetated tiles (NDVI <span class="num">&gt; 0.3</span>) are excluded before scoring.</p>';
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
    let rowClass = row.isTop ? "top" : "";
    let rowStart;
    let name;
    if (canOpen) {
      rowStart = '<tr class="' + rowClass + ' clickable" data-site="' + escapeHtml(row.site.id) + '">';
      // A real <button> on the name, so the row also works with the keyboard
      name = '<button type="button" class="row-link">' + escapeHtml(analog.name) + "</button>";
    } else {
      const tooltip = analog.name + " — known analog for: " + analog.analog_for + " — used for: " + analog.used_for;
      rowStart = '<tr class="' + rowClass + '" title="' + escapeHtml(tooltip) + '">';
      name = '<span class="row-link">' + escapeHtml(analog.name) + "</span>";
    }

    html +=
      rowStart +
        "<td>" +
          name +
          (row.isTop ? '<span class="badge badge-top">Top ' + TOP_PERCENT + "%</span>" : "") +
          '<span class="used-for">' + escapeHtml(analog.used_for) + "</span>" +
          (canOpen ? "" : '<span class="used-for">Not among the sites on the map</span>') +
        "</td>" +
        '<td class="num">' + (row.total === null ? "–" : row.total) + "</td>" +
        validationRankCell(row) +
      "</tr>";
  }
  return html + "</tbody></table>";
}

// The last cell of a validation row: "Top 0.8%" + exact rank + the pipeline's note.
function validationRankCell(row) {
  const note = row.note ? '<span class="tile-note">' + escapeHtml(row.note) + "</span>" : "";

  // Not scored: the note takes the place of the rank (or "no data" when there is no note).
  if (!row.isScored) {
    return '<td class="not-scored">' + (note || '<span class="tile-note">no data</span>') + "</td>";
  }
  return '<td class="num">' +
           (row.percentile === null ? '<span class="of">no data</span>' : "Top " + formatPercent(row.percentile) + "%") +
           '<span class="of">#' + row.globalRank.toLocaleString("en-US") + "</span>" +
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
});

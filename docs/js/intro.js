// Planetary Analog Finder — intro screen
// The intro (<section id="intro"> in index.html) covers the site on every visit.
// It goes away with the "Explore the map" button or the Escape key.
// Add #map to the address (…/index.html#map) to skip it, e.g. for the demo video.
// This file is loaded right after the intro's HTML, so a skipped intro never flashes.

(function () {
  const intro = document.getElementById("intro");
  // What sits behind the intro: the top bar and the map + panel
  const behind = [document.getElementById("topbar"), document.querySelector("main")];

  // Skip: remove the intro before it is ever drawn
  if (location.hash === "#map") {
    intro.remove();
    return;
  }

  // While the intro is open, the Tab key must not reach the controls hidden behind it
  behind.forEach(function (el) { el.inert = true; });

  function closeIntro() {
    if (intro.classList.contains("leaving")) return;      // already closing
    behind.forEach(function (el) { el.inert = false; });
    document.removeEventListener("keydown", onKey);
    intro.classList.add("leaving");                        // CSS fades it out (260ms)…
    setTimeout(function () { intro.remove(); }, 300);      // …then it is removed
    // Orbi (js/orbi.js) says hello, then docks into his button above the legend.
    // (When the intro is skipped with #map there is no greeting: app.js only shows the button.)
    if (window.Orbi) Orbi.greet();
  }

  function onKey(event) {
    if (event.key === "Escape") closeIntro();
  }

  document.getElementById("intro-explore").addEventListener("click", closeIntro);
  document.addEventListener("keydown", onKey);
})();

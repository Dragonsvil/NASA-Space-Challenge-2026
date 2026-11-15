# vendor/ — libraries copied into the site

The site loads these files from here, not from a CDN: during the tests the CDNs dropped several times,
and the live demo must not depend on them. Do not edit these files.

| Library | Version | Files | Copied from | License |
|---|---|---|---|---|
| Leaflet (map) | 1.9.4 | `leaflet/leaflet.js`, `leaflet/leaflet.css`, `leaflet/images/` | `https://unpkg.com/leaflet@1.9.4/dist/` | BSD 2-Clause, (c) 2010-2023 Vladimir Agafonkin, (c) 2010-2011 CloudMade |
| Chart.js (radar chart) | 4.4.1 | `chart.umd.min.js` | `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js` | MIT, (c) Chart.js contributors |

The files are byte-for-byte the ones the site used to load from the CDN (same integrity hashes):

- `leaflet/leaflet.js`  sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=
- `leaflet/leaflet.css` sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=
- `chart.umd.min.js`    sha384-9nhczxUqK87bcKHh20fSQcTGD4qq5GhayNYSYWqwBkINBhOfQLg/P5HG5lF1urn4

`leaflet/images/` must stay next to `leaflet.css`: the layers button takes its icon from there.

Still loaded from the internet: the map background tiles (NASA GIBS and the other base maps), the IBM Plex
fonts (Google Fonts; without them the site uses the system fonts) and Orbi's AI relay.

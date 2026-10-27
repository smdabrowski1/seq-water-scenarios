# Walkthrough media

Four clips of the live dashboard, used on the portfolio site's SEQ Water
Security walkthrough page. Captured headless via Playwright
(`mcr.microsoft.com/playwright:v1.47.0-jammy`) against the running app, then
encoded to MP4 (h264) with `jrottenberg/ffmpeg:6-alpine` — both steps run as
one-off Docker containers, no host-installed browser or ffmpeg needed to
re-capture.

- `01-hero-drag.mp4` — dragging across the grid storage trend to read an
  exact date's value.
- `02-map-dams.mp4` — picking Baroon Pocket, Hinze, then Little Nerang from
  the dam dropdown, each one panning the map to its own shape.
- `03-scenario-trajectory.mp4` — hovering the grid storage trajectory under
  the Millennium Drought repeat scenario.
- `04-scenario-balance.mp4` — clicking a year's breakdown, then switching
  the Logan River investment on and watching the yield line clear demand.

The on-screen cursor and click rings are drawn by an injected script
mirroring real `mousemove`/`mousedown` events, since headless Chromium
renders no OS pointer of its own. Native `<select>` dropdowns are OS-level
chrome headless Chromium never paints into the page, so the dam picker is a
styled stand-in list drawn at click time (real DOM, real click target)
purely for the recording — the actual selection still goes through the real
control underneath.

These are the canonical source files; the portfolio site keeps its own
served copy under `frontend/public/media/seqwater/`.

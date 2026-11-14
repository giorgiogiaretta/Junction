# Junction pitch deck

Open `index.html` directly in a modern browser. No server, network, fonts, libraries or API keys are needed. The repository comparison image is embedded as a data URI, so the HTML can be copied on its own.

- Next: right/down arrow, Page Down, Space, slide click, or the → button.
- Previous: left/up arrow, Page Up, or the ← button.
- Home / End: first / last slide. A URL fragment such as `#5` opens a specific slide.
- `T` or **Light / dark** switches theme. Tab reaches the controls; Enter activates them.
- **Print / PDF** opens the browser print dialog. All slides print, regardless of the active slide.

## Export PDF

Choose the desired theme, then Print / PDF → Save as PDF. Use the CSS-defined landscape page size (16:9), margins **None**, scale **100%**, and disable browser headers and footers. Enable background graphics to preserve the selected theme. The stylesheet defines a 1280 × 720 CSS-pixel page (13⅓ × 7½ inches), with one slide per page. Preview should show ten pages. Do not force A4/Letter if exact 16:9 is required.

## Delivery and evidence

`notes.md` includes a 20–25-second full note for every slide and shorter Core paragraphs for a three-minute delivery. Ten full notes exceed three minutes; rehearse the Core route at roughly 18 seconds per slide.

Source paths appear on every slide and in the notes. They refer to files in the repository; no linked source is fetched at runtime. The image comes unchanged from `docs/media/g1_egg_cap_vs_nocap.jpg`. Its embedded force annotations are explicitly labelled toy simulation outputs.

The older `docs/ORCH_BACKLOG.md` and submission drafts predate `robot/e2e_g1.py` and the current cap policy in `ai/object_profile.py`. The deck acknowledges that bridge code exists, without claiming a newly verified photo-to-grasp run. The shared 0.70 cap supersedes the ball-specific recommendation in the older grasp report. Gemini live performance, a working Gemma recogniser, a live fragile-first ensemble, real head tracking and real G1 grasp performance remain unproven in the cited evidence. The business model is a proposal.

Recognition counts use `docs/OBJECT_RECOGNITION_RESULTS.md`; `docs/CV_RESULTS.md` contains a separate YOLO-World baseline rather than a newer Nemotron evaluation. No recognition experiment was rerun for this deck.

## Local validation

- Headless Chrome: keyboard and click navigation, theme switching, ten slides, no content/footer overlap, no JavaScript errors and no HTTP(S) requests passed.
- Dark and light PDF exports: ten pages each, 960 × 540 points (16:9). Dark slide contact sheet and light cover visually inspected.
- Required `python3 -m pytest tests -q`: blocked because the default Python has no `pytest`. Retried with the existing `/private/tmp/junction-codex-check` environment: collection stopped because `cv2` is missing (`tests/test_vision.py`); one test module skipped. The full suite is **not verified green**. No dependencies were downloaded.
- Simulation and remote recognition were not rerun. Browser export checks establish presentation behaviour, not robot performance.

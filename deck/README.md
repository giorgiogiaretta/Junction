# Junction pitch deck

Open `index.html` directly in a browser. The HTML is an offline, self-contained file: inline styles and script, no external fonts, images, libraries or services. Copying the HTML alone preserves the presentation. The real-robot slide intentionally contains **video: to add**; no clip is attached.

- Next: right/down arrow, Page Down, Space, slide click, or →.
- Previous: left/up arrow, Page Up, or ←.
- Home / End: first / last slide. A fragment such as `#3` opens that slide.
- `T` or **Light / dark** switches theme. Tab reaches the controls.
- **Print / PDF** prints all slides, regardless of the active slide.

## Timing and PDF

There are twelve slides. `notes.md` supplies a **Core** route for roughly three minutes (about 420 spoken words), plus **Detail** to make each full note about twenty to twenty-five seconds at a brisk delivery. Full notes take about four to five minutes. These are rehearsal estimates: twelve full twenty-second notes cannot fit three minutes. Rehearse Core only for the short slot.

For PDF, choose the theme, then **Print / PDF → Save as PDF**. Use the CSS page size, no margins, scale 100%, background graphics enabled and browser headers/footers disabled. Expect twelve landscape pages, 960 × 540 points (16:9). Do not force A4/Letter.

## Evidence and source conflicts

Each slide carries repository source paths, also listed in its speaker note. These are citations, not runtime fetches. Content was reviewed against main at `3e71908`.

- Hardware: `tools/g1_windows_runner/README.md` documents Giorgio's real-G1 glove-driven arms and hands, two runs of 120 seconds, 29.8 commands per second and zero safety-filter clips. The camera computer was off. No vision-assisted physical object grasp is demonstrated. `docs/G1_GUIDE.md` and `docs/G1_LIVE.md` retain limits/plans; their mock results are not used as physical evidence.
- The scorecard predates the hardware report. The final table updates only teleoperation and retains the scorecard's recognition, grasp, calibration, can-holding and validation limits. `docs/SCORECARD.md` itself is outside this worker's scope and remains unchanged.
- `docs/STORY_MODELS.md` contains optimistic earlier wording. The later correction in `docs/VERDA_GEMMA.md` and the result tables identify **PaliGemma 2 on the team-controlled remote GPU**, versus **Gemma 4 through Google's API**. Self-hosted does not mean laptop-offline. Nemotron is not uniquely fast.
- The three recognisers in the offline vote are Nemotron, API Gemma and PaliGemma. Gemini is the separate asynchronous episode judge, with quality still unvalidated. The updated `ai/recognize.py` counts distinct model families for the two-key gate: Gemma and PaliGemma count as one key. The older scorecard/tour caveat about backend counts is superseded by that change.
- Recognition uses the same small photo set, no held-out data. The result tables are reported evidence, not fresh inference in this task. Confidence is not calibrated. Physical thresholds are toy assumptions.
- The Advisor is explicitly experimental. Model mass/size/fragility estimates are not measurements and the initial photo examples are not a quality evaluation.

## Offline claim checker

From the repo root:

```bash
python3 deck/check_deck.py
```

The standard-library script checks audience copy in `index.html` and `notes.md`. It rejects forbidden wording, numeric force claims, missing source files, external resource/link references and numeric tokens absent from text documents under `docs/`. It also requires twelve cited slides. Ratios and percentages remain whole, and decimal comma/trailing-zero variants compare equally. No service, key or package install is needed.

CSS/JS constants, navigation, source-path footers and slide counters are structural and excluded. README validation metadata is also outside the claim corpus. Digit-bearing identifiers such as G1 and Dex3 are not treated as numeric measurements. Spelled-out numbers and the meaning of a claim require human review. A number appearing somewhere in `docs/` does **not** establish its units, context, applicability or truth; source review remains mandatory. Hardware claims are manually traced to the Windows runner report, even where their numeric tokens also occur in docs about mock runs.

Optional `--html`, `--notes` and `--docs` arguments allow checking temporary fixtures. Mutation checks verified rejection of a forbidden phrase split across HTML tags, an unqualified percentage overclaim, a Newton measurement claim, an unseen integer followed by a sentence period, and an unseen ratio.

## Validation for this revision

- `python3 deck/check_deck.py`: passed, including the negative mutation checks described above.
- Default `python3 -m pytest tests -q`: could not start because that interpreter lacks pytest.
- `PATH=/opt/anaconda3/bin:$PATH python3 -m pytest tests -q`: **268 passed, 5 skipped in 34.00 s**, using existing dependencies. Skips do not establish experiment coverage.
- Headless installed Chrome: twelve slides in both themes, content/footer fit, keyboard/button/click navigation, theme toggle, resize, no JavaScript errors and no external page requests. HTTP(S) page requests were blocked during verification.
- Both PDF exports: twelve pages, 960 × 540 points. All slides visually reviewed in dark and light contact sheets. Exports/screenshots are temporary validation artifacts, not committed assets.
- No inference endpoint, physical robot, new photo evaluation or force calibration was run. PR CI is separate from these local checks.

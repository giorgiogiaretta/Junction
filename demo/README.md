# Demo

One command: `demo/run_demo.sh` (mock stream) or `demo/run_demo.sh --real --backend serial --dev /dev/ttyACM0`.
Flow: glove/Rokoko Studio -> UDP 14043 -> `fanout.py` -> dashboard (14044) + robot hand (14045).
Needs `pip install -r demo/requirements.txt -r robot/requirements.txt`. Backends: `dry`, `sim`, `serial`, `pca9685`.
Note: `--backend sim` opens no viewer through run_udp; use `mjpython -m robot.sim` separately for visuals.

## Pitch flow (3 min)
1. Problem: robots learn from human demonstrations, but gathering them is slow and expensive.
2. Live: put on the glove, open/close the hand; dashboard shows fingers, recognised gesture, latency (ms) and fps; the robot hand mirrors it.
3. Show a gesture (point, peace, fist) -> label changes -> same stream can trigger robot commands.
4. Record: same stream saved as dataset (Rokoko/src/listen.py --out) -> train a policy (ml/).
5. Business model: sell a glove + capture kit as a data-collection service for robotics teams (pay per demo hour / dataset licence).
6. Close: next steps (remote teleop over the internet, more hand sensors).

## Offline QC pitch page

Open `demo/results.html` directly. It has no external assets or network calls and
uses the system light/dark preference. The committed snapshot contains no QC data.

To embed existing `data/qc/*.json` reports in the single HTML file:

```sh
python3 demo/build_results.py
```

Alternatively select local JSON files in the page. The browser cannot enumerate
`data/qc/` from a `file://` page, so bundling is the reproducible offline path.
Do not commit embedded private reports or raw data. To restore the empty snapshot,
bundle from an empty directory using `--source /path/to/empty-directory`.

Provisional import contract (not yet the ML producer contract): one take object,
an array, or `{"takes": [...]}` per JSON file. Each take needs a unique string
`take_id`, numeric `score` (0–100), `decision` (`keep` or `discard`), and non-empty
`reason`. Optional string fields: `series`, `hand`. Invalid entries and duplicate
IDs are surfaced in the page and excluded from the card. No score thresholds or
missing metrics are invented. Loading files replaces the current review session.

Human keep/discard overrides require a reason for export. The downloaded
`qc-review.json` preserves the original reports and separates overrides from
producer recommendations. It is a review artifact, not a QC input file. Reviews
are in memory until exported; source recordings and report files are untouched.

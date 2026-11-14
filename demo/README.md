# Demo

One command: `demo/run_demo.sh` (mock stream) or `demo/run_demo.sh --real --backend serial --dev /dev/ttyACM0`.
Flow: glove/Rokoko Studio -> UDP 14043 -> `fanout.py` -> dashboard (14044) + robot hand (14045).
Needs `pip install -r demo/requirements.txt -r robot/requirements.txt`. Backends: `dry`, `sim`, `serial`, `pca9685`.
Note: `--backend sim` opens no viewer through run_udp; use `mjpython -m robot.sim` separately for visuals.

## Projector mode

Open `demo/results.html` in a browser for the offline G1 egg comparison and
recognizer results. The comparison embeds the repository JPEG and labels its
contact forces as simulation outputs.

Run `demo/run_demo.sh --present --assist egg` to show the mock stream and live
simulation telemetry fullscreen. Press F11 to toggle fullscreen or Esc to leave it.
The live bar shows current and peak simulated contact force. The profile and closure
cap come from the same UDP telemetry and disappear when telemetry goes stale.

Click **Stato rete/endpoint** to check whether the configured endpoint responds
to an unauthenticated `GET /models`. Green means HTTP 2xx or an authentication
response (401/403). Red means the check failed. The check does not run inference
or send a frame or a key. It uses `LLM_BASE_URL` when set and Verda otherwise.

To pick a Force Cushion profile once at startup, set `FRAME` to a head-camera image.
If `HX`, `HY` and `HZ` are all set, the picker uses the hand position in the head
frame (metres) to crop the image. If any coordinate is missing, it uses the full frame.

```sh
FRAME="head camera.jpg" HX=0.05 HY=0.10 HZ=0.45 demo/run_demo.sh --auto-profile
FRAME="head camera.jpg" demo/run_demo.sh --auto-profile
```

The picker publishes on local UDP 14070. The demo forwards the update to both the
simulator and the hand process. The dashboard displays the simulator's active
profile and closure cap. The picker uses its built-in fallback offline.

## Pitch flow (3 min)
1. Problem: robots learn from human demonstrations, but gathering them is slow and expensive.
2. Live: put on the glove, open/close the hand; dashboard shows fingers, recognised gesture, latency (ms) and fps; the robot hand mirrors it.
3. Show a gesture (point, peace, fist) -> label changes -> same stream can trigger robot commands.
4. Record: same stream saved as dataset (Rokoko/src/listen.py --out) -> train a policy (ml/).
5. Business model: sell a glove + capture kit as a data-collection service for robotics teams (pay per demo hour / dataset licence).
6. Close: next steps (remote teleop over the internet, more hand sensors).

## Offline QC pitch page

Open `demo/results.html` directly. It has no external assets or network calls and
uses a dark theme for projection. The committed snapshot contains no QC data.

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

# Aaltonomous Humanoid: 2-hour time-boxed spike (plan only)

*Tommaso's Aalto-Orchestrator, 2026-11-14, branch `aalto/spike`. No application code in this commit. No keys or tokens
in any file: secrets go through interactive logins (`huggingface-cli login`, `gh auth`) or shell env on the box only.*

Sources read: the challenge brief, `docs/AALTONOMOUS_FEASIBILITY.md`, Giorgio's board answers (2026-11-14 20:16Z),
and from `zupermiez/aaltonomous-humanoid` (main): `aaltonomous/cloud/{QUICKSTART.md,setup_instance.sh,aalto.sh}`,
`docs/participants/{README,RULES_AND_SCORING,FAQ,SUBMISSION}.md`, `data/DATA_CARD.md`,
`baselines/classical/{policy.py,config.yaml}`, `interface/tasks.py`.

## 0. Where we start (facts, not hopes)

- **The robot already moved for us**, but in the Rokoko track: Giorgio ran the organisers' runner against the real
  G1 (branch `g1-real-working`, `g1/arms_simple.py`, 2 x 120 s, 29.8 Hz, 0 safety clips). In THIS track the rules
  say nobody touches the robot: the organisers run our Docker image, and only the **top ~5 by sim score** get real
  runs on Sunday. So the real-robot work proves the plumbing and the safety traps; it is not a shortcut to the finals.
- **A real dataset is about to arrive** (Drop 0 / Drop 1: LeRobot v3.0 + GR00T copy, head RGB-D + 2 wrist RGB,
  `observation.state` 28, `action` 28, per-episode labels and object layouts in `meta/aalto_episodes.jsonl`).
  Links come on the Junction Discord, not on HF search.
- **The organisers ship a classical baseline** (`baselines/classical/`): HSV + depth, top-down claw grasp with IK,
  plans pre-checked against the safety filter. Sim rung 1: 76-82 % of objects sorted, 0 clips, 30 Hz.
  It **ignores the instruction**: `policy.reset()` takes `info["mapping"]` or falls back to `FIXED_MAPPING`.
- **Scoring lever:** rung 2 pays +2 per correct object (rung 1: +1), and 2 of the 3 finals episodes are rung 2
  (the unseen instruction weighs x1.5). An offline instruction -> mapping parser plugged into the baseline is the
  cheapest real gain. Network at the finals is not guaranteed: the parser must work with no API.
- **GPU:** our Verda A100 cannot run the sim (no RT cores). We need an RTX-class on-demand instance (RTX Pro 6000,
  L40S, A6000, RTX 4090/5090, >= 24 GB) with a persistent volume. That is new spend: Tommaso approves it.

## 1. Isaac Sim + `aalto eval` on a Verda RTX instance

Owner: **Codex-Setup** (`aalto/setup/`: scripts and a log of what actually happened, timings included).
Human step: Tommaso creates the instance (money) and gets the `aalto-sim:v1` image link from Discord.

1. **Instance** (Tommaso, Verda console): on-demand, NOT spot; RTX-class >= 24 GB; Ubuntu 22.04/24.04 x86_64;
   >= 8 vCPU, >= 32 GB RAM, >= 80 GB disk; attach a persistent block volume, mount at `/data`.
2. **Host checks** (SSH, inside `tmux`):
   - `nvidia-smi`: driver **>= 580.65.06**; GPU not A100/H100.
   - `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi` works. If it fails with
     `could not select device driver`: install `nvidia-container-toolkit` (QUICKSTART §2 gives the 3 commands; needs sudo).
3. **Docker path (preferred, ~15 min + 5-10 min first shader compile):**
   ```bash
   docker load -i /data/aalto-sim-v1.tar.zst      # or docker pull <registry from Discord>/aalto-sim:v1
   docker run -d --name aalto --gpus all --network host --ipc host \
     -v aalto-kitcache:/root/miniforge3/envs/isaac/lib/python3.12/site-packages/isaacsim/kit/cache \
     -v /data:/data aalto-sim:v1 sleep infinity
   docker exec -it aalto bash
   aalto sim        # returns when the scene service answers; log /tmp/aalto_sim.log
   aalto check      # expect 8 PASS / 0 FAIL
   aalto snap       # one JPEG per camera in /tmp/aalto_snap; mean ~0 = shader cache still cold, wait
   aalto baseline   # oracle, rung 1, 3 trials (~75 s each)
   ```
4. **Bare-metal fallback (~30-40 min, no sudo except one apt line):** get the repo (`git clone` the public repo
   into `/data/aaltonomous-humanoid`), then `bash aaltonomous/cloud/setup_instance.sh` (steps: prereq, conda,
   torch cu130, isaacsim 6.2 incl. the 10.5 GB ext cache, IsaacLab v3.0 pinned, CycloneDDS 0.10.x build,
   unitree repos, USD assets from HF, msgpack/websockets, verify). Re-running resumes. Install on `/data` so a dead
   instance does not cost the install. Then `bash aaltonomous/cloud/aalto.sh sim|check|snap|baseline`.
5. **Our policy server through the real evaluator** (the gate the organisers use):
   - start the server on the host (`--network host` shares port 8000), or as an image:
     `docker run -d --gpus all -p 8000:8000 <our-image>` (no docker CLI inside the sim container);
   - pre-checks: `python -m aaltonomous.deploy.replay --synthetic 100 --policy ws://localhost:8000` (exit 0);
   - inside the container: `aalto eval --policy ws://localhost:8000 --team <team> --task sort_fixed --trials 3`,
     then `--task sort_language --trials 3`. Exit 0 = gate passed, 2 = failed; read
     `runs/eval/<...>/eval.json` and every clip reason in `runs/<team>/<run>/episode_NNN.jsonl`.
6. **Rules of the box:** one sim per instance (CPU starvation breaks the 27 Hz gate); never `pkill -f sim_main`
   (use `aalto stop`); results and logs copied to `/data`; stop the instance when idle (billing).

## 2. Backlog with owners

Ownership: `aalto/` is a new folder. At GO, add one row to the AGENTS.md table (Tommaso's agents) and post the
claim on the board. Codex's current rules allow only `demo/` and `docs/PITCH*.md`: Tommaso must widen them to
`aalto/setup|data|policy/` for this track, or Claude does those parts.

| # | Owner | Folder | Task | Done when |
|---|---|---|---|---|
| S1 | Codex-Setup | `aalto/setup/` | Section 1 steps 2-4 as a checked runbook + `verify.sh` that prints driver, GPU, `aalto check` result | `aalto check` 8 PASS, `aalto baseline` 3 trials run, log committed |
| S2 | Codex-Setup | `aalto/setup/` | Build the organisers' `baseline.Dockerfile` unchanged; run step 5 on it | baseline image passes the gate on 3 sort_fixed trials (0 clips, >= 27 Hz, `policy_hz_rt` >= 27) |
| S3 | Codex-Setup | `aalto/setup/` | Persistence: everything on `/data`, a one-page "resume on a new instance" note | a fresh instance gets back to `aalto check` from `/data` in < 15 min |
| D1 | Codex-Data | `aalto/data/` | Download the drop (link from Discord, HF login interactive), load with `lerobot==0.7.0`, table per episode: success, rung, warnings, depth health | `aalto/data/REPORT.md` with counts; raw data stays OUT of git (`data/` is untracked) |
| D2 | Codex-Data | `aalto/data/` | Filter: success = true, no safety warnings, depth `valid_frac_mean` above a threshold; export the episode list | a JSON list of usable episodes + reasons for every rejected one |
| D3 | Codex-Data | `aalto/data/` | **Real2sim check of perception:** run the baseline's `perception.py` on real head RGB-D frames (first frame of each usable episode) and compare with the object layout in `aalto_episodes.jsonl` | detection rate and position error per colour/shape on REAL frames (the held-out variant and the finals are where the baseline breaks) |
| P1 | Codex-Policy | `aalto/policy/` | Policy server = the organisers' classical baseline + our mapping from the instruction (P1 calls S-parser below in `reset()`, passes `mapping`) | mock runner 2 episodes, 0 clips; replay --synthetic exit 0 |
| P2 | Codex-Policy | `aalto/policy/` | Safety wrapper on every target: clamp into the filter range, cap arm 1.0 rad/s and hand 3.0 rad/s per tick, first move straight up out of the counter keep-out (Giorgio's traps a, b) | unit test: rest pose with fingers past limits and wrists in keep-out gives 0 clips on mock |
| P3 | Codex-Policy | `aalto/policy/` | Docker image from `submission.Dockerfile` (CUDA >= 12.8, linux/amd64, no download at start, < 120 s startup) | `replay --synthetic 100 --container <image>` exit 0 |
| L1 | Claude Sonnet | `ai/` | **Instruction -> mapping parser, in words to code later:** deterministic rules first (colour words incl. synonyms, bin words left/center/middle/right + paraphrases, "the rest"/"everything else", negations rare), LLM only as an optional second opinion behind a timeout, never required | function `parse_instruction(text) -> {"red": "left", ...}` or `None` (fallback = FIXED_MAPPING) |
| L2 | Claude Sonnet | `ai/` | Test set: the 8 training `TEMPLATES` with all colour/bin permutations + >= 40 hand-written paraphrases the templates do not contain | >= 95 % exact mapping on paraphrases, 100 % on templates, offline, < 5 ms |

Not in the 2 h box: IL/VLA fine-tuning on the drop (few demos; GR00T fine-tuning is a day of work), RL, rung 3,
our own perception models (Gemma/PaliGemma) inside the image (latency + 32 GB VRAM + no network).

## 3. Checkpoint at T0 + 2 h: go / no-go

T0 = the moment the RTX instance is up. Each criterion is binary; the evidence is a file or a log, not a sentence.

| Area | GO if all true | Evidence |
|---|---|---|
| Sim | `aalto check` 8 PASS; `aalto baseline` 3 trials finish; our server (P1) through `aalto eval` 1+ trial with **0 clips, rate >= 27 Hz, policy_hz_rt >= 27, no abort/timeout/crash** | `eval.json` + `episode_*.jsonl` copied to `aalto/setup/runs/` (small text only) |
| Dataset | drop downloaded and loaded; usable-episode list exists; D3 ran on >= 20 real frames with a number | `aalto/data/REPORT.md` |
| Baseline | P1 runs on mock with the parsed mapping; L2 meets its bar; one `sort_language` sim trial scores > 0 with 0 clips | test output + eval.json |

Decision rule:
- **GO** (all three): continue tonight with S2 on 20 trials per rung, then tune where D3 shows the baseline
  failing on real frames (colour thresholds, triangle grasp), then submit the image.
- **PARTIAL** (sim GO, dataset late): continue; the dataset is a bonus for tuning, not a blocker.
- **NO-GO** (sim not passing the gate at +2 h, or no RTX instance available): stop spending, shut the instance,
  post the outcome on the board, all effort back to the Rokoko demo. The parser (L1/L2) stays as reusable code.

## 4. Honest risks

1. **Getting an RTX box at all.** Hackathon demand; our A100 is useless for the sim. No RTX in 30 min = no-go.
2. **Setup time.** QUICKSTART says 15 min with the image, 30-40 min bare metal; first shader compile 5-10 min.
   Nobody on the team has done it (Giorgio: "hours, not minutes", untested). Driver < 580.65.06 or a missing
   container toolkit can eat the whole box.
3. **The sim image link** (`aalto-sim:v1`) comes from Discord: a human has to fetch it.
4. **Finalist selection is by sim score on a held-out variant** (other textures, lighting, camera jitter). The
   baseline is available to every team: baseline + parser may not be enough to reach the top 5, and originality
   (20 %) is low for it. Our edge is rung 2 robustness to unseen phrasings, and D3's real-frame check.
5. **Real-robot vision has never run for us:** PC2 (head RGB-D + wrist cams) was off all of Giorgio's session.
   If it is off at the finals, every vision policy fails; ask the staff early.
6. **Safety traps (seen on the real G1):** wrists start inside the counter keep-out, resting fingers sit past the
   URDF limits. Commanding the measured pose = clips = abort. P2 must handle both before anything else moves.
7. **Rate gate:** any slow step in `act()` (LLM, big model) drops below 27 Hz; `policy_hz_rt` checks our own
   latency, so a slow sim does not hide it. Keep the parser in `reset()`, never in `act()`.
8. **The dataset is raw and small:** failed and messy episodes mixed in; not enough for IL in this window.
9. **People and budget:** two people, Rokoko demo stays Giorgio's priority, Tommaso's usage limit, plus new GPU
   spend. Codex permissions must be widened by Tommaso for `aalto/`.
10. **Rule traps:** no privileged sim state in the submission, no hard-coded layouts, weights inside the image,
    <= 40 GB, <= 32 GB VRAM, server up in < 120 s.

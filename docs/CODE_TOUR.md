# Ten-minute technical judge tour

Snapshot: `9ab91f9`, reviewed for issue #169 on 2026-11-15. This is an **offline code/evidence tour**, not a live hardware demonstration. Start in the repository root with an already-installed Python environment. Do not install packages, download weights/assets, start inference services or connect to hardware during this tour. Use the companion [scorecard](SCORECARD.md) for challenge-specific questions.

## Directory map

| Path | What to inspect |
|---|---|
| `Rokoko/src/` | Stream decoding, glove calibration, raw recording/replay, episode generation and mock inputs. |
| `ml/` | Closure assist, episode labels, gesture/policy experiments; not all modules sit on the current demo path. |
| `ai/` | Image recognisers, vote aggregation, object caps, legacy profile picker, language router and episode judges. |
| `robot/` | Five-finger simulation pipeline, retargeting, real-take replay and the simple G1 simulation bridge. |
| `g1/` | Arm/hand integration, live-policy adapters, provisional object profiles and MuJoCo experiments under `sim/`. |
| `vision/`, `cv/` | Camera/table and object localisation, detector/embedding experiments; consult their result files before quoting a score. |
| `demo/` | Dashboard, fan-out and launch scripts; a displayed status is not independent proof of a grasp. |
| `tests/` | Unit/integration checks, synthetic inputs, fake services and conditional asset/data tests. |
| `docs/evidence/recognition/` | Committed per-photo answers, labels and latencies; **not the photos**. |
| `data/`, `imgs/` | Local runtime/recording/assets and image prerequisites; do not assume they exist in a fresh clone. |

## Data flow in plain words

The Rokoko client decodes glove rotations and, when available, wrist pose. It publishes normalised finger closures. A camera image takes a separate path through recognisers. `ai/recognize.py` collects their answers, favours a sufficiently confident egg answer (or an egg with unknown confidence), and otherwise chooses by vote count and mean confidence. `ai/object_profile.py` turns that result into a provisional closure limit. The operator still supplies motion; the limit restricts how far fingers may close.

These are **several related paths**, not one interchangeable implementation:

- **Legacy five-finger demo:** `Rokoko/src/rgmp_client.py` → hand-state packet → `robot/pipeline.py` → `ml/grasp_assist.py` → `robot/scene.py`. `robot/sim_server.py` accepts profile updates; `demo/fanout.py` distributes packets. `ml/grasp_assist.py` has its own old profile table.
- **Recognition ensemble:** image → `ai/recognize.py` → `ai/object_profile.cap_for_votes` → optional UDP profile/object/cap publication. Defaults include a colour baseline; PaliGemma requires explicit backend selection. Backend count is not enforced family independence.
- **Simple G1 simulation bridge:** `robot/e2e_g1.py` → `behaviour(label)` → `g1/sim/grasp_physics.py` → capped/uncapped held/broken output. Manual `--label` skips AI. Image mode uses one recogniser, not the ensemble.
- **Live-policy adapter:** `g1/live_policy_v1.py` combines glove input, perception, state transitions, IK and caps for the organisers' policy interface. V2 adds the Coil chain (`g1/coil_chain.py`). These are hardware-facing code paths, not evidence of physical execution.
- **Post-episode judge:** `ai/judge_gemini.py` reads a recorded episode after the motion. It does not directly control the hand.

Read `docs/contracts.md` for interface context, but check the actual selected path: the old five-finger cap, G1 shared cap and posture-specific experiments differ. For example, `g1/object_profiles.json` marks can unsupported while `g1/sim/demo_e2e.py` contains separate can scenarios. A scenario's presence does not establish supported can holding.

## Ten important files, with offline entry points

Each row gives the file's role and a way to exercise it offline. Library modules are exercised through tests rather than invented command-line interfaces. Tests use local fixtures/fakes; some integration tests use loopback sockets. Dependencies must already be installed. A skipped test is not a successful experiment.

| # | File and one-line role | Offline command | What it establishes / prerequisite |
|---:|---|---|---|
| 1 | `Rokoko/src/rgmp_client.py` — decodes the stream and publishes normalised glove state. | `python3 -m pytest tests/test_pipeline.py -k rgmp_client_vs_mock -q` | Mock TCP server → client → local UDP; no real gloves or camera. |
| 2 | `robot/pipeline.py` — applies the legacy assist and steps the five-finger scene. | `python3 -m pytest tests/test_truth.py -q` | Synthetic integration in MuJoCo; not a G1 or human demonstration. |
| 3 | `ml/grasp_assist.py` — caps closure, with optional normalised feedback. | `python3 -m ml.grasp_assist` | Toy stiffness/contact calculation; printed “force” is a toy quantity, not a measurement. |
| 4 | `robot/g1_dex3.py` — maps closures to bounded, slew-limited Dex3 joint targets. | `python3 -m pytest tests/test_g1_dex3.py -q` | Mapping/bounds checks; its episode loop returns without exercising episodes if local data is absent. |
| 5 | `ai/object_profile.py` — loads provisional G1 overrides and decides robust/voted caps. | `python3 -m pytest tests/test_safety_matrix.py tests/test_cap_for.py -q` | Policy arithmetic and error-direction checks, not universal physical safety. |
| 6 | `ai/recognize.py` — gathers votes, handles timeouts and chooses fragile-first. | `RECOGNISE_LOG=off python3 -m pytest tests/test_recognize.py -q` | Fake recognisers exercise errors, deadlines and breaker; no live inference. |
| 7 | `ai/paligemma.py` — adapts short PaliGemma answers to votes without confidence. | `python3 -m pytest tests/test_paligemma_backend.py -q` | Fake transport and missing-server behaviour; no GPU/model download. |
| 8 | `robot/e2e_g1.py` — compares capped and uncapped G1 grasp simulation. | `python3 -m pytest tests/test_e2e_g1.py -q` | Skips if cached G1 assets are missing. With assets/MuJoCo already present: `python3 -c "from robot.e2e_g1 import simulate; print(simulate('egg', 'egg'))"`; any force output is simulation only. |
| 9 | `g1/live_policy_v1.py` — connects perception and glove phases to robot-policy targets. | `python3 -m pytest tests/test_live_policy_v1.py -q` | Cap test runs; full policy test requires the organisers' local clone, assets and replay inputs and may skip. No real runner is launched. |
| 10 | `ai/judge_gemini.py` — packages episode samples and parses post-grasp judgements. | `python3 -m pytest tests/test_judge_gemini.py -q` | Fake SDK calls, JSON/NaN handling and unclear results; not live Gemini quality. |

Supporting files worth opening beside those ten: `g1/sim/grasp_physics.py` (the physical assumptions), `g1/object_profiles.json` (toy numbers and unsupported can), `ai/crosscheck.py` (saved-answer audit), `ai/intent_router.py` (local stop keywords and JSON gate).

## Guided agenda — 10 minutes

The durations below are a proposed presentation schedule, not measured execution times. Pre-run long tests and show their output if necessary.

**0:00–1:00 — State the boundary.** Open `docs/ORCH_BACKLOG.md` section 1, then the reconciliation table in `docs/SCORECARD.md`. Say: “The evidence is real head-camera photo answers and glove recordings, plus simulated grasps. Hardware transfer remains unverified.” Point out that the old audit predates the bridge and later recognition runs.

**1:00–2:00 — Follow the human input.** Open `Rokoko/src/rgmp_client.py` at `decode` and `run`, then `robot/g1_dex3.py` at `step`. Show the mock-client test from row 1. Finger closure is not force sensing; the thumb mapping is provisional and the Dex3 does not map all glove fingers.

**2:00–3:00 — Show the saved model evidence.** Run the following. It reads only committed answer JSON:

```bash
python3 -m ai.crosscheck docs/evidence/recognition/nemotron_run2.json docs/evidence/recognition/gemma4_api.json --names nemotron,gemma4
```

Verified output for this snapshot: **69/77 overall agreements**, **47/50 labelled agreements**, **3 single-model errors flagged by disagreement**, and **0 shared wrong answers on the labelled set**. The remaining photos are unlabelled multi-object scenes, not accuracy examples. Read `docs/evidence/recognition/README.md`: one person/place/day; photos absent from git.

**3:00–4:00 — Recompute accuracy without a service.** This command also audits the saved three-model vote; it performs no inference and writes no decision log:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from ai.recognize import decide
root = Path('docs/evidence/recognition')
files = ['nemotron_run2.json', 'gemma4_api.json', 'paligemma2_local.json']
runs = []
for name in files:
    rows = json.loads((root / name).read_text())
    labelled = [r for r in rows if r.get('expected')]
    correct = sum(bool(r['ok']) and r['object'] == r['expected'] for r in labelled)
    print(name, correct, '/', len(labelled))
    runs.append({r['file']: r for r in rows})
keys = sorted(set.intersection(*(set(r) for r in runs)))
labelled = [k for k in keys if runs[0][k].get('expected')]
correct = sum(decide([r[k] for r in runs])['object'] == runs[0][k]['expected'] for k in labelled)
print('saved-answer three-model vote', correct, '/', len(labelled))
PY
```

Expected from these saved files: **48/50**, **49/50**, **49/50**, then **50/50** for the vote. These are the same small photo set, not held-out generalisation or a new model run. `docs/PROMPT_ITERATION.md` also reports later prompt changes tuned on this set; keep that separate from these raw files.

**4:00–5:00 — Inspect the conservative decision.** Open `ai/recognize.py:decide` and `ai/object_profile.py:cap_for_votes`. Run row 6's fake-backend tests. One confident ball vote does not unlock full closure. The egg rule has a confidence condition; the code does not veto every possible egg vote. Agreement count does not authenticate model families. A mean confidence threshold is still used despite no demonstrated calibration.

**5:00–6:00 — Separate the two simulators.** Open `robot/pipeline.py` and `robot/e2e_g1.py`. Show row 8's test output, including any skip. The older 10/11→1/11 egg-break comparison belongs to a five-finger simulation with scripted closure on real wrist paths (`docs/PHASE1_REAL_DATA.md`), not a real G1 result. The newer bridge uses Dex3 geometry and requires separate cached assets.

**6:00–7:00 — Explain toy physics and unresolved cans.** Open `g1/sim/grasp_physics.py` and `g1/object_profiles.json`. Break criteria, object properties and servo gains are assumptions. The source now describes a full sealed can while older prose and other scenarios describe an empty can: do not combine their metrics. The shared profile remains unsupported for can. Later `docs/G1_V2_RUN.md` still reports unsuccessful can holding; its replay aligns/scales the approach and is not an unmodified live take.

**7:00–8:00 — Explain outage handling.** Show `ai/recognize.py:collect`: failed votes are excluded, no answers means `other`, and the breaker opens after three failures for thirty seconds, in memory. Pending worker threads are not forcibly killed. Show `ai/paligemma.py`: missing server is a failed vote. “Self-hosted remote GPU” is not laptop-offline. Show `ai/intent_router.py`: stop keywords are local, malformed model commands become `none`, and firm-mode requests are gated by current object label.

**8:00–9:00 — Show the hardware boundary and slow judge.** Open `g1/live_policy_v1.py` and `docs/G1_V2_RUN.md`'s unverified list. This tour never starts a physical policy/runner. Then open `ai/judge_gemini.py` and row 10's fake-client tests. The executable `DEFAULT_MODEL` is `gemini-3.1-flash-lite`, while older docstrings/docs mention a different default: confirm deployed identity before a live claim. A printed false with NON VALUTATO means unclear, not a labelled failed grasp.

**9:00–10:00 — Close with test evidence and limits.** Show the validation record below and `docs/SCORECARD.md`. Explain what the next experiment would settle: frozen prompts on new photos; marked-object glove takes; verified hardware dry-run under the owner's procedure. Do not claim mock success, saved-answer agreement or passing tests proves physical safety.

## Real data, simulation, photos and hardware

| Evidence class | What exists | Honest boundary |
|---|---|---|
| Real captured photos | Saved per-photo answers in `docs/evidence/recognition/`; source-image method in `docs/OBJECT_RECOGNITION_RESULTS.md` | Cannot visually audit or rerun absent photos from the clone alone; saved answers are not fresh inference. |
| Real glove recordings | Replay methodology/results in `docs/PHASE1_REAL_DATA.md`; recording code under `Rokoko/src/` | Local takes/episodes are prerequisites; scripted closure and trajectory alignment must be labelled. |
| Simulation | `robot/scene.py`, `g1/sim/grasp_physics.py`, `robot/e2e_g1.py`, V2 replay report | Force values and broken/held verdicts depend on toy physical assumptions. |
| Hardware-facing code | `robot/g1_dex3.py`, `g1/live_policy_v1.py`, `g1/live_policy_v2.py`, `g1/run_mock_gate.py` | Source and mock runner coverage do not establish execution on the physical G1. |
| Cloud/self-hosted inference | Reported Verda Nemotron, Google API Gemma, remote A100 PaliGemma results | Current uptime, exact deployed IDs and live Gemini judge quality not checked in this work. |

## Validation record for this documentation change

- `python3 -m pytest tests -q` using the default Homebrew Python failed immediately: `No module named pytest`.
- `PATH=/opt/anaconda3/bin:$PATH python3 -m pytest tests -q` completed: **211 passed, 5 skipped in 33.38 s**. This uses the existing installation; no dependencies were installed. It is local evidence, not PR CI status.
- The saved-answer `ai.crosscheck` command above was run successfully. The recomputation command above also ran successfully: 48/50, 49/50, 49/50 and 50/50, respectively.
- Asset and external-clone checks can skip. `tests/test_g1_dex3.py` also silently returns from its episode-specific test when there are no episodes: green does not imply data coverage.
- No endpoint inference, hardware execution, new camera dataset, asset download, or real-force calibration was performed. Do not use `g1/sim/g1_sim.py` as an unconditional offline command: it fetches model assets when missing.

# Day 2 runbook (proposal, adjust freely)

Principle: **one vertical slice first** (real glove -> retarget -> real hand holds a fragile object, with video), everything else only after it works. Human time with hardware is the bottleneck: agents prepare scripts and tests beforehand, humans spend hardware minutes only on checks that are already scripted.

## 0. First 30 min (humans, in parallel)
| Who | Task | Done when |
|---|---|---|
| Tommaso | NVIDIA key on build.nvidia.com + exact Nemotron 3.5 Super VL model id (booth / catalogue); `export NVIDIA_API_KEY=... LLM_MODEL=...` | `python -c "from ai.llm import ChatClient; print(ChatClient().chat([{'role':'user','content':'ping'}]))"` answers |
| Tommaso | Google AI Studio key (Gemini) as second backend | same call with `LLM_BASE_URL` of the Gemini OpenAI-compatible endpoint |
| Giorgio | Connect repo to CRACI (owner) and Entire | CI check from CRACI visible on a PR |
| Tommaso | Aalto Robotics Club: Inspire model, IP/port, Modbus registers (ANGLE_SET, FORCE_ACT), can it sit on our table? G1 slot with Erkka? | registers written into robot/inspire.py comments + docs/contracts.md |

## 1. Hardware slice (the demo that wins)
1. `pytest tests -q` green (includes Inspire fake Modbus server + G1 Dex3 preflight).
2. Inspire hand, dry first: `python -m robot.run_udp --backend inspire --host <ip>` (prints commands), then `--live --close-cap 0.5` with the mock stream, hand empty.
3. Real glove: `demo/run_demo.sh --real --bimanual --backend inspire --assist egg` (+ `--live` once the dry output is sane). Open/close hand slowly, check direction and limits.
4. Grasp the real object (can or egg) with `--assist egg`; compare with `--close-cap 1.0` only if the object is expendable.
5. Film it (phone + dashboard on screen). Gate: one clean take of a held, undamaged object. If not by midday: fall back to simulation + GIFs and say so.

## 2. Data (only what unblocks something)
- Failures: 5-10 takes with a clearly dropped/missed/crushed object, labelled with `python ml/label.py` (otherwise judge agreement is trivial).
- Object position per take (`--obj` in ml/label.py) so approach can be tested.
- Thumb: only if the SDK solver thumb01 is published; else keep thumb as unverified.

## 3. AI layer (after the slice works)
1. `python -m ai.judge` on all episodes with Nemotron; report precision/recall per class, not accuracy only.
2. Profile picker in the demo (one frame -> `set_grasp_profile`), fallback to the fixed profile.
3. Gemini as second judge: comparison table. Gemma only if something really runs locally.
4. Write the NVIDIA submission text: model, role, why essential, how output was improved (prompt iterations + measured agreement).

## 4. Freeze and pitch
- Feature freeze a few hours before delivery; then only stability, video, slides.
- Numbers slide: latency (measured on hardware), peak force vs break threshold, episodes recorded, judge agreement. Label simulation as simulation.
- Rehearse with the backup plan (mock stream, MuJoCo instead of Inspire, GIFs).

## Rules to stay efficient
- Agents never block on humans: prepare, test with mocks/fakes, post results; humans only do what needs a body or an account.
- Claims in the pitch only if reproducible by a command in this repo.
- Run the loop agent in its own worktree (`git worktree add ../Junction-loop`) to avoid sharing a working tree with an interactive session.

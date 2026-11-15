# NVIDIA — Best Use of Nemotron

**Model:** NVIDIA Nemotron 3.5 Super VL, called through the Verda-hosted endpoint (OpenAI-compatible API, image input, tool calls, thinking off). Exact serving id to confirm with NVIDIA [DA VERIFICARE]; it is marked unverified in `ai/llm.py`.

## The problem
Rokoko gloves give a robot hand human motion but no sense of force. Before a Unitree G1's Dex3 hand closes, something must know whether it is about to squeeze an egg or a stress ball.

## What Nemotron does: the real-time eyes
One head-camera frame before the grasp goes to Nemotron, which returns the object (egg / stress ball / can / other) and a confidence. That answer is the **NVIDIA key** of a two-family vote; the vote sets the closure cap of the robot hand. It is the fastest model in our decision path: **median 0.22 s per call**, measured on our photos.

```
head camera frame ──▶ Nemotron 3.5 Super VL (0.22 s) ──┐
                  ──▶ Gemma 4 / PaliGemma (Google key) ─┼─▶ fragile-first vote ──▶ closure cap ──▶ Dex3 fingers
                  ──▶ colour rule (sanity check) ───────┘
```

## Why it matters
Without a recogniser, every object gets one conservative cap: safe, but the robot can never squeeze the ball firmly. Nemotron is what makes object-aware grasping possible inside the time before the hand closes.

## How we improved its output (measured on our 50 labelled photos)
1. **Latency first.** Thinking off: median 0.22 s. The first full result, 48/50, was reproduced in a second run (`docs/evidence/recognition/nemotron_run2.json`).
2. **Prompt iteration with repeats** (`docs/PROMPT_ITERATION.md`): prompt A scored 47, 49, 49 of 50 over three runs; prompt B, with visual cues (pale oval shell, orange ball, metal can), scored 49, 50, 50. B was written after seeing the failing eggs of this set, so it is optimistic. The spread at temperature 0 taught us that one run is weak evidence.
3. **We found where it fails, and built around it.** Both errors were small eggs called "stress ball", the expensive direction. Its confidence on those errors (0.90) was as high as on its lowest right answers. So one confident answer never unlocks force.
4. **A second family checks it.** Nemotron and Gemma 4 disagreed on 3 of the 50 labelled photos, and each disagreement was exactly one model's error: 3 of 3 caught, none shared.
5. **Outages handled.** Every call has a timeout; three failures open a 30 s breaker; no answer means a conservative cap, never "squeeze".

## Code you can open
| File · function | What it does |
|---|---|
| `ai/llm.py` | OpenAI-compatible client for the Verda endpoint, retries with backoff. |
| `ai/eval_objects.py` · `recognize` | Sends one image, parses the object and confidence; also the evaluation tool. |
| `ai/recognize.py` · `collect`, `decide` | Runs the recognisers in parallel with a deadline, then the fragile-first vote. |
| `ai/object_profile.py` · `cap_for_votes` | Turns the vote into a closure cap; full force only with 2 agreeing families. |
| `ai/perceive.py` · `perceive` | On a G1 head RGB-D frame: finds every object, crops it, asks the recognisers, locates it. |
| `verify/run.py` | Recomputes every number above from the saved answers, offline. |

## Proven / not proven
- **Proven (recomputable offline):** 48/50 on our photos, median 0.22 s, 3 of 3 disagreements = errors (`python3 -m verify.run`).
- **Proven in simulation:** the cap chosen from the label decides egg intact vs broken in the G1 simulation (`python3 -m robot.e2e_g1 --label egg`).
- **Not proven:** generalisation (one person, place and day, no held-out set); Nemotron deciding a grasp on the real robot (the camera path ran there only as a capture test).

## Criteria map
Meaningful usage → it is one of the two keys that set the grip. Technical execution → parallel calls, deadlines, breaker, fallback. Quality of output → repeated runs, prompt iteration, error analysis, cross-family check. Creativity → a VLM as a safety sensor for a hand that cannot feel.

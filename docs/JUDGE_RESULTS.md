# Episode judge (Nemotron 3.5 Super VL via Verda): v1 vs v2

Setup: `python -m ai.judge --version 1|2` over 60 episodes (A-J). Human labels (`ml/label.py`): success=true ("object not dropped") on 32 episodes, unlabelled on 28, **no negative label anywhere**. So only RECALL on positives can be measured; precision is unknown.

| | v1 (aggregate stats only) | v2 (task definition + 0.5 s timeline of closure and wrist height) |
|---|---|---|
| human-positive judged `good` | 5 / 32 (16%) | **22 / 32 (69%)** |
| judged `bad` | 11 | 10 |
| judged `unclear` | 16 | 0 |

How it was improved: v1 gave only peak/mean closure and wrist ranges, so the model said unclear or bad. v2 states the task (grip held while the wrist moves; thumb ignored; series A is a flat hand on a box) and sends a coarse timeline. Reasoning model: needs max_tokens 6000 (~10 s per episode).

## Correction (2026-11-14, PR on branch 71-judge-timeline-compare)
The code that produced the v2 column did NOT send the timeline: `summarize_episode(path, 2)` ignored `version` and `timeline()` was never called. So 22/32 was measured with **v2 prompt (task definition) + aggregate stats only**. The fix adds the 0.5 s timeline to v2 summaries; the v2 number must be re-measured (`python -m ai.judge --version 2`) before the pitch quotes "timeline". Until then say "task-definition prompt: 5/32 -> 22/32".

Two-backend comparison: `python -m ai.compare_judges --a nemotron --b gemini` (needs `GEMINI_API_KEY`; Gemini never receives the NVIDIA/Verda key) prints per-model recall/precision and model-vs-model agreement (raw + Cohen's kappa).

## Warnings (do not over-claim)
- v2 calls non-grasp series `good`: E (calibration open hand/fist) 3/3 and D (noise) 5/5. So it is permissive; precision is probably poor.
- Series F (hands at rest) is correctly `bad` (3/3).
- No negatives => no accuracy, no precision. Needed: 5-10 clearly failed takes (dropped/missed/crushed) labelled with `ml/label.py`, then re-run and report precision/recall per class.
- Text-only. Video frames (robot/DJI camera) are the next improvement and what a vision-language model is for.

## Correction (14/11 morning)
- The v2 run above did **not** send the timeline (0/60 summaries contained it): the 22/32 measures the task-definition prompt only. Fixed in PR #71 (timeline now sent, NaN-safe JSON, output directory created).
- A second run of the SAME no-timeline v2 prompt gave **25/32** good on the 32 human-positive episodes (22/32 before): the run-to-run noise of this judge is about +-3 even at temperature 0. Treat any difference smaller than ~4 episodes as noise.
- The 7 positives called `bad` in the second run: takes 5-9 (series A, flat hand on a box: low closure is the expected pattern there) and 13, 22 (series B).
- Still no negatives: precision unknown. Series F (rest) and J are called `bad` (correct for F); E (calibration) and D (noise) are called `good` (wrong): the judge is permissive.
- Pending: re-run with the real timeline after PR #71 is merged.

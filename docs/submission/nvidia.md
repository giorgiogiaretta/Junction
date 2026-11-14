# NVIDIA Nemotron prize: draft

## Model
Nemotron 3.5 Super VL via the hackathon Verda endpoint (OpenAI-compatible chat API, image input, tool calls, thinking off). Client: `ai/llm.py`. The exact model id string is marked unverified in `ai/llm.py`: confirm with the NVIDIA mentors before submitting.

## Role in the system
Nemotron is the **fast vote** in our object-recognition ensemble and the single model in the live G1 picker. Before a grasp, one head-camera frame goes to Nemotron, which returns the object (egg / stress ball / can / other) and a confidence via a tool call (`ai/pick_profile.py`, `ai/recognize.py`). The answer selects the closure cap the robot hand must respect (`ai/object_profile.py`), published on UDP 14070.

## Why it is essential
Smartgloves have no force sensors, so without a recogniser the system cannot know whether it is about to squeeze an egg or a stress ball and falls back to one conservative cap for everything. Nemotron is the fastest of our recognisers: median 0.22 s per call against 7.7 s for Gemma, so it is the one that fits a live take.

## How we improved the output (measured, same 50 photos)
- **Reproduced**: 48/50 in the first run and 48/50 again in the second run, median 0.22 s per call (max 0.31 s), 0 failed calls. `python -m ai.eval_objects imgs --backend nemotron --mix`; `docs/OBJECT_RECOGNITION_RESULTS.md`.
- **Its errors are the dangerous kind**: both errors are small eggs called "stress ball". Confidence does not help: the two wrong answers have confidence 0.90, the same as the lowest right answer. So we never let a single confident answer unlock full closure on the ball.
- **Ensemble, fragile first**: Nemotron + Gemma 4, where any confident "egg" vote wins, gives 50/50 with all 20 eggs right, computed offline from the saved answers (`ai/recognize.py`). Full closure on the ball needs 2 agreeing recognisers (`cap_for_votes`, `python3 -m pytest tests/test_cap_for.py -q`).
- **Simulation consequence**: an egg mistaken for a stress ball is still held intact in the G1 Dex3 simulation thanks to the shared cap; without the cap it breaks (`python3 -m robot.e2e_g1 --true egg --label stress_ball`). Simulated forces use assumed thresholds.
- **Episode judge**: adding a task definition to the prompt raised positives judged good from 5/32 to 22/32 (repeat run 25/32, noise about ±3), positives only (`docs/JUDGE_RESULTS.md`).

## Caveats
One person, one place, one day, 50 photos; folder name = label; no held-out set. The endpoint was unreachable for part of the day, which is why every call has a timeout and a conservative fallback.

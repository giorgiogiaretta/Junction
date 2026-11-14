# NVIDIA Nemotron prize: draft

## Model
Nemotron 3.5 Super VL, called through the hackathon Verda endpoint (OpenAI-compatible chat API, image input, tool calls). Client: `ai/llm.py`. The exact model id string is marked unverified in `ai/llm.py`; confirm with the NVIDIA mentors before submitting.

## Role in the system
Nemotron is the **primary object recogniser**. Before a grasp, one head-camera frame (optionally cropped around the hand, `ai/crop.py`) is sent to Nemotron, which returns the object (egg / stress ball / can / other) and a confidence through a tool call. That answer selects the grip limit the robot hand must respect (`ai/pick_profile.py` -> `ai/object_profile.py` -> UDP 14070).

A second use: Nemotron as a text judge of recorded glove episodes ("was the grasp held?"), `ai/judge.py`.

## Why it is essential
Smartgloves have no force sensors, so the system has no other way to know whether it is about to squeeze an egg or a can. Without the recogniser the picker falls back to a conservative `cup` limit for everything: safe, but it gives up the per-object behaviour that is the point of the project.

## How we improved the output (measured)
- **Recognition**: 48 of 50 of our own head-camera photos in one run (egg 18/20, stress ball 22/22, can 8/8). `python -m ai.eval_objects imgs --backend nemotron --mix`; `docs/OBJECT_RECOGNITION_RESULTS.md`. One person, one place, one day.
- **Making the errors safe**: both errors were small eggs called "stress ball", the dangerous direction. We made the model report a confidence and added rules that only soften: a stress-ball answer with confidence < 0.9 becomes egg, < 0.6 becomes at most the conservative `cup`, and timeouts fall back to `cup`, never to no limit. `python3 -m pytest tests/test_picker_safety.py -q`. Thresholds are hand-picked and not yet calibrated on live confidences.
- **Episode judge prompt**: adding a task definition to the prompt raised positives judged good from 5/32 to 22/32 (a repeat run gave 25/32, so noise is about ±3). Positives only, no labelled negatives, so precision is unknown. `python3 -m ai.judge --version 2`; `docs/JUDGE_RESULTS.md`.
- **Reliability lesson**: the endpoint stopped answering after the recognition run (calls timed out from 11:45). This is why the picker has fast failure (20 s, 1 retry), a Gemini backup and a safe fallback.

## Honest limits
Latency of the model itself was not measured (the run was dominated by our client rate limiter). The 48/50 run could not be repeated yet.

# The model story: two keys, two families, one safe hand

**One sentence.** A Rokoko glove cannot feel force, so before the hand closes **two independent AI model families must agree what the object is**; when they disagree, the robot stays conservative and asks a human.

## Why not one model
Every recogniser errs: on our 50 labelled head-camera photos Nemotron missed 1-2 eggs (called them a stress ball) and Gemma 1 ball. An egg treated as a ball is the expensive mistake. A single model's confidence does not warn us: both wrong Nemotron answers and Gemma's one wrong answer have confidence 0.90, the same as the lowest right answers.

## NVIDIA Nemotron 3.5 Super VL = the real-time eyes
- **Job:** one head-camera frame, before the grasp -> object + grasp profile (tool call `set_grasp_profile`), median **0.22 s** with thinking off (measured, `docs/OBJECT_RECOGNITION_RESULTS.md`).
- **Why it is essential:** the hand cannot start closing until it knows what it holds, and this is the only model fast enough to sit inside the grasp decision.
- **How we improved its output:** (1) thinking off for latency (0.4 s instead of seconds); (2) safety layer around it: shared egg/ball cap, fragile-first vote, conservative fallback; (3) prompt iteration with visual cues, measured in `docs/PROMPT_ITERATION.md` (A: 47, 49, 49 of 50; B: 49 (one failed call), 50, 50 of 50 over three repeats; tuned on the same photos, so optimistic); (4) endpoint outages handled: fallback is never "squeeze".
## Google Gemma 4 on our own GPU = the independent second key and the voice
- **Job 1, second opinion:** a different model family looks at the same frame (49/50 on our photos, eggs 20/20).
- **Job 2, language:** the operator can say "Oggetto caduto, cambia in modalita' presa forte"; Gemma returns strict JSON that a safety gate validates (a firm grip is only allowed for the stress ball; "stop" never waits for a model).
- **Why on our own GPU:** no quota, no data leaves, open weights, real latency we can measure.
## Gemma on our own GPU, measured (14/11 evening)
PaliGemma 2 (Gemma family, 3B) runs on a Verda A100 behind an SSH tunnel: 49/50 on our photos with a 3-option question, median 0.21 s, and in a three-model vote (Nemotron + Gemma-4 + PaliGemma) every ball is confirmed by two models and no egg is missed (50/50 on the same photos: optimistic, one person/place/day). Honest note: the binary "fragile or rigid?" question does not work on it (it says "fragile" for everything).

## Google Gemini = the slow judge
After a recording, Gemini reads the whole episode and says whether the hand-off worked (free-tier aware: daily-quota chain, async). It never sits in the real-time loop.

## The two-key rule, measured
Nemotron vs Gemma agree on 69/77 photos; on the 50 labelled photos they disagree on 3, and **each disagreement is exactly one single-model error** (3 of 3 caught, 0 mistakes shared by both). Disagreements go to human review. Full force on the stress ball needs the two families to agree (or the operator's explicit choice).
**Caveats we say out loud:** 50 photos, one person, one place, one day; agreement is not accuracy; simulation only for the grasp; the first real G1 run is at 10 % closure.

# Jury cheat sheet — 12 answers, one page

**If in doubt, say this:** "Motion is proven on the real G1. Vision-guided grasping is shown in simulation only. Numbers are on our 50 photos: one person, one place, one day."

| # | Who | Question | Say this |
|---|---|---|---|
| 1 | Rokoko | Did it run on the real robot? | **Motion, yes.** Gloves drove the real G1's arms and hands: 2 runs of 120 s, 0 commands clipped by the safety filter. Vision-guided grasping: simulation only. |
| 2 | Rokoko | What is new for Rokoko? | Gloves give motion, not touch. Vision adds the missing sense, and every demonstration comes out labelled with its object: training data. |
| 3 | Rokoko | How good is the glove signal? | 89 takes, 83 Hz glove stream, 0 dropouts, max gap 12 ms. Dex3 has three fingers: thumb, index, middle map one to one. |
| 4 | Rokoko | Why did the real arms lag? | Real arms lagged 0.6-1.4 s under load; our policy takes 4-8 ms per command. The lag is in the runner loop on our Windows setup. A fix exists on a branch, not tested on the robot. |
| 5 | NVIDIA | Why Nemotron, what does it decide? | The fast first look: median 0.22 s per call. It is the NVIDIA key of the vote that sets the finger cap. Without it, every object gets one conservative cap. |
| 6 | NVIDIA | How did you improve its output? | Thinking off. Repeats: prompt A 47, 49, 49 of 50; prompt B 49, 50, 50, tuned on the same photos. Error analysis: both errors were eggs called balls. Second family: 3 of 3 disagreements were one model's error. |
| 7 | NVIDIA / Google | Is 50 of 50 real? | On our 50 photos, yes, recomputable offline (`python3 -m verify.run`). One person, one place, one day, no held-out set: a start, not a proof. |
| 8 | Google | Why two Google models, one key? | Gemma 4 got all 20 eggs right. PaliGemma 2 runs on our own Verda GPU, median 0.24 s. Same family: counting them twice would be a fake second opinion. |
| 9 | Google | What did not work? | Asked "fragile or rigid?", PaliGemma said fragile for 48 of 50 photos. A concrete three-option question works. |
| 10 | All | What if the models are wrong? | Fragile first: one credible "egg" vote wins. Wrong answers had the same confidence as the lowest right answers, so confidence never unlocks full closure. No answer: conservative cap. |
| 11 | All | Why do real caps differ from the simulation rule? | Two layers. Simulation: the models decide, under the two-family rule. Real G1: the operator sets hard caps, egg 0.50, empty can 0.90, ball 1.0, and the camera can only lower them. Hardware is stricter. |
| 12 | Verda | Why your own GPU? | Independence and privacy: the second family runs on a Verda GPU we control, no daily quota, photos never leave it. We did not train at scale on Verda. |

## Extra facts, only if asked
- The one photo two models got wrong (egg-012) was saved by the third model's egg vote.
- Every stress ball was confirmed by both model families (22/22), in the three-model vote.
- Gemma 4 through the API: median 7.7 s per call. That is why PaliGemma runs on our own GPU.
- In simulation the break thresholds are assumed. We say "intact" or "broken", nothing more.
- Coil filter delay 197 ms → 20 ms on replayed takes.

## Never say
- That vision guides grasps on the real G1.
- Any force value or force unit.
- A percentage without "on our 50 photos". Prefer "48 of 50".
- Any claim that it works beyond our photos, that it learns on its own, or any absolute safety promise.
- The simulation caps (0.55, 0.70): not in our numbers table.

## Not verified — do not state as fact
- GPU type on Verda ("A100") and credits spent **[DA VERIFICARE]**
- Exact Nemotron serving id on the Verda endpoint **[DA VERIFICARE]**
- Gemini: only if we link the challenge; role = judge after the run, offline tests only **[DA VERIFICARE]**

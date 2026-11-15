# G — Twelve hard jury questions, short honest answers

| # | Challenge | Question | Answer |
|---|---|---|---|
| 1 | Rokoko | Did it run on the real robot? | Motion, yes: the gloves drove both arms and both Dex3 hands of the real G1, two 120-second runs, zero commands clipped by the safety filter. Vision-guided grasping is shown in simulation; on the real robot the camera path ran only as a capture test. |
| 2 | Rokoko | What is new for Rokoko here? | Gloves give motion but not force. We add the missing sense with vision, and every demonstration comes out labelled with the object and the outcome: training data. |
| 3 | Rokoko | How good is the glove signal? | 89 takes at 83 Hz, 0 dropouts, max gap 12 ms on the glove clock. The Dex3 has three fingers, so thumb, index and middle map one to one. |
| 4 | Rokoko | Why did the real arms lag? | We measured 0.6-1.4 s between command and motion under load, while our policy needs 4-8 ms per command. The lag is in the runner loop on our Windows setup; a fix is on a branch and has not been tested on the robot. |
| 5 | NVIDIA | Why Nemotron, and what does it decide? | It is the fast eyes, median 0.22 s per frame, and the NVIDIA key of the vote that sets the finger cap. Without it every object gets one conservative cap. |
| 6 | NVIDIA | How did you improve its output? | Thinking off for speed; three repeated runs per prompt (47, 49, 49 then 49, 50, 50 of 50, tuned on the same photos); error analysis (both errors were eggs called balls); a second model family that caught 3 of 3 disagreements. |
| 7 | NVIDIA / Google | Is 50 of 50 real? | On our 50 photos, yes, recomputable offline with `python3 -m verify.run`. One person, one place, one day, no held-out set: a start, not a generalisation claim. |
| 8 | Google Gemma | Why two Google models, and why count them as one key? | Gemma 4 got every egg right; PaliGemma runs on our own GPU in 0.24 s. They share a family, so counting them twice would be a fake second opinion. |
| 9 | Google Gemma | What did not work? | Asking PaliGemma "fragile or rigid?": it said fragile for 48 of 50 photos. A concrete three-option question works. |
| 10 | All | What if the models are wrong? | Fragile-first: one credible "egg" vote wins. The model's confidence was as high on wrong answers as on right ones, so confidence alone never unlocks force. No answer means a conservative cap. |
| 11 | All | Why are the real-robot caps different from the simulation rule? | Two layers. In simulation the models may decide under the two-family rule. On the real G1 the operator sets hard caps (egg 0.50, empty can 0.90, ball 1.0) and the camera can only lower them. Hardware is stricter. |
| 12 | Verda | Why your own GPU? | Independence and privacy: the second model family runs on a Verda A100 we control, no daily quota, photos never leave it. We did not use Verda for training at scale. |

Never say: that vision runs grasps on the real G1, any force value, a percentage without "on our 50 photos", "it generalises", "it learns by itself".

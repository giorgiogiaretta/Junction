# Pitch speech (3 minutes) + jury Q&A

English, spoken. Matches the twelve-slide deck (`deck/`), core route. Numbers only from `docs/submission/STORY.md` ("Numbers we may say"). Rehearsal targets, not measured times. Read it aloud twice before the demo.

## Speech (about 450 words, 3:00)

**[0:00] Hook.**
Aristotle said we have hands because we are wise. Two and a half thousand years later, robots finally have hands. They still do not know how to hold an egg.

**[0:20] The problem.**
Today you teach a humanoid with expensive teleoperation rigs. We use Rokoko Smartgloves instead: put them on, move naturally, and the robot's hand follows. Anyone can demonstrate. But the gloves have one limit. They cannot feel force. A confident human fist is a crushed egg on the other side.

**[0:50] Proof it works on a real robot.**
Giorgio drove both arms and both Dex3 hands of a real Unitree G1 with the gloves: two runs of 120 seconds, 29.8 hertz, zero commands clipped by the safety filter. That is motion. We are not claiming vision-guided grasping on the physical robot yet, and we say so.

**[1:15] Our idea: the robot looks first.**
A head camera sees the object before the hand closes. Several recognisers vote: NVIDIA Nemotron as fast eyes, Google Gemma and PaliGemma as the second opinion, a colour rule as a sanity check. The vote is fragile-first: if a credible recogniser says egg, it is an egg. Two keys must agree, counted per model family, before anything gets full force.

**[1:50] Then it holds back.**
The object sets a closure cap. Egg: gentle. Stress ball: full squeeze only when two families agree, or the operator says so. Unknown: careful. In our G1 simulation, same egg, same fist: with the cap it is held intact, without it, broken.

**[2:20] The numbers, honestly.**
On our fifty labelled photos: Nemotron 48, Gemma 4 49, PaliGemma 49. Together, fragile-first, 50 of 50. But these photos come from one person, one place, one day. And model confidence does not separate right from wrong: wrong answers scored as high as right ones. That is exactly why the cap is a safety layer and not a trust in any single model. The thresholds are toy values until we calibrate them on hardware.

**[2:45] Close.**
Repetitive work: the glove teaches, the robot repeats. Delicate work: the camera protects. The operator just moves naturally. The easy way to teach a humanoid.

## Jury Q&A (short answers)

| Question | Answer |
|---|---|
| Does it work on the real robot? | Motion: yes, two 120 s runs, zero clips. Vision-guided grasp: only in simulation so far. Next step is the first real ball grasp at a 0.1 closure limit. |
| Why not a force sensor? | Gloves and Dex3 here have none, and that is the point: the camera gives the missing context. A tactile sensor would complement it. |
| Is 50 of 50 real? | Yes, on our photos, and recomputable from raw answers in `docs/evidence/recognition/`. It is not a generalisation claim; we tried several prompts on the same set. |
| What if the models are wrong? | Fragile-first: one credible egg vote wins. Wrong-model errors we saw were single-model, and the cap stays at 0.70 for egg/ball unless two families agree. |
| Why three model families? | Independent errors. Nemotron called eggs balls; PaliGemma called an egg a can. Counting Gemma and PaliGemma as one key avoids a fake second opinion. |
| Where is Gemini? | Asynchronous judge of recorded episodes, outside motion control, quota-aware on the free tier. |
| What does the egg break threshold mean? | A toy 3 N value in the sim, tuned for the demo. Not a measurement of a real egg. |
| What about the can? | Unsupported for now; capped conservatively. |
| What is the next step? | Vision on the real G1, other people and places, and automatic object labels for Rokoko grasp datasets. |

## Never say
"works on the G1" for vision, any Newton value as a real force, a percent without "on our 50 photos", "generalises", "learns by itself".

## Italiano, promemoria in 5 righe
1. Mani e saggezza (gancio). 2. Guanti facili ma ciechi alla forza. 3. Robot reale: solo moto, 0 clip. 4. Visione prima: voto fragile-first, due chiavi per famiglia. 5. Onestà: 50 foto, soglie toy, prossimo passo sul robot.

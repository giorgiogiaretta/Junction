# Pitch story brief (for the deck owner: Tommaso's Codex, `deck/`)

Language of the deck: English. Every number must come from the "Numbers we may say" table; wording from `docs/ORCH_BACKLOG.md` section 1.

## The line
**"The easy way to teach a humanoid. Repetitive work. Delicate work. Now it's easy."**

## Story arc (3 minutes, 8 slides)

| # | Beat | Say (core) | Show |
|---|---|---|---|
| 1 | **Hands make us human** | Anaxagoras said humans are the wisest animals because they have hands. Aristotle answered the other way round: we have hands because we are wise, and the hand is "the instrument of instruments". Giordano Bruno called the hand the organ that lets the mind act on the world. 2,500 years later, robots finally have hands. They still don't know how to use them. | Black slide, three names, one hand photo (ours, from the head camera) |
| 2 | **Teaching is hard** | Today you teach a humanoid with expensive teleop rigs and experts. Two kinds of work need hands: **repetitive** (pick, place, sort, all day) and **delicate** (an egg, fruit, a glass). | Split: repetitive / delicate |
| 3 | **Gloves: easy to teach** | Put on Rokoko Smartgloves, move naturally: the G1 hand follows. Anyone can demonstrate. 89 takes recorded, 83 Hz glove stream with 0 dropouts. | Glove -> G1 Dex3 in MuJoCo |
| 4 | **But gloves can't feel** | No force sensor. A confident human fist crushes the egg on the robot. In our G1 simulation: egg without a limit = broken. | e2e sim still, "no cap: broken" |
| 5 | **So the robot looks first** | A head camera sees the object; four recognisers vote, and the fragile answer always wins. Nemotron answers in 0.22 s; Gemma got every egg right; together 50 of 50 on our photos. | Vote diagram, 3 logos |
| 6 | **Then it holds back** | The object sets a closure cap. Egg: gentle. Stress ball: full squeeze only if two models agree. Unknown: careful. Same egg, same fist: with the cap it is held intact, even when a model mistakes it for a ball. | Cap vs no-cap side by side |
| 7 | **Now it's easy** | Repetitive work: the glove teaches, the robot repeats. Delicate work: the camera protects. The operator just moves naturally. First real G1 test runs at 10% closure. | Live / video of the run |
| 8 | **Honest + next** | Shown: recognition on our 50 photos, end-to-end grasp in simulation. Next: real G1 at higher closure, more people and places, labelling Rokoko grasp datasets with the object automatically. | Two columns |

Philosophy quotes: paraphrase, attribute (Anaxagoras via Aristotle, *Parts of Animals* IV.10; Aristotle, *De Anima* III.8; Giordano Bruno, *Spaccio de la bestia trionfante*). Do not invent verbatim Bruno quotes.

## Numbers we may say (source)

| Number | Exact safe wording | Source |
|---|---|---|
| 0.22 s | "Nemotron: median 0.22 s per call, 48 of 50 in two runs" | `docs/OBJECT_RECOGNITION_RESULTS.md` |
| 20/20 | "Gemma 4 got all 20 eggs right, 49 of 50 overall" | same |
| 50/50 | "Together, fragile-first: 50 of 50 on our photos (computed offline, same photos)" | same |
| held vs broken | "In simulation: with the cap held intact, without it broken" (no Newton) | `python3 -m robot.e2e_g1 --label egg` |
| 83 Hz, 0 dropouts | "89 takes, 83 Hz glove stream, 0 dropouts" | `Rokoko/src/episode_quality.py`, board 13:30 |
| 10% | "First real G1 test at 10% closure" (say a result only if recorded in `docs/G1_LIVE.md`) | `docs/G1_LIVE.md` |

## Never say
"works on the G1" (until a recorded result), forces in Newton, "96%" or any percent without "on our 50 photos", "generalises", "learns by itself".

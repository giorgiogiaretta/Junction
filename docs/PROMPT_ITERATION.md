# Nemotron prompt iteration (how we improved the output), 14/11

Task: name the object in a head-camera photo (`egg` / `stress_ball` / `can` / `other`), 50 labelled photos in `imgs/` (not in git), thinking off, three repeats per prompt, same endpoint and images (`ai.eval_objects.recognize`).
- **Prompt A (v1, the one we shipped):** classes + short definitions ("stress_ball = soft squeezable ball", "can = drink can").
- **Prompt B (v2):** adds the visual cues that the two failing photos pointed at: "egg = a smooth pale/white oval shell, often small in the fingertips and possibly with a printed stamp", "stress_ball = a squeezable ORANGE ball", "can = a metal drink can", plus "colour is a strong cue" and "the object the hand holds or is about to grasp".

| Prompt | Run 1 | Run 2 | Run 3 | Errors |
|---|---|---|---|---|
| A | 47/50 (one call failed, endpoint slow) | 49/50 | 49/50 | egg-014 (-> stress_ball) every run; egg-012 in run 1 |
| B | 50/50 | 50/50 | 50/50 | none |

**Read this honestly.** B was written after looking at the failing eggs of THIS photo set, so it is tuned on the evaluation photos: the 50/50 is optimistic and says nothing about eggs in other light, hands or places. The honest takeaways: (1) model answers vary run to run even at temperature 0 (A: 47, 49, 49), so single runs are weak evidence; (2) adding the visual cues removed the egg-to-ball error on this set in 3/3 runs; (3) the safety design does not rely on this: egg and ball share the cap and the vote is fragile-first. To confirm B we need NEW photos (other person, light, place) never used while writing the prompt: the 8 advisor photos and any new egg/ball/can shots are the held-out set.

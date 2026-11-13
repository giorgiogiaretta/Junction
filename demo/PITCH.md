# Pitch + live demo script (5 min) — Rokoko x Junction

**One line:** Safe, low-latency glove teleoperation for fragile objects that doubles as a robot-training data recorder.

## Story
1. **Problem (30 s):** Robots learn dexterity from human demonstrations, but good demos are scarce. Webcam hand tracking drops fingers when occluded and cannot be trusted near fragile objects; teleop jerks crush things.
2. **Solution (30 s):** Rokoko Smartgloves II -> 5-finger stream -> retargeting to a dexterous hand (Inspire/G1) with smoothing and a grasp limiter for fragile objects. Every session is also recorded as a synchronised dataset for imitation learning.
3. **Live demo (2 min)** — `demo/run_demo.sh --real --backend inspire` (or `--backend sim` if hardware fails):
   - Open/close hand: dashboard shows fingers, gesture label, fps, latency (ms).
   - Robot (or sim) hand mirrors it.
   - Pick up the fragile object (cup/egg) with `--close-cap 0.6`; contrast with uncapped closure.
   - Show the recorded episode and the policy replaying it (Giorgio's recorder/policy, #13/#15).
4. **Glove vs webcam (30 s):** run the webcam baseline (Rokoko/src, MediaPipe) side by side. Talking points: occlusion-proof, ~1 kHz-class sensor data vs ~30 fps camera, works in the dark, measured joint angles rather than inferred. Show the latency numbers from the dashboard for both.
5. **Business model (1 min):**
   - *Data-collection-as-a-service:* sell expert demonstration hours (skilled trades, lab handling) to robotics labs/startups (Physical Intelligence, Skild, Generalist type buyers). Price per demo-hour + dataset licence.
   - *Teleop kit:* glove + retargeting software subscription for remote operation of hazardous or remote tasks.
   - Moat: quality metrics on every episode (smoothness, success, fragility score) so buyers pay for clean data.
6. **Close (20 s):** Next: remote teleop over the internet, multi-robot retargeting, closed-loop force feedback.

## Backup plan
- No gloves: `demo/run_demo.sh` (mock stream) — same dashboard and robot path.
- No robot hand: `--backend sim` (MuJoCo); `mjpython -m robot.sim` for the viewer.
- Network/USB trouble: pre-record a 30 s screen capture of the full flow on the first working run.

## Rehearsal checklist
- [ ] `rokoko-sdk --auto-stream-usb` running; calibrate (open/close 8 s) before going on stage
- [ ] Dashboard visible on the projector; latency < 100 ms
- [ ] Fragile object and a rejected-grasp demo ready
- [ ] Numbers on one slide: latency, fps, episodes recorded, success rate

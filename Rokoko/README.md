# Rokoko Smartgloves Challenge (Junction Hackathon, Finland)

- Info/SDK/links: https://www.rokoko.com/mocap/junction-hackathon
- Hardware: available at the hardware lab at the venue; Rokoko mentors help with setup.
- Guide: Rokoko_Smartgloves_Hackathon_Guide.pdf (in Downloads)

## Brief
48h, one pair of gloves. Gloves capture hand + finger motion (NOT touch or force).
Two main uses: **teleoperation controller** (hand drives a robot hand/gripper live) and **data recorder** (demos to train a robot policy).
Tip: best pitches = working demo + business model.

## Ideas (difficulty)
1. Glove-to-robot-hand teleop: 5 finger angles -> servo/3D-printed hand grabs a cup (Medium)
2. Record-and-replay data kit: glove + head camera, export dataset, replay on cheap arm (Medium)
3. Remote teleop over internet: web dashboard, live video, latency counter (Medium)
4. Skilled-trade capture: 20 expert runs of one task, searchable library (Easy)
5. Glove-in-simulation: drive virtual hand in MuJoCo/Isaac Sim, save grasp trajectories (Medium)
6. Train a tiny policy: ~50 demos pick-and-place, train ACT, 1 autonomous run (Hard)
7. Gesture control for any robot: 5-6 gestures -> drone/rover/arm commands (Easy)
8. Hand-motion analytics for health/safety: range of motion + rep counts dashboard (Easy)

## Startups to learn from
Physical Intelligence, Skild AI, Generalist, Sunday, Genesis AI, Origami Robotics, Proception, Asimov, Human Archive, Aktoria, Markov, Shotwell, Rodeo.

## Notes
(team, chosen idea, plan go here)

## Setup (code in `src/`)
1. `pip install -r requirements.txt` (Python 3.11+; the Rokoko SDK examples want 3.12+).
2. Rokoko Studio: connect gloves, Livestream > Custom forward > UDP 127.0.0.1:14043, JSON v3.
3. `python src/listen.py --show` to see the real frame keys, then adapt a parser.
4. No hardware yet: `python src/mock_stream.py` in another terminal.
5. Record: `python src/listen.py --out data/demo1.jsonl`.

Docs: https://sdk.rokoko.com/guides/streaming-data/ (RGMP, Smartgloves II USB) · https://support.rokoko.com/hc/en-us/articles/4410416376977-Custom-Streaming · Studio Command API (HTTP, default port 14053, key 1234) for start/stop recording.

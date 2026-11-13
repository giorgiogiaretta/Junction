# Demo

One command: `demo/run_demo.sh` (mock stream) or `demo/run_demo.sh --real --backend serial --dev /dev/ttyACM0`.
Flow: glove/Rokoko Studio -> UDP 14043 -> `fanout.py` -> dashboard (14044) + robot hand (14045).
Needs `pip install -r demo/requirements.txt -r robot/requirements.txt`. Backends: `dry`, `sim`, `serial`, `pca9685`.
Note: `--backend sim` opens no viewer through run_udp; use `mjpython -m robot.sim` separately for visuals.

## Pitch flow (3 min)
1. Problem: robots learn from human demonstrations, but gathering them is slow and expensive.
2. Live: put on the glove, open/close the hand; dashboard shows fingers, recognised gesture, latency (ms) and fps; the robot hand mirrors it.
3. Show a gesture (point, peace, fist) -> label changes -> same stream can trigger robot commands.
4. Record: same stream saved as dataset (Rokoko/src/listen.py --out) -> train a policy (ml/).
5. Business model: sell a glove + capture kit as a data-collection service for robotics teams (pay per demo hour / dataset licence).
6. Close: next steps (remote teleop over the internet, more hand sensors).

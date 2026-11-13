# Contracts

Interfaces between teammates (functions, JSON schemas, ports). Update and post on the board when they change.

- Glove stream: Rokoko Studio -> UDP 127.0.0.1:14043 (JSON v3). Parsed fingers: 5 floats 0..1 (TBD after seeing a real frame).
- Robot hand (`robot/hand.py`): `make_hand(kind, **kw)` -> `Hand.set_fingers([5 floats 0..1])`, 0=open, 1=closed, order thumb,index,middle,ring,pinky. kinds: `dry`, `sim` (MuJoCo), `serial` (Arduino, `port=`; line `a,b,c,d,e\n` ints 0-180 @115200), `pca9685` (channels 0-4).
- UDP driver: `python -m robot.run_udp --backend sim --port 14043` accepts `{"fingers":[5]}` JSON (mock_stream / forward_to_jetson format).
- Retargeting (`robot/retarget.py`): glove 5 floats (1=closed) -> Inspire RH56 6 ints 0..1000 [pinky,ring,middle,index,thumb_bend,thumb_rot], 1000=open. `make_hand("inspire", host=..., dry=False, close_cap=0.6)` (Modbus TCP, registers UNVERIFIED on hardware). CLI: `python -m robot.run_udp --backend inspire [--live --host IP --close-cap 0.6]`. `close_cap` = max closure, hook for fragile-grasp assist (#14).
- Two gloves (`Rokoko/src/rgmp_client.py`): single-hand stream unchanged on 14043 `{"fingers":[5],"t":..,"src":"rokoko","hand":"left|right"}` (choose with `--hand`). Bimanual: `--bimanual-port 14053` sends `{"left":[5]|null,"right":[5]|null,"t":epoch_s}`; a hand is null until that glove has been seen/calibrated. Finger order thumb,index,middle,ring,little; 0=open, 1=closed.
- Bimanual consumers (`robot/parse.py: parse_hands`): robot.run_udp and demo/dashboard accept both the single-hand and bimanual UDP formats. `python -m robot.run_udp --port 14053 --hand left|right` picks the glove for a robot hand; `demo/run_demo.sh --bimanual --hand left`. Dashboard shows left (magenta/dashed) and right (cyan) together.
- Grasp assist wired: `python -m robot.run_udp --assist cup|egg|can` (open-loop cap from ml/grasp_assist.py); `demo/run_demo.sh --assist egg`. Force feedback: pass `force=` to GraspAssist.apply once a sensor exists.

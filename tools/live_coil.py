"""Live glove + Coil check, no take: prints once per second, per hand, what the gloves see. Ctrl+C to stop.
  py -3.11 tools/live_coil.py
Per hand over the last second: samples (rate), Coil present %, wrist position present %, EMF saturation %, flip-decided %, wrist position
(m, Coil frame) and distance from the Coil, index/middle finger angle. Walk towards the Coil with the gloves on and watch Coil % go to 100."""
import os, socket, struct, sys, time, json
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
import analyze_takes as A

R = A.R


def main(host="127.0.0.1", port=12276):
    s = socket.create_connection((host, port), timeout=5); s.settimeout(1.0)
    buf, lay, hands, win, t_last, used = b"", {}, {}, {}, time.time(), {}
    print("connesso al driver Rokoko: muovi i guanti / avvicinati al Coil (Ctrl+C per uscire)")
    while True:
        try:
            c = s.recv(65536)
            if not c: print("driver chiuso"); return
            buf += c
        except socket.timeout:
            pass
        while len(buf) >= 8:
            typ, ln = struct.unpack_from("<II", buf, 0)
            if len(buf) < 8 + ln: break
            p, buf = buf[8:8 + ln], buf[8 + ln:]
            if typ == 1:
                sd = json.loads(p.decode("utf-8")); d = sd["device_id"]; lay[d] = R.build_layout(sd); hands[d] = A.name_device(sd, used) + f" [{d}]"
            elif typ == 2:
                d = struct.unpack_from("<I", p, 0)[0]
                if d not in lay: continue
                _, name, ts, items = R.decode(lay[d], p)
                if name != "default": continue
                ang, pos, flags = [0.0] * 5, None, 0
                for st, v in items:
                    tf, mt, ref = st["target_frame"], st["measure_type"], st.get("reference_frame")
                    if mt == "TRANSFORM" and tf.endswith("finger_sensor"): ang[A.FRAMES.index(tf.split("_")[0])] = R.angle_of(R.quat(v))
                    elif mt == "TRANSFORM" and tf == "arm_sensor" and ref == "coil_pro": pos = v[:3]
                    elif mt == "STATUS_FLAGS" and tf == "arm_sensor": flags = int(v[0])
                win.setdefault(hands[d], []).append((ang, pos, flags))
        if time.time() - t_last >= 1.0:
            dt = time.time() - t_last; t_last = time.time(); line = []
            if not win: line.append("nessun dato dai guanti (accesi? driver con --auto-stream-usb?)")
            for h, rows in sorted(win.items()):
                n = len(rows); fl = np.array([r[2] for r in rows])
                P = [r[1] for r in rows if r[1]]; pos = np.mean(P, 0) if P else None
                coil, sat, flip = ((fl >> 9) & 1).mean(), ((fl >> 8) & 1).mean(), ((fl >> 10) & 1).mean()
                fing = np.mean([r[0] for r in rows], 0)
                ps = f"pos {np.round(pos, 2).tolist()} dist {np.linalg.norm(pos):.2f} m" if pos is not None else "pos --"
                warn = "  <-- COIL NON VISTO" if coil < 0.9 else ("  <-- SATURO: troppo vicino" if sat > 0.05 else "")
                line.append(f"{h:5s} {n / dt:5.0f} Hz | Coil {coil:4.0%} pos {len(P) / n:4.0%} sat {sat:4.0%} flip {flip:4.0%} | {ps} | indice {fing[1]:.2f} medio {fing[2]:.2f} rad{warn}")
            print(time.strftime("%H:%M:%S"), " || ".join(line), flush=True); win = {}


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: pass
    except OSError as e: print(f"driver non raggiungibile su 127.0.0.1:12276 ({e}): avvia rokoko-sdk --auto-stream-usb")

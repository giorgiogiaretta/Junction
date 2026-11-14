"""Which glove is on the head? Run once after mounting the third glove on the GoPro / head (writes data/devices.json).
  py -3.11 tools/identify_head.py
For 8 s: keep the HEAD STILL and open/close BOTH HANDS (fists) 3-4 times. The glove whose fingers move least is the head one.
Everything downstream (take.py data check, episodes, live_coil.py) then calls it "head": head_wrist_pos / head_wrist_quat = camera pose."""
import json, os, socket, struct, sys, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
import analyze_takes as A

R = A.R


def main(secs=8.0):
    s = socket.create_connection(("127.0.0.1", 12276), timeout=5); s.settimeout(0.5)
    print(f"Testa FERMA, apri e chiudi a pugno ENTRAMBE le mani 3-4 volte per {secs:.0f} secondi... VIA")
    buf, lay, info, rows, t0 = b"", {}, {}, {}, time.time()
    while time.time() - t0 < secs:
        try: buf += s.recv(65536)
        except socket.timeout: pass
        while len(buf) >= 8:
            typ, ln = struct.unpack_from("<II", buf, 0)
            if len(buf) < 8 + ln: break
            p, buf = buf[8:8 + ln], buf[8 + ln:]
            if typ == 1:
                sd = json.loads(p.decode("utf-8")); d = sd["device_id"]; lay[d] = R.build_layout(sd); info[d] = (sd.get("device_info") or {}).get("hand", "?")
            elif typ == 2:
                d = struct.unpack_from("<I", p, 0)[0]
                if d not in lay: continue
                _, name, ts, items = R.decode(lay[d], p)
                if name != "default": continue
                ang, pos = [0.0] * 5, None
                for st, v in items:
                    if st["measure_type"] == "TRANSFORM" and st["target_frame"].endswith("finger_sensor"): ang[A.FRAMES.index(st["target_frame"].split("_")[0])] = R.angle_of(R.quat(v))
                    elif st["measure_type"] == "TRANSFORM" and st["target_frame"] == "arm_sensor" and st.get("reference_frame") == "coil_pro": pos = v[:3]
                rows.setdefault(d, []).append((ang, pos))
    print()
    if len(rows) < 3: sys.exit(f"vedo {len(rows)} guanti ({ {d: info.get(d) for d in rows} }): servono 3 (2 mani + 1 in testa). Accendili e riprova.")
    stat = {}
    for d, r in rows.items():
        a = np.array([x[0] for x in r]); fl = a[:, 1:].mean(1); P = np.array([x[1] for x in r if x[1]])
        stat[d] = {"hand_label": info.get(d), "samples": len(r), "finger_span_rad": round(float(np.percentile(fl, 95) - np.percentile(fl, 5)), 2),
                   "pos": np.round(P.mean(0), 2).tolist() if len(P) else None}
        print(f"  device {d} ({info.get(d)}): campioni {len(r)}, movimento dita {stat[d]['finger_span_rad']} rad, posizione {stat[d]['pos']}")
    head = min(stat, key=lambda d: stat[d]["finger_span_rad"])
    spans = sorted(v["finger_span_rad"] for v in stat.values())
    if spans[1] < 0.3: print("  ATTENZIONE: anche un'altra mano si e' mossa poco: hai chiuso i pugni? Riprova se il risultato e' sbagliato.")
    names = A.device_names(); names = {k: v for k, v in names.items() if v != "head"}; names[str(head)] = "head"
    json.dump(names, open(A.DEVICES, "w"), indent=1)
    print(f"\nGuanto in TESTA = device {head} (etichetta guanto '{info.get(head)}'). Scritto {os.path.normpath(A.DEVICES)}")


if __name__ == "__main__":
    main()

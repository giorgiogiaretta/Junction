"""Guided block of grasp takes: the program tells you what to do (screen + beeps), you only press Enter at the end of each take.
  py -3.11 Rokoko/src/guided.py --obj ball --plan good          (5 good grasps of the stress ball)
  py -3.11 Rokoko/src/guided.py --obj egg  --plan fail          (5 deliberate failures: drop, slip, drop, slip, miss)
  options: --n 5 --hand R (right glove on the hand, LEFT glove on the head) --cam 1 (DJI) --operator giorgio --plan crush (egg: 1 crushed)
Same files/labels as take.py (series O): data/raw/take_NN.rgmp, data/video/take_NN.mp4, data/raw/takes.jsonl.
At the end of a take: Enter = the planned outcome; or type C/S/X/M (dropped/slipped/crushed/missed) if it went differently, N = discard."""
import argparse, json, os, socket, struct, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_takes import parse

try:
    import winsound
    beep = lambda f=880, ms=150: winsound.Beep(f, ms)
except Exception:
    beep = lambda f=880, ms=150: print("\a", end="", flush=True)

H = struct.Struct("<dI")
RAW = "data/raw"; LOG = f"{RAW}/takes.jsonl"
OBJ = {"ball": ("stress_ball", "la PALLINA"), "can": ("can", "la LATTINA"), "egg": ("egg", "l'UOVO")}
CODES = {"": None, "C": "dropped", "S": "slipped", "X": "crushed", "M": "missed", "N": "discard", "O": "ok"}
# what to do in the 'hold' phase for each planned outcome
FAIL = {"ok": "SOLLEVALO di 15 cm e TIENILO FERMO",
        "dropped": "SOLLEVALO di 10 cm poi APRI la mano: lascialo CADERE",
        "slipped": "SOLLEVALO e allenta piano le dita: lascialo SCIVOLARE",
        "missed": "MANCA la presa: chiudi la mano ACCANTO all'oggetto, non prenderlo",
        "crushed": "STRINGI FORTE fino a romperlo / schiacciarlo"}
PLANS = {"good": ["ok"] * 5, "fail": ["dropped", "slipped", "dropped", "slipped", "missed"], "crush": ["crushed"]}
LEAD, TAIL = 3.5, 1.0   # sync fist window 0.5-2.5 s, look at 3.5 s


def check(path, head):
    try: rows = parse(path)
    except Exception as e: print(f"  ! controllo dati non riuscito: {e}"); return False
    ok = True
    for h in ("right", "left"):
        r = rows.get(h, [])
        if len(r) < 20: print(f"  !!! manca il guanto {h}{' (TESTA)' if h == head else ''}"); ok = False; continue
        n = len(r); coil = sum((x[3] >> 9) & 1 for x in r) / n; sat = sum((x[3] >> 8) & 1 for x in r) / n; pos = sum(1 for x in r if x[2]) / n
        bad = coil < 0.9 or pos < 0.9 or sat > 0.05
        print(f"  {'TESTA' if h == head else 'MANO '} ({h}): Coil {coil:.0%}, posizione {pos:.0%}, saturazione {sat:.0%}" + ("   <-- !!!" if bad else "  ok"))
        ok = ok and not bad
    return ok


def step(t0, at, text, f=880):
    while time.time() - t0 < at: time.sleep(0.02)
    beep(f); print(f"\n   [{at:4.1f}s]  >>> {text}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obj", required=True, choices=list(OBJ)); ap.add_argument("--plan", default="good", choices=list(PLANS)); ap.add_argument("--n", type=int)
    ap.add_argument("--hand", default="R", choices=["R", "L"]); ap.add_argument("--cam", type=int, default=int(os.environ.get("CAM", "1")))
    ap.add_argument("--operator", default=os.environ.get("OPERATOR", "giorgio"))
    a = ap.parse_args()
    plan = PLANS[a.plan]; plan = (plan * 10)[:a.n] if a.n else plan
    obj, name = OBJ[a.obj]; head = "left" if a.hand == "R" else "right"; mano = "DESTRA" if a.hand == "R" else "SINISTRA"
    os.makedirs(RAW, exist_ok=True)
    from cam import CamRecorder
    cam = CamRecorder(a.cam); print(f"camera {a.cam}: {cam.w}x{cam.h} | mano {mano}, guanto {head} in testa | oggetto {name} | piano {plan}")
    input(f"\nMetti {name} sul segno davanti a te, mano {mano} a riposo sul tavolo. Invio = INIZIA il blocco di {len(plan)} take ")
    i = 0
    while i < len(plan):
        want = plan[i]
        takes = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
        n = max([t["take"] for t in takes], default=0) + 1; path = f"{RAW}/take_{n:02d}.rgmp"
        print(f"\n================ TAKE {i + 1}/{len(plan)} (n. {n}) - {name} - obiettivo: {want.upper()} ================")
        for k in (3, 2, 1): print(f"   parte tra {k}...", flush=True); time.sleep(1)
        sock = socket.create_connection(("127.0.0.1", 12276)); stop = threading.Event(); t0 = time.time(); cam.start(n)
        def rec():
            with open(path, "wb") as f:
                while not stop.is_set():
                    try: b = sock.recv(65536)
                    except OSError: break
                    if not b: break
                    f.write(H.pack(time.time() - t0, len(b)) + b)
        th = threading.Thread(target=rec, daemon=True); th.start()
        step(t0, 0.5, "REC. PUGNO DI SCATTO davanti alla camera (sync)", 1200)
        step(t0, 2.5, f"mano {mano} A RIPOSO sul tavolo, ferma")
        step(t0, 3.5, f"GUARDA {name} (1 secondo, testa ferma)")
        step(t0, 5.0, f"PRENDI {name} LENTAMENTE con pollice + indice + medio")
        step(t0, 8.5, FAIL[want])
        if want == "ok": step(t0, 11.5, f"POSA {name} sul segno e APRI la mano")
        else: step(t0, 11.5, f"rimetti {name} sul segno (se puoi) e apri la mano")
        step(t0, 13.5, "MANO A RIPOSO, FERMA 2 secondi", 660)
        step(t0, 15.5, "fine: premi Invio", 440)
        r = input("   Invio = esito " + want.upper() + "  |  oppure C caduto, S scivolato, X schiacciato, M mancato, O ok, N annulla: ").strip().upper()
        v = cam.stop(); stop.set(); t1 = time.time(); sock.close(); th.join(timeout=2)
        out = CODES.get(r, None) or want
        if out == "discard":
            for f in (path, f"data/video/take_{n:02d}.mp4", f"data/video/take_{n:02d}_frames.json"):
                if os.path.exists(f): os.remove(f)
            print("   take annullata: la rifacciamo"); continue
        rec_ = {"take": n, "series": "O", "file": path, "t_start": t0, "t_stop": t1, "t_mark": None, "lead_s": LEAD, "tail_trim_s": TAIL, "video": (v or {}).get("video"),
                "pos_id": None, "hand_used": a.hand, "object": obj, "outcome": out, "planned_outcome": want, "success": out == "ok", "operator": a.operator,
                "head_glove": head, "cam_pos": "head", "gopro_sync": False, "guided": True, "chunks": None, "bytes": os.path.getsize(path)}
        open(LOG, "a").write(json.dumps(rec_) + "\n")
        print(f"   salvata take {n:02d}: {t1 - t0:.1f}s, esito {out}")
        if not check(path, head):
            if input("   !!! dati non buoni: N = annulla e rifai, Invio = tienila comunque: ").strip().upper() == "N":
                for f in (path, f"data/video/take_{n:02d}.mp4", f"data/video/take_{n:02d}_frames.json"):
                    if os.path.exists(f): os.remove(f)
                open(LOG, "w").write("".join(json.dumps(t) + "\n" for t in takes)); print("   annullata, la rifacciamo"); continue
        i += 1
        if i < len(plan): print(f"\n   rimetti {name} sul segno, mano a riposo: la prossima parte da sola"); time.sleep(3)
    cam.close(); beep(1000, 400); print(f"\nBLOCCO FINITO: {len(plan)} take di {name}.")


if __name__ == "__main__":
    main()

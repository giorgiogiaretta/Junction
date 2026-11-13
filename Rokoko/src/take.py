"""Take recorder with on-screen instructions. One raw RGMP file per take + log data/raw/takes.jsonl.
Run:  python Rokoko/src/take.py        (driver rokoko-sdk --auto-stream-usb must be running)
Menu: A B C D E = choose series (shows instructions), Enter = repeat last series, L = list, U = undo (delete) last take, Q = quit.
Series E = calibration (5 s flat open hand, then 5 s tight fist; both gloves) -> python Rokoko/src/calib.py.
No markers. Every take has a 2 s lead-in after START (lead_s) and its last second (Invio to stop) is dropped downstream (tail_trim_s); episodes.py applies both.
"""
import json, os, socket, threading, time

H = __import__("struct").Struct("<dI")
RAW = "data/raw"; LOG = f"{RAW}/takes.jsonl"
os.makedirs(RAW, exist_ok=True)
S = {
 "A": ("Cubo rigido", 10, [
   "Parti con le mani a riposo, davanti al Coil Pro (non attaccato al cubo).",
   "Avvicina la mano all'oggetto rigido (libro/cubo) sul tavolo.",
   "Afferralo con decisione (presa a mano piena).",
   "Sollevalo di ~20 cm, tienilo 2 secondi, riposalo, torna a riposo."]),
 "B": ("Fragile / uovo", 10, [
   "Stesso setup, con un bicchiere di carta vuoto (o oggetto delicato).",
   "Avvicina la mano LENTAMENTE.",
   "Presa a pinza: pollice + indice + medio (tripod).",
   "Solleva dolcemente senza schiacciare, riposa, torna a riposo."]),
 "C": ("HandOff: correzione errore (CRITICO)", 10, [
   "Avvicina la mano all'oggetto in modo VOLUTAMENTE SBAGLIATO (traiettoria storta o mano mezza chiusa).",
   "Resta 2-3 secondi nell'errore (senza segnali).",
   "Poi correggi la traiettoria, afferra bene e solleva.",
   "Riposa e torna a riposo. Poi Invio per STOP. (Nessun marker: l'inizio della correzione si ricava dai dati.)"]),
 "E": ("Calibrazione: mano aperta / pugno", 3, [
   "Entrambe le mani con i guanti, davanti a te.",
   "5 secondi: mano APERTA, piatta, dita tese e ferme.",
   "Poi 5 secondi: PUGNO stretto, tutte le dita chiuse e ferme. Poi Invio = STOP (nessun marker)."]),
 "F": ("Mani a riposo (rumore dei sensori)", 2, [
   "Entrambe le mani con i guanti appoggiate ferme sul tavolo, rilassate, senza muovere le dita.",
   "Resta fermo 10 secondi, poi Invio = STOP. Serve a misurare il rumore dei sensori a riposo."]),
 "G": ("Pollice: opposizione e pinza", 2, [
   "Entrambe le mani con i guanti davanti a te, palmi verso l'alto o di lato, mani ferme.",
   "Con il pollice tocca in sequenza la punta di indice, medio, anulare, mignolo (2 secondi ciascuno), poi riapri il pollice del tutto.",
   "Poi: pollice che si apre e si chiude da solo (flessione) per 5 volte. Invio = STOP. Serve per calibrare il pollice."]),
 "D": ("Rumore / movimenti spuri", 5, [
   "Fai movimenti a caso: grattarti la testa, mano che trema, dita a caso.",
   "Nessun compito preciso: serve a insegnare cosa scartare."]),
}
LEAD = 2.0   # seconds between START (Invio) and the move: you get into position
TAIL = 1.0   # last second (pressing Invio to stop) is discarded downstream
def load():
    return [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
def counts():
    c = {k: 0 for k in S}
    for t in load(): c[t["series"]] = c.get(t["series"], 0) + 1
    return c
def menu():
    c = counts(); print("\n=== SERIE (fatte/obiettivo) ===")
    for k, (n, goal, _) in S.items(): print(f"  [{k}] {n:<38} {c[k]}/{goal}")
    print("  [Invio] ripeti ultima   [L] elenco   [U] annulla ultima presa   [Q] esci")
def show(k):
    n, goal, steps = S[k]; print(f"\n--- Serie {k}: {n} (presa {counts()[k]+1}/{goal}) ---")
    for i, s in enumerate(steps, 1): print(f"  {i}. {s}")
last = "A"
while True:
    menu(); c = input("Scelta: ").strip().upper()
    if c == "Q": break
    if c == "L":
        for t in load(): print(f"  take {t['take']:02d} serie {t['series']} {t['t_stop']-t['t_start']:.0f}s {t['bytes']//1024} KB" + (" [mark]" if t.get("t_mark") else ""))
        continue
    if c == "U":
        ts = load()
        if not ts: print("  niente da annullare"); continue
        t = ts[-1]
        if input(f"  cancello take {t['take']:02d} (serie {t['series']})? s/N: ").strip().lower() == "s":
            os.remove(t["file"]); open(LOG, "w").write("".join(json.dumps(x) + "\n" for x in ts[:-1])); print("  cancellata")
        continue
    if c in S: last = c
    elif c != "": print("  scelta non valida"); continue
    show(last)
    pos_id = input("Posizione oggetto (P1-P5 segnata sul tavolo, Invio = salta): ").strip().upper() or None if last in ("A", "B", "C") else None
    n = len(load()) + 1; path = f"{RAW}/take_{n:02d}.rgmp"
    input("Pronto? Invio = START (poi hai 2 secondi per metterti in posizione) ")
    sock = socket.create_connection(("127.0.0.1", 12276)); stop = threading.Event(); cnt = [0]; t0 = time.time()
    def rec():
        with open(path, "wb") as f:
            while not stop.is_set():
                try: b = sock.recv(65536)
                except OSError: break
                if not b: break
                f.write(H.pack(time.time() - t0, len(b)) + b); cnt[0] += 1
    th = threading.Thread(target=rec, daemon=True); th.start()
    print(f"  >>> REC {path}  - mettiti in posizione: ", end="", flush=True)
    for k in range(int(LEAD), 0, -1): print(f"{k}... ", end="", flush=True); time.sleep(1)
    print("VIA! (fai il movimento, poi Invio = STOP)")
    tm = None
    input("  Invio = STOP ")
    stop.set(); t1 = time.time(); sock.close(); th.join(timeout=2)
    rec_ = {"take": n, "series": last, "file": path, "t_start": t0, "t_stop": t1, "t_mark": tm, "lead_s": LEAD, "tail_trim_s": TAIL, "pos_id": pos_id, "chunks": cnt[0], "bytes": os.path.getsize(path)}
    open(LOG, "a").write(json.dumps(rec_) + "\n")
    print(f"  salvata take {n:02d}: {t1-t0:.1f}s, {rec_['bytes']//1024} KB")

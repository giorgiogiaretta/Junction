"""Take recorder with on-screen instructions. One raw RGMP file per take + log data/raw/takes.jsonl.
Run:  python Rokoko/src/take.py        (driver rokoko-sdk --auto-stream-usb must be running)
Menu: A B C D E = choose series (shows instructions), Enter = repeat last series, L = list, U = undo (delete) last take, Q = quit.
Series O = object grasp for the G1 (egg / stress_ball / can) with the outcome asked after STOP; P = HandOff with object; S = camera sync.
Env: CAM=<idx> camera, CAMPOS=head|fixed, OPERATOR=<name>.
Series E = calibration (5 s flat open hand, then 5 s tight fist; both gloves) -> python Rokoko/src/calib.py.
No markers. Every take has a 2 s lead-in after START (lead_s) and its last second (Invio to stop) is dropped downstream (tail_trim_s); episodes.py applies both.
"""
import json, os, socket, sys, threading, time

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
 "H": ("Quadrato: lattina nei 4 angoli (senso orario)", 10, [
   "Lattina Coca-Cola vuota sul marker IN BASSO A SINISTRA. Mani FERME sul tavolo (hai 2 s dopo Invio per metterti in posizione).",
   "Prendi la lattina e portala: BASSO-SX -> ALTO-SX -> ALTO-DX -> BASSO-DX -> di nuovo BASSO-SX (senso orario, 4 spostamenti).",
   "In ogni angolo POSA la lattina, lasciala un attimo (mano aperta), riprendila e vai al successivo. Muovi sempre con la stessa mano.",
   "Finito: rimetti le mani FERME sul tavolo e solo dopo premi Invio = STOP (l'ultimo secondo viene scartato)."]),
 "I": ("Scala: righello (linee rette di distanza nota)", 2, [
   "Appoggia un foglio A4 sul tavolo (lato lungo 29,7 cm) davanti a te. Metti il polso (cinturino) su un estremo del lato lungo, mano piatta, ferma. Hai 3 s dopo Invio (pugno di sync per la GoPro, poi in posizione).",
   "Scorri il polso in linea retta fino all'altro estremo (29,7 cm), fermati 2 s, torna indietro: 3 andate e ritorni sinistra-destra.",
   "Poi 3 andate e ritorni AVANTI-INDIETRO (lato corto 21 cm, se usi lo stesso foglio girato), poi alza la mano in verticale di 20 cm con un righello accanto, fermati 2 s, riabbassa: 3 volte.",
   "Mani ferme sul tavolo, poi Invio = STOP. Fai 1 presa con la destra e 1 con la sinistra (indica la mano quando la chiede)."]),
 "J": ("Tocca i 4 angoli (senza lattina)", 4, [
   "Nessun oggetto. Mano piatta, dita puntate in avanti (verso il bordo opposto del tavolo). Appoggia la PUNTA DELL'INDICE al centro della X in basso a sinistra. Hai 3 s dopo Invio (pugno di sync per la GoPro, poi in posizione).",
   "Fermo 2 secondi, poi sposta la mano (sempre con la STESSA postura) sulla X in alto a sinistra, ferma 2 s; poi alto-dx, ferma 2 s; poi basso-dx, ferma 2 s; poi di nuovo basso-sx, ferma 2 s. Sono 5 tocchi = 1 giro.",
   "Fai 2 giri di fila senza riposare la mano a meta'. Poi mano ferma sul tavolo e Invio = STOP. 2 prese per mano (indica R/L quando lo chiede).",
   "Importante: stessa postura e stessa punta dell'indice in tutti i tocchi; la mano non deve ruotare."]),
 "O": ("Presa oggetto: uovo / pallina / lattina (G1)", 60, [
   "Oggetto sul segno davanti a te, mano a riposo sul tavolo, camera in testa accesa (l'oggetto deve essere inquadrato). Hai 3 s dopo Invio (pugno di sync per la GoPro, poi in posizione).",
   "Guarda l'oggetto 1 secondo (serve alla camera), poi avvicina la mano e afferralo con pollice + indice + medio.",
   "Sollevalo di ~15 cm, tienilo 2 secondi, riposalo sul segno, apri la mano e torna a riposo.",
   "Fallimenti VOLUTI (quando richiesti): fallo cadere, fallo scivolare, stringi troppo, manca la presa. Dopo STOP dichiari l'esito."]),
 "P": ("HandOff con oggetto: errore poi correzione", 15, [
   "Come la serie O, ma la prima presa e' VOLUTAMENTE sbagliata (mano storta, troppo aperta o troppo chiusa) per 2-3 secondi.",
   "Poi correggi, afferra bene, solleva, riposa. Esito = quello finale."]),
 "K": ("Calibrazione assi braccio (G1), a inizio sessione", 2, [
   "Una mano alla volta (indica R/L). Polso davanti al petto, gomito piegato, mano ferma 2 s = RIPOSO. Hai 3 s dopo Invio (pugno di sync per la GoPro, poi in posizione).",
   "AVANTI 20 cm in linea retta (verso il tavolo), fermo 2 s, torna al riposo, fermo 2 s.",
   "SINISTRA 20 cm, fermo 2 s, torna, fermo 2 s. Poi SU 20 cm, fermo 2 s, torna, fermo 2 s. Poi Invio = STOP.",
   "Non ruotare la mano. Rifai la serie K se sposti il Coil."]),
 "S": ("Sincronia camera-guanto", 2, [
   "Mano con il guanto ben visibile alla camera, ferma 2 s.",
   "Poi 3 schiocchi veloci: chiudi a pugno di scatto e riapri, con 2 s di pausa tra uno e l'altro. Serve a misurare il ritardo della camera."]),
 "D": ("Rumore / movimenti spuri", 5, [
   "Fai movimenti a caso: grattarti la testa, mano che trema, dita a caso.",
   "Nessun compito preciso: serve a insegnare cosa scartare."]),
}
OBJ = {"U": "egg", "P": "stress_ball", "L": "can"}
OUTCOMES = {"": "ok", "C": "dropped", "S": "slipped", "X": "crushed", "M": "missed", "N": "discard"}
OPERATOR = os.environ.get("OPERATOR", "giorgio")
CAMPOS = os.environ.get("CAMPOS", "head")   # where the camera is: head (egocentric mount) or fixed
LEAD = 3.0   # seconds between START (Invio) and the move: sync fist for the GoPro, then get into position (was 2.0 before take 61)
GOPRO = os.environ.get("GOPRO", "1") not in ("", "0")   # external head camera recording continuously: per-take sync fist in the lead-in
TAIL = 1.0   # last second (pressing Invio to stop) is discarded downstream
CAMIDX = os.environ.get("CAM")   # optional: CAM=1 -> also record the camera (Rokoko/src/cam.py), same PC clock
cam = None
if CAMIDX not in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cam import CamRecorder
    cam = CamRecorder(int(CAMIDX)); print(f"camera {CAMIDX} ready: {cam.w}x{cam.h}")
def check(path):
    """Instant data check after every take: gloves streaming, Coil present, flips/saturation. Warn loudly, never block."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from analyze_takes import parse, device_names
        rows = parse(path)
    except Exception as e: print(f"  ! controllo dati non riuscito: {e}"); return
    if not any(len(r) > 20 for r in rows.values()): print("  !!! ATTENZIONE: nessun dato dai guanti in questa take (driver/guanti spenti?). Annullala con U."); return
    if "head" in device_names().values() and len(rows.get("head", [])) < 20: print("  !!! ATTENZIONE: manca il guanto in TESTA (posizione camera). Annulla con U e controlla.")
    extra = [h for h in rows if h not in ("left", "right", "head") and len(rows[h]) > 20]
    if extra: print(f"  !!! guanti non identificati {extra}: lancia py -3.11 tools/identify_head.py")
    for h, r in rows.items():
        if len(r) < 20: continue
        fl = [x[3] for x in r]; n = len(fl)
        coil = sum((f >> 9) & 1 for f in fl) / n; sat = sum((f >> 8) & 1 for f in fl) / n; pos = sum(1 for x in r if x[2]) / n
        msg = f"  {h}: {n} campioni, Coil presente {coil:.0%}, posizione {pos:.0%}, saturazione {sat:.0%}"
        print(msg + ("   <-- !!! COIL ASSENTE / POSIZIONE MANCANTE" if coil < 0.9 or pos < 0.9 else "") + ("   <-- !!! SATURAZIONE (troppo vicino al Coil?)" if sat > 0.05 else ""))
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
            os.remove(t["file"]); [os.remove(f) for f in (f"data/video/take_{t['take']:02d}.mp4", f"data/video/take_{t['take']:02d}_frames.json") if os.path.exists(f)]; open(LOG, "w").write("".join(json.dumps(x) + "\n" for x in ts[:-1])); print("  cancellata")
        continue
    if c in S: last = c
    elif c != "": print("  scelta non valida"); continue
    show(last)
    pos_id = input("Posizione oggetto (P1-P5 segnata sul tavolo, Invio = salta): ").strip().upper() or None if last in ("A", "B", "C") else None
    hand_used = (input("Mano che muove la lattina (R/L): ").strip().upper() or None) if last in ("H", "I", "J", "K") else None
    obj = None; operator = None
    if last in ("O", "P"):
        while obj is None: obj = OBJ.get(input("Oggetto: U = uovo, P = pallina, L = lattina: ").strip().upper())
        hand_used = input("Mano (R/L, Invio = R): ").strip().upper() or "R"
        operator = input(f"Operatore (Invio = {OPERATOR}): ").strip() or OPERATOR
    n = len(load()) + 1; path = f"{RAW}/take_{n:02d}.rgmp"
    input("Pronto? Invio = START (poi 3 s: pugno di sync e posizione) ")
    sock = socket.create_connection(("127.0.0.1", 12276)); stop = threading.Event(); cnt = [0]; t0 = time.time()
    if cam: cam.start(n)
    def rec():
        with open(path, "wb") as f:
            while not stop.is_set():
                try: b = sock.recv(65536)
                except OSError: break
                if not b: break
                f.write(H.pack(time.time() - t0, len(b)) + b); cnt[0] += 1
    th = threading.Thread(target=rec, daemon=True); th.start()
    if GOPRO: print("  >>> SYNC: guarda la mano DESTRA e chiudila a PUGNO DI SCATTO una volta (la GoPro la deve vedere), poi in posizione")
    print(f"  >>> REC {path}  - mettiti in posizione: ", end="", flush=True)
    for k in range(int(LEAD), 0, -1): print(f"{k}... ", end="", flush=True); time.sleep(1)
    print("VIA! (fai il movimento, poi Invio = STOP)")
    tm = None
    input("  Invio = STOP ")
    vinfo = cam.stop() if cam else None
    stop.set(); t1 = time.time(); sock.close(); th.join(timeout=2)
    outcome = None
    if last in ("O", "P"):
        while outcome is None:
            outcome = OUTCOMES.get(input("Esito: Invio = OK, C = caduto, S = scivolato, X = schiacciato/rotto, M = presa mancata, N = annulla take: ").strip().upper())
        if outcome == "discard":
            os.remove(path); [os.remove(f) for f in (f"data/video/take_{n:02d}.mp4", f"data/video/take_{n:02d}_frames.json") if os.path.exists(f)]
            print("  take annullata"); continue
    rec_ = {"take": n, "series": last, "file": path, "t_start": t0, "t_stop": t1, "t_mark": tm, "lead_s": LEAD, "tail_trim_s": TAIL, "video": (vinfo or {}).get("video"), "pos_id": pos_id, "hand_used": hand_used, "object": ("coke_can_empty_standard_low" if last == "H" else obj), "outcome": outcome, "success": (None if outcome is None else outcome == "ok"), "operator": operator, "cam_pos": CAMPOS if cam else ("gopro_head" if GOPRO else None), "gopro_sync": GOPRO, "chunks": cnt[0], "bytes": os.path.getsize(path)}
    open(LOG, "a").write(json.dumps(rec_) + "\n")
    print(f"  salvata take {n:02d}: {t1-t0:.1f}s, {rec_['bytes']//1024} KB")
    check(path)

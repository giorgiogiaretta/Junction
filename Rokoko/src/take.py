"""Take recorder for the 35-take protocol. One raw RGMP file per take + a log with series/labels/times.
Run:  python Rokoko/src/take.py            (driver rokoko-sdk must be running)
Per take: type the series letter (A/B/C/D, or Enter = same as last), press Enter to START, Enter again to STOP.
'q' + Enter quits. Files: data/raw/take_01.rgmp ...   Log: data/raw/takes.jsonl (series, start/stop epoch, chunks).
No renaming needed: A=rigid cube x10, B=fragile x10, C=hand-off correction x10, D=noise x5.
"""
import json, os, socket, struct, threading, time

H = struct.Struct("<dI")
os.makedirs("data/raw", exist_ok=True)
existing = [f for f in os.listdir("data/raw") if f.startswith("take_") and f.endswith(".rgmp")]
n = len(existing); last = "A"
while True:
    s = input(f"\nTake {n+1:02d} series [A/B/C/D, Enter={last}, q=quit]: ").strip().upper()
    if s == "Q": break
    last = s or last; n += 1; path = f"data/raw/take_{n:02d}.rgmp"
    sock = socket.create_connection(("127.0.0.1", 12276)); stop = threading.Event(); cnt = [0]; t0 = time.time()
    def rec():
        with open(path, "wb") as f:
            while not stop.is_set():
                try: b = sock.recv(65536)
                except OSError: break
                if not b: break
                f.write(H.pack(time.time() - t0, len(b)) + b); cnt[0] += 1
    th = threading.Thread(target=rec, daemon=True); th.start()
    input(f"  >>> RECORDING {path} (series {last}). ACTION! Press Enter to STOP ")
    stop.set(); t1 = time.time(); sock.close(); th.join(timeout=2)
    with open("data/raw/takes.jsonl", "a") as lg:
        lg.write(json.dumps({"take": n, "series": last, "file": path, "t_start": t0, "t_stop": t1, "chunks": cnt[0], "bytes": os.path.getsize(path)}) + "\n")
    print(f"  saved take {n:02d}: {t1-t0:.1f}s, {os.path.getsize(path)//1024} KB")

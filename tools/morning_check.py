#!/usr/bin/env python3
"""Morning check for the robot/hackathon stack (draft by a delegate model, reviewed by Claude). Local only.
Prints an OK/WARN/FAIL table (one row per check) and exits with the number of FAILs. Everything is best-effort: missing drivers, cameras or GPU never raise.
No secrets are ever printed (env check shows only 'set' / 'missing').   python tools/morning_check.py [--tests]
"""
import argparse
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time

HOST = "127.0.0.1"
PORT = 12276
GB = 1024 ** 3
ENV_VARS = ["VERDA_INFERENCE_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY", "LLM_MODEL"]
results = []  # (check_name, status, detail)


def add(name, status, detail=""):
    results.append((name, status, detail))


def _run(cmd, timeout=15):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def read_exact(sock, n, deadline):
    buf = bytearray()
    while len(buf) < n:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deadline")
        sock.settimeout(remaining)
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed")
        buf.extend(chunk)
    return bytes(buf)


def check_port_and_gloves(window_s=4.0):
    try:
        sock = socket.create_connection((HOST, PORT), timeout=3)
    except OSError as e:
        return "FAIL", f"{HOST}:{PORT} unreachable ({type(e).__name__})"
    gloves, n_type1 = {}, 0
    try:
        deadline = time.monotonic() + window_s
        while True:
            try:
                hdr = read_exact(sock, 8, deadline)
            except (TimeoutError, ConnectionError):
                break
            ftype, length = struct.unpack("<II", hdr)
            if length > 5_000_000:
                return "WARN", f"frame too large ({length} B), protocol mismatch?"
            try:
                payload = read_exact(sock, length, deadline)
            except (TimeoutError, ConnectionError):
                break
            if ftype != 1:          # 1 = JSON stream definition, 2 = data
                continue
            n_type1 += 1
            try:
                obj = json.loads(payload.decode("utf-8", "replace"))
            except Exception:
                continue
            info = obj.get("device_info")
            gloves[obj.get("device_id", "__noid__")] = info.get("hand") if isinstance(info, dict) else obj.get("hand")
    finally:
        try:
            sock.close()
        except Exception:
            pass
    hands = sorted({h for h in gloves.values() if h in ("left", "right")})
    detail = f"{len(gloves)} glove(s), hands={hands or 'none'}, type1_frames={n_type1}"
    return ("OK", detail) if gloves else ("WARN", "port open, no gloves seen: " + detail)


def check_process():
    try:
        r = _run(["tasklist", "/FI", "IMAGENAME eq rokoko-sdk.exe"])
    except FileNotFoundError:
        return "WARN", "tasklist not found (non-Windows?)"
    except subprocess.TimeoutExpired:
        return "WARN", "tasklist timeout"
    return ("OK", "rokoko-sdk.exe running") if "rokoko-sdk.exe" in (r.stdout or "").lower() else ("FAIL", "rokoko-sdk.exe not running")


def check_cameras():
    try:
        import cv2
    except Exception as e:
        return "WARN", f"cv2 not importable ({type(e).__name__})"
    found = []
    for i in range(6):
        cap = None
        try:
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap is not None and cap.isOpened():
                found.append((i, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
        except Exception:
            pass
        finally:
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
    return ("OK", "; ".join(f"idx{i}={w}x{h}" for i, w, h in found)) if found else ("WARN", "no cameras on indices 0..5")


def check_gh():
    try:
        r = _run(["gh", "auth", "status"])
    except FileNotFoundError:
        return "WARN", "gh not installed / not on PATH"
    except subprocess.TimeoutExpired:
        return "WARN", "gh auth status timeout"
    return ("OK", "gh authenticated") if r.returncode == 0 else ("FAIL", f"gh auth status exit {r.returncode}")


def check_git():
    try:
        br = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if br.returncode != 0:
            return "FAIL", "not a git repository"
        branch = (br.stdout or "").strip() or "?"
        modified = len([l for l in (_run(["git", "status", "--porcelain"]).stdout or "").splitlines() if l.strip()])
        rev = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"])
        if rev.returncode == 0:
            parts = (rev.stdout or "").split()
            upstream = f"ahead {parts[0]}/behind {parts[1]}" if len(parts) >= 2 else "ahead/behind ?"
        else:
            upstream = "no upstream"
        return ("OK" if modified == 0 else "WARN"), f"branch={branch}, modified={modified}, {upstream}"
    except FileNotFoundError:
        return "WARN", "git not installed"
    except subprocess.TimeoutExpired:
        return "WARN", "git timeout"


def check_disk():
    try:
        free = shutil.disk_usage(".")[2]
    except Exception as e:
        return "WARN", f"disk_usage failed ({type(e).__name__})"
    return ("OK" if free / GB >= 20 else "WARN"), f"free {free / GB:.1f} GB"


def check_env():
    parts = [f'{k}={"set" if os.environ.get(k) else "missing"}' for k in ENV_VARS]
    return ("OK" if all(os.environ.get(k) for k in ENV_VARS) else "WARN"), ", ".join(parts)


def check_gpu():
    try:
        r = _run(["nvidia-smi", "--query-gpu=name,temperature.gpu,memory.used,memory.total", "--format=csv,noheader"])
    except FileNotFoundError:
        return "WARN", "nvidia-smi not found"
    except subprocess.TimeoutExpired:
        return "WARN", "nvidia-smi timeout"
    rows = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()] if r.returncode == 0 else []
    if not rows:
        return "WARN", f"no GPU reported (exit {r.returncode})"
    hot, parts = False, []
    for row in rows:
        cols = [c.strip() for c in row.split(",")]
        try:
            hot = hot or float(cols[1]) >= 80
        except (IndexError, ValueError):
            pass
        parts.append(f"{cols[0]} {cols[1] if len(cols) > 1 else '?'}C {cols[2] + '/' + cols[3] if len(cols) >= 4 else ''}".strip())
    return ("WARN" if hot else "OK"), " | ".join(parts)


def check_night(path="data/night/report.md"):
    if not os.path.isfile(path):
        return "WARN", "no night report"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = [next(f, "") for _ in range(8)]
        return "OK", f"age {(time.time() - os.path.getmtime(path)) / 60:.0f} min :: " + " | ".join(l.strip() for l in head if l.strip())[:300]
    except Exception as e:
        return "WARN", f"read failed ({type(e).__name__})"


def check_tests():
    try:
        r = _run([sys.executable, "-m", "pytest", "-q", "tests", "-x"], timeout=300)
    except subprocess.TimeoutExpired:
        return "FAIL", "pytest timeout (300s)"
    except Exception as e:
        return "WARN", f"pytest spawn failed ({type(e).__name__})"
    lines = [l for l in ((r.stdout or "") + (r.stderr or "")).splitlines() if l.strip()]
    return ("OK" if r.returncode == 0 else "FAIL"), f"exit {r.returncode}: {(lines[-1] if lines else '(no output)')[:160]}"


def main():
    ap = argparse.ArgumentParser(description="Morning health check")
    ap.add_argument("--tests", action="store_true", help="also run pytest -q tests -x")
    args = ap.parse_args()
    checks = [("port/gloves", check_port_and_gloves), ("process", check_process), ("cameras", check_cameras), ("gh auth", check_gh), ("git", check_git),
              ("disk", check_disk), ("env", check_env), ("gpu", check_gpu), ("night", check_night)]
    if args.tests:
        checks.append(("tests", check_tests))
    for name, fn in checks:
        try:
            status, detail = fn()
        except Exception as e:  # never crash the whole run
            status, detail = "FAIL", f"{type(e).__name__}: {e}"
        add(name, status, detail)
    w = max(len(n) for n, _, _ in results)
    print(f'\n{"CHECK":<{w}}  {"STATUS":<4}  DETAIL\n' + "-" * (w + 8 + 60))
    for n, s, d in results:
        print(f"{n:<{w}}  {s:<4}  {d}")
    n_fail = sum(1 for _, s, _ in results if s == "FAIL")
    n_warn = sum(1 for _, s, _ in results if s == "WARN")
    print(f"\nSUMMARY: {len(results) - n_fail - n_warn} OK, {n_warn} WARN, {n_fail} FAIL")
    return n_fail


if __name__ == "__main__":
    sys.exit(main())

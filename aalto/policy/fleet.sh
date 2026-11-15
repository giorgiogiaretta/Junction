#!/bin/bash
# Parallel sim evaluation on one box: N sim instances (own DDS domain + ports), one team policy server each.
#   bash fleet.sh sims-up "a b c d"       start sims (a = the default instance on 55555/55580/55560, domain 1)
#   bash fleet.sh servers-up "a b c d"    (re)start one team_aalto server per instance on 8000/8001/8002/8003
#   bash fleet.sh eval <task> <trials> "a b c d" <tag>   seeds: a 2000+, b 2100+, c 2200+, d 2300+ (logs /root/fleet/)
#   bash fleet.sh summary <tag>           mean score per task over every trial of that tag
#   bash fleet.sh down "b c d"            stop extra sims (never `pkill -f sim_main`)
# Everything is started with nohup / in the background: this script returns at once.
set -u
REPO=/root/aaltonomous-humanoid
F=/root/fleet; mkdir -p "$F"
source /root/miniforge3/etc/profile.d/conda.sh; conda activate isaac
cd "$REPO"

idx() { case $1 in a) echo 0;; b) echo 1;; c) echo 2;; d) echo 3;; *) echo "bad instance $1" >&2; exit 1;; esac; }
envs() {  # print the env of instance $1
    local i; i=$(idx "$1"); local base=$((55555 + 1000 * i))
    local dom=1; [[ $i -gt 0 ]] && dom=$((6 + i))
    echo "AALTO_DDS_DOMAIN=$dom AALTO_CAM_PORT_BASE=$base AALTO_SCENE_PORT=$((base + 25)) AALTO_RGBD_PORT=$((base + 5))" \
         "$([[ $i -gt 0 ]] && echo AALTO_INSTANCE=$1)"
}

cmd=${1:-}; shift || true
case "$cmd" in
sims-up)
    for n in $1; do
        env $(envs "$n") TASK=Aalto-Sort-G129-Dex3-Joint PYTHONPATH="$REPO" \
            nohup bash aaltonomous/sim/run_sim.sh > "$F/sim_$n.log" 2>&1 &
        echo "sim $n starting (log $F/sim_$n.log): $(envs "$n")"
        sleep 20   # stagger: shader cache + CPU spike at start
    done ;;
servers-up)
    for n in $1; do
        i=$(idx "$n"); port=$((8000 + i))
        pkill -f "TEAM_POLICY_PORT=$port" 2>/dev/null
        nohup env TEAM_POLICY_PORT=$port PYTHONPATH="$REPO" python -m team_aalto.policy_server > "$F/server_$n.log" 2>&1 &
        echo "server $n on :$port (log $F/server_$n.log)"
    done ;;
eval)
    task=$1; trials=$2; insts=$3; tag=$4
    for n in $insts; do
        i=$(idx "$n"); port=$((8000 + i)); seed=$((2000 + 100 * i))
        env $(envs "$n") PYTHONPATH="$REPO" nohup python -m aaltonomous.sim.evaluate --policy ws://localhost:$port \
            --team "${tag}_$n" --task "$task" --trials "$trials" --seed "$seed" > "$F/eval_${tag}_${task}_$n.log" 2>&1 &
        echo "eval $n: $task x$trials seeds $seed.. -> $F/eval_${tag}_${task}_$n.log"
    done ;;
summary)
    tag=$1
    python - "$tag" <<'PY'
import glob, json, sys, collections
tag = sys.argv[1]; agg = collections.defaultdict(list); clips = 0; bad = []
for f in glob.glob(f"/root/aaltonomous-humanoid/runs/eval/{tag}_*/eval.json"):
    for t in json.load(open(f)).get("trials", []):
        agg[t["task"]].append((t["score"], t["max_score"], t["n_correct"], t["n_objects"]))
        if not t.get("gate_ok"): bad.append((t["seed"], t.get("gate_why")))
for task, v in sorted(agg.items()):
    s, m, c, n = (sum(x[i] for x in v) for i in range(4))
    print(f"{task:14s} trials {len(v):3d}  score {s:+d}/{m} ({100*s/max(m,1):.0f} %)  objects correct {c}/{n}")
print("gate failures:", bad or "none")
PY
    ;;
down)
    for n in $1; do
        for pid in $(pgrep -f "^python .*aalto_sim_main.py"); do
            grep -qz "AALTO_INSTANCE=$n" /proc/$pid/environ 2>/dev/null && kill -INT "$pid" && echo "SIGINT sim $n ($pid)"
        done
    done ;;
*) sed -n 2,8p "$0" ;;
esac

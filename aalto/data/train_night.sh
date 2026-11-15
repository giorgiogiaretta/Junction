#!/bin/bash
# Night run: ACT (LeRobot) on zupermiez/g1_junction_drop_2 + drop_3, actions made safety-compliant,
# DDP on GPUs 1,2,3 (GPU 0 stays with the sim). Run it inside tmux; output goes to the terminal.
# Knobs (env): GPUS=1,2,3  STEPS=60000  BS=32 (per GPU)  RUN=act_drop23_safe
set -euo pipefail
. /root/lr/bin/activate
export HF_LEROBOT_HOME=/root/data/lerobot
W=/root/aalto_train
SPEC=/root/aaltonomous-humanoid/aaltonomous/interface/joint_spec.yaml
GPUS=${GPUS:-1,2,3}
NPROC=$(tr "," "\n" <<<"$GPUS" | wc -l)
STEPS=${STEPS:-60000}
BS=${BS:-32}
RUN=${RUN:-act_drop23_safe}
D=$HF_LEROBOT_HOME/aalto
say() { echo "=== [night $(date +%H:%M:%S)] $*"; }

say "1/4 download + merge drop_2 and drop_3 (skipped if already there)"
if [[ ! -d $D/g1_drop23 ]]; then
  python -c "from lerobot.datasets.lerobot_dataset import LeRobotDataset as L; [print(r, L(r).meta.total_frames) for r in ('zupermiez/g1_junction_drop_2', 'zupermiez/g1_junction_drop_3')]"
  [[ -d $D/drop3_rgb ]] || lerobot-edit-dataset --repo_id zupermiez/g1_junction_drop_3 --new_repo_id aalto/drop3_rgb \
      --operation.type remove_feature --operation.feature_names "['observation.images.head_depth', 'observation.tactile']"
  lerobot-edit-dataset --new_repo_id aalto/g1_drop23 --operation.type merge \
      --operation.repo_ids "['zupermiez/g1_junction_drop_2', 'aalto/drop3_rgb']"
fi

say "2/4 safe copy: real copy of meta/ and data/, hard links for videos (original stays untouched), retime actions"
if [[ ! -f $D/g1_drop23_safe/.retimed ]]; then
  rm -rf "$D/g1_drop23_safe"
  mkdir -p "$D/g1_drop23_safe"
  cp -r "$D/g1_drop23/meta" "$D/g1_drop23/data" "$D/g1_drop23_safe/"
  cp -al "$D/g1_drop23/videos" "$D/g1_drop23_safe/"
  python "$W/retime_actions.py" "$D/g1_drop23_safe" "$SPEC" | tee "$W/retime_report.txt"
  lerobot-edit-dataset --repo_id aalto/g1_drop23_safe --operation.type recompute_stats --operation.overwrite true
  touch "$D/g1_drop23_safe/.retimed"
fi

say "3/4 ACT on GPUs $GPUS ($NPROC procs, batch $BS per GPU, $STEPS steps) -> /root/runs/$RUN"
accelerate launch --multi_gpu --num_processes "$NPROC" --num_machines 1 --gpu_ids "$GPUS" \
    --mixed_precision no --dynamo_backend no \
  "$(which lerobot-train)" \
  --policy.type=act --dataset.repo_id=aalto/g1_drop23_safe \
  --policy.chunk_size=50 --policy.n_action_steps=50 \
  --batch_size="$BS" --steps="$STEPS" --num_workers=12 \
  --save_freq=10000 --log_freq=200 \
  --output_dir="/root/runs/$RUN" --job_name="$RUN" \
  --policy.device=cuda --policy.push_to_hub=false --trackio.enable=false

say "4/4 done: checkpoints in /root/runs/$RUN/checkpoints"

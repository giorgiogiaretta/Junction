# Team submission: organisers' classical planner + our instruction parser and real-colour HSV (team_aalto/).
# Build from the aaltonomous-humanoid repo root with team_aalto/ copied next to aaltonomous/:
#   docker build -f team.Dockerfile -t team-aalto/policy:v1 .
# Same base and pins as aaltonomous/docker/baseline.Dockerfile (CUDA 12.8 base, CPU-only, ~1.5 GB).
FROM nvidia/cuda:12.8.0-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir numpy==2.2.6 scipy==1.15.2 opencv-python-headless==4.10.0.84 pyyaml \
        msgpack "websockets>=12" pin==3.3.1
WORKDIR /app
COPY third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf third_party/xr_teleoperate/assets/g1/
COPY aaltonomous/__init__.py aaltonomous/
COPY aaltonomous/deploy/__init__.py aaltonomous/deploy/protocol.py aaltonomous/deploy/policy_server.py aaltonomous/deploy/
COPY aaltonomous/interface/__init__.py aaltonomous/interface/safety.py aaltonomous/interface/calibration.py \
     aaltonomous/interface/tasks.py aaltonomous/interface/joint_spec.yaml aaltonomous/interface/calibration.yaml \
     aaltonomous/interface/
COPY aaltonomous/scene/__init__.py aaltonomous/scene/scene.py aaltonomous/scene/scene.yaml aaltonomous/scene/
COPY aaltonomous/baselines/__init__.py aaltonomous/baselines/
COPY aaltonomous/baselines/classical/*.py aaltonomous/baselines/classical/config.yaml aaltonomous/baselines/classical/
COPY team_aalto/ team_aalto/
RUN python3 -c "from team_aalto.policy_server import TeamPolicy; p = TeamPolicy(); p.reset('Put the yellow objects in the left bin, the purple objects in the center bin and the orange objects in the right bin.')"
EXPOSE 8000
CMD ["python3", "-m", "team_aalto.policy_server"]

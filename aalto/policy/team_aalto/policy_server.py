"""Team policy server: organisers' classical planner (IK, safety-checked plans, 30 Hz threaded) + our
instruction parser + HSV ranges measured on the real robot's head camera (drop 2, cam_high).

    python -m team_aalto.policy_server        # :8000 (what the Docker image runs)

Per episode: instruction -> colour->bin mapping (team_aalto.instruction); perception looks ONLY for the colours
the instruction names, so orange/red or purple/blue never compete, and colours with no bin are left alone.
"""
from __future__ import annotations

import logging
import time

from aaltonomous.baselines.classical.policy_server import ClassicalServerPolicy
from aaltonomous.deploy.policy_server import serve

from .instruction import colour_mapping, parse

log = logging.getLogger("team_aalto")

# OpenCV HSV (H 0-180). Real values measured 2026-11-15 on drop 2 cam_high frames (13x13 px patches, p10-p90):
#   purple cube H 109-112 S ~150 V ~250 | yellow H 44-47 S 70-82 (washed out) | orange H 12-14 S 133-224 V 146-255
#   bins (NOT objects) H 4-6 S 175-198 V 100-107 | wooden table S < 35.
# Sim colours (scene.yaml) are covered too: yellow H ~26, blue H ~113, red H 0-8.
HSV = {
    "yellow": [[[18, 50, 110], [55, 255, 255]]],
    "purple": [[[100, 80, 70], [140, 255, 255]]],
    "orange": [[[9, 120, 125], [20, 255, 255]]],
    "red":    [[[0, 70, 70], [8, 255, 255]], [[170, 70, 70], [180, 255, 255]]],
    "blue":   [[[100, 70, 50], [130, 255, 255]]],
}


class TeamPolicy(ClassicalServerPolicy):
    name = "team-aalto-classical-lang"

    def reset(self, instruction, task=None, seed=None):
        job, t0 = self.pol._job, time.monotonic()
        while job is not None and job["result"] is None and time.monotonic() - t0 < 30.0:
            time.sleep(0.02)
        mapping = colour_mapping(instruction)
        self.pol.perception.cfg["hsv"] = {c: HSV[c] for c in mapping if c in HSV}
        self.pol.reset({"instruction": instruction, "mapping": mapping})
        log.info("reset task=%s seed=%s mapping=%s parsed=%s instruction=%r",
                 task, seed, mapping, parse(instruction), instruction)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    serve(TeamPolicy(), port=8000)

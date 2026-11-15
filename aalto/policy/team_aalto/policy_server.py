"""Team policy server: organisers' classical planner (IK, safety-checked plans, 30 Hz threaded) + our
instruction parser + HSV ranges measured on the real robot's head camera (drop 2, cam_high).

    python -m team_aalto.policy_server        # :8000 (what the Docker image runs)

Per episode: instruction -> colour->bin mapping (team_aalto.instruction); perception looks ONLY for the colours
the instruction names, so orange/red or purple/blue never compete, and colours with no bin are left alone.
"""
from __future__ import annotations

import logging
import os
import time

from aaltonomous.baselines.classical.policy_server import ClassicalServerPolicy
from aaltonomous.deploy.policy_server import serve

from .instruction import colour_mapping, parse

log = logging.getLogger("team_aalto")

# OpenCV HSV (H 0-180). Real values measured 2026-11-15 on drop 2 cam_high frames (13x13 px patches, p10-p90):
#   purple cube H 109-112 S ~150 V ~250 | yellow H 44-47 S 70-82 (washed out) | orange H 12-14 S 133-224 V 146-255
#   bins (NOT objects) H 4-6 S 175-198 V 100-107 | wooden table S < 35.
# Sim (our recoloured scene, rendered): purple H 124-132 S 24-74 (washed out), yellow H 28 S 58-77, orange H 20
#   S 143, bin walls H 11 S 167, bin floor H 16 S 114, mat S < 5. Ranges cover sim + real; flat table / mat blobs
#   that slip through are rejected by the planner's depth height check (height_range), bins by their 3D hulls.
HSV = {
    "yellow": [[[24, 45, 110], [55, 255, 255]]],   # real H 44-47, sim H 28: must NOT reach orange (sim H 20)
    "purple": [[[100, 30, 70], [140, 255, 255]]],
    "orange": [[[7, 110, 115], [23, 255, 255]]],   # real H 12-14, sim H ~15-20; real bins H 4-6 / V < 110
    "red":    [[[0, 70, 70], [8, 255, 255]], [[170, 70, 70], [180, 255, 255]]],
    "blue":   [[[100, 70, 50], [130, 255, 255]]],
}


class TeamPolicy(ClassicalServerPolicy):
    name = "team-aalto-classical-lang"

    def __init__(self, **kw):
        super().__init__(**kw)
        # Objects start >= 8 cm apart; a failed claw grasp pushes the object a few cm. With the default 3 cm the
        # pushed object looked new and was retried up to 7 times (sim seed 1001): count it as the same object.
        self.pol.cfg["policy"]["same_object_radius"] = 0.06

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
    serve(TeamPolicy(), port=int(os.environ.get("TEAM_POLICY_PORT", "8000")))

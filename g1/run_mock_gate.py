"""Run the organisers' mock runner WITHOUT the Pinocchio workspace check (pinocchio has no Windows wheel). Valid for this bridge because the ARMS NEVER MOVE
(arm target = first measured pose); joint limits, speed caps, command rate and watchdog of the safety filter stay fully active.
  AALTO_REPO=<clone> python g1/run_mock_gate.py --policy ws://localhost:8000 --team giorgio --episodes 1 [--time-limit 20]"""
import os, runpy, sys
REPO = os.environ["AALTO_REPO"]; sys.path.insert(0, REPO); os.chdir(REPO)
import aaltonomous.interface.safety as S
S.WorkspaceChecker = lambda spec, c: None            # self.ws = None -> workspace check skipped
sys.argv = ["runner", "--backend", "mock"] + sys.argv[1:]
runpy.run_module("aaltonomous.deploy.runner", run_name="__main__")

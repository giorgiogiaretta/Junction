"""Minimal numpy stand-in for the Pinocchio calls used by aaltonomous (safety.WorkspaceChecker, calibration):
buildModelFromUrdf (fixed base at the URDF root), neutral, forwardKinematics, framesForwardKinematics,
updateFramePlacement, data.oMf, model.getJointId / getFrameId / joints[id].idx_q. Windows has no pin wheel.
Frames = links and joints (placement of a joint frame = its child link). Revolute/continuous/prismatic joints, 1 dof each."""
import xml.etree.ElementTree as ET

import numpy as np

__version__ = "shim-0.1"


def _rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _axis_angle(a, t):
    a = np.asarray(a, float); a = a / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K


class SE3:
    def __init__(self, R=None, p=None):
        self.rotation = np.eye(3) if R is None else np.asarray(R, float)
        self.translation = np.zeros(3) if p is None else np.asarray(p, float)

    def __mul__(self, o):
        return SE3(self.rotation @ o.rotation, self.rotation @ o.translation + self.translation)


class _Joint:
    def __init__(self, idx_q):
        self.idx_q = idx_q


class Model:
    pass


class Data:
    def __init__(self, model):
        self.oMf = [SE3() for _ in model._frames]
        self._q = np.zeros(model.nq)


def buildModelFromUrdf(path):
    root = ET.parse(str(path)).getroot()
    links = [l.get("name") for l in root.findall("link")]
    js = []
    for j in root.findall("joint"):
        o = j.find("origin")
        xyz = np.array([float(v) for v in (o.get("xyz", "0 0 0") if o is not None else "0 0 0").split()])
        rpy = [float(v) for v in (o.get("rpy", "0 0 0") if o is not None else "0 0 0").split()]
        ax = j.find("axis")
        axis = np.array([float(v) for v in ax.get("xyz").split()]) if ax is not None else np.array([1.0, 0, 0])
        js.append(dict(name=j.get("name"), type=j.get("type"), parent=j.find("parent").get("link"),
                       child=j.find("child").get("link"), T=SE3(_rpy(*rpy), xyz), axis=axis))
    m = Model()
    children = {j["child"] for j in js}
    m._root = [l for l in links if l not in children][0]
    m._by_child = {j["child"]: j for j in js}
    m.names = ["universe"]
    m.joints = [_Joint(-1)]
    for j in js:
        if j["type"] in ("revolute", "continuous", "prismatic"):
            j["iq"] = len(m.names) - 1
            m.names.append(j["name"]); m.joints.append(_Joint(j["iq"]))
    m.nq = len(m.names) - 1
    m._frames = links + [j["name"] for j in js]
    m._frame_link = {**{l: l for l in links}, **{j["name"]: j["child"] for j in js}}
    return m


def _model_methods():
    def getJointId(self, name):
        return self.names.index(name) if name in self.names else len(self.names)

    def getFrameId(self, name):
        if name not in self._frames:
            raise KeyError(f"frame {name} not in URDF")
        return self._frames.index(name)

    def createData(self):
        return Data(self)
    Model.getJointId, Model.getFrameId, Model.createData = getJointId, getFrameId, createData


_model_methods()


def neutral(model):
    return np.zeros(model.nq)


def _link_pose(model, q, link, cache):
    if link in cache:
        return cache[link]
    if link == model._root:
        cache[link] = SE3(); return cache[link]
    j = model._by_child[link]
    M = _link_pose(model, q, j["parent"], cache) * j["T"]
    if j["type"] in ("revolute", "continuous"):
        M = M * SE3(_axis_angle(j["axis"], q[j["iq"]]))
    elif j["type"] == "prismatic":
        M = M * SE3(None, j["axis"] * q[j["iq"]])
    cache[link] = M
    return M


def forwardKinematics(model, data, q):
    data._q = np.asarray(q, float).copy(); data._cache = {}


def updateFramePlacement(model, data, fid):
    M = _link_pose(model, data._q, model._frame_link[model._frames[fid]], data._cache)
    data.oMf[fid] = M
    return M


def framesForwardKinematics(model, data, q):
    forwardKinematics(model, data, q)
    for f in range(len(model._frames)):
        updateFramePlacement(model, data, f)

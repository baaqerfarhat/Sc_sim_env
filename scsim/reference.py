"""Reference families.

Two families, reported separately (build_scSim.md Sec 10):

`StepSetpointReference` - hardware-matched. traj_simple_y.py is a setpoint sequence
with position-triggered transitions, not a time-parameterised trajectory. Its
`v_ref` is identically zero, which gives a large reference defect b_r and directly
inflates s_cert. A smooth reference will NOT reproduce the observed behaviour,
because the step at the 15 cm switch is a large part of the dynamics.

`SmoothFeasibleReference` - dynamically feasible, so the certificate has a chance.
Speeds are capped by the achievable acceleration, so v_ref is consistent with what
the plant can actually deliver.
"""
from __future__ import annotations

import numpy as np

from . import config as C


class StepSetpointReference:
    """Hardware-matched. Stage 1 holds start+[0,-2]; when |y - y_wp1| < 0.15 m it
    switches to start+[+1,-2] and republishes that forever. v_ref = a_ref = 0."""

    name = "step"

    def __init__(self, start=np.zeros(2), psi_ref=0.0):
        self.start = np.asarray(start, dtype=float)
        self.wp = [self.start + C.WP1, self.start + C.WP2]
        self.stage = 0
        self.psi_ref = float(psi_ref)
        self.switch_step = None

    def update(self, x, k=None):
        """Position-triggered transition. Called once per control cycle."""
        if self.stage == 0 and abs(x[1] - self.wp[0][1]) < C.WP_SWITCH_TOL:
            self.stage = 1
            if self.switch_step is None:
                self.switch_step = k
        return self.current()

    def current(self):
        p = self.wp[self.stage]
        return np.array([p[0], p[1], 0.0, 0.0, self.psi_ref, 0.0])

    def preview(self, N):
        """The MPC's preview. The deployed controller previewed a constant setpoint,
        since the transition is triggered by position and cannot be predicted."""
        r = self.current()
        return np.tile(r, (N + 1, 1))

    def scoring_reference(self, k):
        """The original task reference used for scoring, independent of any online
        reference change by a supervisor."""
        return self.current()


class SmoothFeasibleReference:
    """Dynamically feasible rest-to-rest profile over the same 3 m Manhattan path.

    Peak acceleration is held at `accel_frac` of the achievable 0.0384 m/s^2 so the
    feedforward the certificate needs actually exists. This is the family that gives
    the certificate a chance; it is NOT what hardware ran.
    """

    name = "smooth"

    def __init__(self, start=np.zeros(2), psi_ref=0.0, accel_frac=0.5):
        self.start = np.asarray(start, dtype=float)
        self.psi_ref = float(psi_ref)
        a_max = accel_frac * C.ANCHORS.accel_chain_pred
        # two rest-to-rest legs: 2.0 m in -y, then 1.0 m in +x
        self.legs = [(np.array([0.0, -2.0]), 2.0), (np.array([1.0, 0.0]), 1.0)]
        self.a_max = a_max
        # bang-bang (triangular) profile duration for a rest-to-rest move of length L
        self.durations = [2.0 * np.sqrt(L / a_max) for _, L in self.legs]
        self.t_switch = np.cumsum([0.0] + self.durations)

    def _leg_state(self, leg, t):
        """Triangular accel profile: position, velocity along the leg direction."""
        direction, L = self.legs[leg]
        u = direction / np.linalg.norm(direction)
        T = self.durations[leg]
        a = self.a_max
        if t <= 0:
            return 0.0, 0.0
        if t >= T:
            return L, 0.0
        if t < T / 2:
            return 0.5 * a * t * t, a * t
        td = T - t
        return L - 0.5 * a * td * td, a * td

    def state_at(self, t):
        p = self.start.copy()
        v = np.zeros(2)
        for leg in range(len(self.legs)):
            direction, L = self.legs[leg]
            u = direction / np.linalg.norm(direction)
            t_leg = t - self.t_switch[leg]
            s, sd = self._leg_state(leg, t_leg)
            p = p + u * s
            if 0.0 <= t_leg <= self.durations[leg]:
                v = u * sd
        return np.array([p[0], p[1], v[0], v[1], self.psi_ref, 0.0])

    def update(self, x, k=None):
        self.k = 0 if k is None else k
        return self.state_at(self.k * C.TS)

    def current(self):
        return self.state_at(getattr(self, "k", 0) * C.TS)

    def preview(self, N):
        k = getattr(self, "k", 0)
        return np.array([self.state_at((k + i) * C.TS) for i in range(N + 1)])

    def scoring_reference(self, k):
        return self.state_at(k * C.TS)


def make_reference(family, start=np.zeros(2), psi_ref=0.0):
    if family == "step":
        return StepSetpointReference(start, psi_ref)
    if family == "smooth":
        return SmoothFeasibleReference(start, psi_ref)
    raise ValueError(f"unknown reference family {family!r}")

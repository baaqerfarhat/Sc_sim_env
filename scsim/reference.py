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
from .plant import wrap_pi


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

    def final_target(self):
        """The FINAL intended waypoint and heading.

        Task completion has to be judged against this, not against whichever waypoint
        happens to be current. Scoring a dwell at the current setpoint credits the
        vehicle for sitting at an intermediate waypoint - possibly before the fault
        even arrives - which is not completion of the commanded task.
        """
        p = self.wp[-1]
        return np.array([p[0], p[1], 0.0, 0.0, self.psi_ref, 0.0])


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

    def final_target(self):
        """End of the last leg, at rest. The profile is time-parameterised, so this is
        the state after every leg has completed."""
        return self.state_at(float(self.t_switch[-1]))


class TransferReference:
    """A HELD-OUT family, used for transfer evaluation only and never for training.

    Sec 5.2 of the corrections plan: a family used for cross-reference training
    cannot simultaneously be presented as an unseen test family. `step` and `smooth`
    are both in the training mixture, so a third family is reserved here.

    It differs structurally from both, not just in parameters: a continuously curving
    figure-of-eight with no rest points and a yaw reference that tracks the path
    tangent, so heading is never constant. Speed is scaled to the same achievable
    acceleration so it remains feasible.
    """

    name = "transfer"

    def __init__(self, start=np.zeros(2), psi_ref=0.0, accel_frac=0.5, period=30.0):
        self.start = np.asarray(start, dtype=float)
        self.period = float(period)
        a_max = accel_frac * C.ANCHORS.accel_chain_pred
        w = 2.0 * np.pi / self.period
        # lissajous x = Ax sin(wt), y = Ay sin(2wt); peak accel scales as A w^2
        self.w = w
        self.Ay = a_max / (4.0 * w * w)      # the 2w term dominates the acceleration
        self.Ax = 2.0 * self.Ay

    def state_at(self, t):
        w, Ax, Ay = self.w, self.Ax, self.Ay
        px = Ax * np.sin(w * t)
        py = Ay * np.sin(2.0 * w * t)
        vx = Ax * w * np.cos(w * t)
        vy = 2.0 * Ay * w * np.cos(2.0 * w * t)
        psi = np.arctan2(vy, vx) if (abs(vx) + abs(vy)) > 1e-9 else 0.0
        # yaw rate by differentiating atan2 of the velocity
        ax = -Ax * w * w * np.sin(w * t)
        ay = -4.0 * Ay * w * w * np.sin(2.0 * w * t)
        sp2 = vx * vx + vy * vy
        r = (vx * ay - vy * ax) / sp2 if sp2 > 1e-12 else 0.0
        return np.array([self.start[0] + px, self.start[1] + py, vx, vy,
                         wrap_pi(psi), r])

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

    def final_target(self):
        """This family is a closed, continuously curving path with no rest point, so
        it has no terminal waypoint. Task completion in the waypoint sense is
        undefined here, and callers must score tracking error instead of completion.
        """
        return None


def _quintic(tau):
    """Minimum-jerk arc length and its first three derivatives w.r.t. tau.

    s = 10 tau^3 - 15 tau^4 + 6 tau^5 has s(0)=0, s(1)=1 and s'=s''=0 at both ends, so
    two of these joined end to end are continuous in position, velocity, acceleration
    and jerk at the join - every derivative the plan requires to match is zero there.
    """
    t2, t3, t4, t5 = tau * tau, tau ** 3, tau ** 4, tau ** 5
    s = 10.0 * t3 - 15.0 * t4 + 6.0 * t5
    sd = 30.0 * t2 - 60.0 * t3 + 30.0 * t4
    sdd = 60.0 * tau - 180.0 * t2 + 120.0 * t3
    return s, sd, sdd


# Peak |s''| over tau in [0, 1], attained at tau = (3 - sqrt(3))/6 and its mirror. Used
# by the analytic half of the feasibility gate so the acceleration bound is exact rather
# than sampled: peak |accel| on a segment of length Lg and duration T is
# QUINTIC_ACC_PEAK * Lg / T^2.
QUINTIC_ACC_PEAK = 10.0 / np.sqrt(3.0)


class SmoothDockReference:
    """`smooth_dock_v1`: the prespecified inspection-to-docking preview task (Sec 6.3).

    Two quintic minimum-jerk rest-to-rest segments over the selected manoeuvre
    duration, then the docking pose is held for the remainder of the episode:

      segment 1  start                -> start + (0.6, +0.6), yaw 0 -> +30 deg
      segment 2  start + (0.6, +0.6)  -> start + (1.0,  0.0), yaw +30 deg -> 0

    Every derivative vanishes at the join, so position, yaw, velocity, angular rate,
    acceleration and angular acceleration are continuous there by construction rather
    than by numerical accident.

    Unlike the retained `step` family this reference is differentiable and carries a
    genuine feedforward, so preview has something to exploit; unlike `smooth` it turns
    the vehicle, so the heading channel is exercised and the body/world distinction
    matters. The coordinates are an engineering design declared in Sec 6.3 of the plan;
    they are NOT extracted from any hardware mission, and they are frozen before the
    test manifest is opened.
    """

    name = "smooth_dock"
    version = "smooth_dock_v1"

    # offsets from the nominal start pose, exactly as declared in the plan
    PRE_DOCK = np.array([0.6, +0.6])
    FINAL = np.array([1.0, 0.0])
    YAW_PRE_DOCK = np.deg2rad(30.0)
    YAW_FINAL = 0.0

    def __init__(self, start=np.zeros(2), psi_ref=0.0, duration=30.0):
        self.start = np.asarray(start, dtype=float)
        self.psi_start = float(psi_ref)
        self.duration = float(duration)
        self.T_seg = self.duration / 2.0
        self.k = 0
        # (target position, target yaw) at the end of each segment
        self.legs = ((self.start + self.PRE_DOCK, self.psi_start + self.YAW_PRE_DOCK),
                     (self.start + self.FINAL, self.psi_start + self.YAW_FINAL))

    # ------------------------------------------------------------------
    def _segment(self, i, t):
        """Position, velocity, acceleration, yaw, rate and angular acceleration on
        segment i at local time t."""
        p0 = self.start if i == 0 else self.legs[0][0]
        y0 = self.psi_start if i == 0 else self.legs[0][1]
        p1, y1 = self.legs[i]
        dp, dy = np.asarray(p1) - np.asarray(p0), float(y1 - y0)
        T = self.T_seg
        tau = np.clip(t / T, 0.0, 1.0)
        s, sd, sdd = _quintic(tau)
        return (p0 + dp * s, dp * sd / T, dp * sdd / (T * T),
                y0 + dy * s, dy * sd / T, dy * sdd / (T * T))

    def full_state_at(self, t):
        """(position, velocity, acceleration, yaw, yaw rate, angular acceleration).

        The acceleration channels are what the feasibility gate needs, so they are
        returned here rather than differenced numerically by the caller.
        """
        if t <= 0.0:
            return (self.start.copy(), np.zeros(2), np.zeros(2),
                    self.psi_start, 0.0, 0.0)
        if t < self.T_seg:
            return self._segment(0, t)
        if t < self.duration:
            return self._segment(1, t - self.T_seg)
        p, y = self.legs[1]
        return (np.asarray(p, dtype=float).copy(), np.zeros(2), np.zeros(2),
                float(y), 0.0, 0.0)

    def state_at(self, t):
        p, v, _, psi, r, _ = self.full_state_at(t)
        return np.array([p[0], p[1], v[0], v[1], wrap_pi(psi), r])

    # ------------------------------------------------------------------
    def update(self, x, k=None):
        self.k = 0 if k is None else k
        return self.state_at(self.k * C.TS)

    def current(self):
        return self.state_at(self.k * C.TS)

    def preview(self, N):
        """The complete N+1 reference sequence, committed before the action is chosen.

        This family, unlike `step`, has a preview that is actually informative: the
        successor references are known in advance rather than being produced by an
        unpredictable position-triggered switch.
        """
        return np.array([self.state_at((self.k + i) * C.TS) for i in range(N + 1)])

    def scoring_reference(self, k):
        return self.state_at(k * C.TS)

    def final_target(self):
        """The declared docking pose. Held for the remainder of the episode, so task
        completion is judged against a target the reference actually rests at."""
        p, y = self.legs[1]
        return np.array([p[0], p[1], 0.0, 0.0, wrap_pi(float(y)), 0.0])


# families that may appear in TRAINING data, and the one reserved for transfer
TRAIN_FAMILIES = ("step", "smooth")
TRANSFER_FAMILY = "transfer"
# Path B evaluation families (Sec 6.2/6.3): the retained hardware-anchored step task
# and the prespecified smooth preview mission.
PATHB_FAMILIES = ("step", "smooth_dock")


class StationKeepReference(StepSetpointReference):
    """Hold ONE setpoint for the whole episode, at a fixed heading.

    This is the narrow operating case of Sec 11/C1: a bounded reference domain with an
    exactly feasible feedforward. It matters for the certificate because the reference
    defect bound b_r is what makes the swept region empty - the hardware-matched `step`
    family contains a 1.0 m setpoint jump in a single 0.1 s sample, for which no bounded
    input can follow the reference, and its defect measures b_r = 29.7 against an input
    radius of 1.4. On this family the feedforward is exact and b_r = 0 identically.
    """

    name = "station_keep"

    def update(self, x, k=None):
        """No transition: the setpoint is held. Kept for interface compatibility."""

    def final_target(self):
        p = self.wp[0]
        return np.array([p[0], p[1], 0.0, 0.0, self.psi_ref, 0.0])


# The manoeuvre duration selected by the Sec 6.4 development feasibility ladder. It is
# written here by pathb2_taskgate.py once the gate passes and is READ by every later
# stage, so the task cannot silently differ between the gate and the test.
SMOOTH_DOCK_DURATION_S = 30.0


def make_reference(family, start=np.zeros(2), psi_ref=0.0):
    if family == "step":
        return StepSetpointReference(start, psi_ref)
    if family in ("smooth_dock", "smooth_dock_v1"):
        return SmoothDockReference(start, psi_ref,
                                   duration=SMOOTH_DOCK_DURATION_S)
    if family == "station_keep":
        return StationKeepReference(start, psi_ref)
    if family == "smooth":
        return SmoothFeasibleReference(start, psi_ref)
    if family == "transfer":
        return TransferReference(start, psi_ref)
    raise ValueError(f"unknown reference family {family!r}")

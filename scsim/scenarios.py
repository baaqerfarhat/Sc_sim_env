"""Scenario definitions and the causal history features fed to the encoder.

Four main conditions (Simulation_Validation_Protocol Phase F): healthy, actuator,
perception, combined. Impairment onset is drawn uniformly from 15-20 s.

The two actuator interventions are kept strictly distinct and never conflated:

  `pulse_skip`  the hardware mechanism. Deterministic on-time zeroing of T7/T8 on a
                fixed fraction of cycles. fmax is unchanged; there is no thrust
                reduction. This is what the hardware runs reproduce.
  `eta_smooth`  a smooth per-thruster effectiveness scale used only for the severity
                sweep. Labelled as a distinct intervention, never as "x%
                effectiveness" of the pulse-skip fault.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
import zlib

import numpy as np

from . import config as C
from .plant import jetson_nominal_step, wrap_pi


@dataclass
class Scenario:
    name: str
    condition: str                  # healthy | actuator | perception | combined
    fault_active: bool = False
    fault_fraction: float = 0.7
    perception: str = "healthy"
    eta_smooth: list | None = None
    onset_s: float = 17.5
    reference: str = "step"
    mass: float = C.MASS
    jzz: float = C.JZZ
    drag: float = 0.0
    yaw_damp: float = 0.0
    duty_ceiling: float = C.PWM_PERIOD
    fmax: float = C.FMAX_PER_THRUSTER
    fit_offset: float = C.FIT_OFFSET
    intervention: str = "none"      # none | pulse_skip | eta_smooth | measurement
    stress: bool = False            # True marks an out-of-distribution stress cell

    @property
    def onset_step(self):
        return int(round(self.onset_s / C.TS))

    def run_kwargs(self):
        return dict(
            fault_active=self.fault_active, fault_fraction=self.fault_fraction,
            fault_onset_step=self.onset_step, perception=self.perception,
            eta_smooth=None if self.eta_smooth is None else np.array(self.eta_smooth),
            reference=self.reference, mass=self.mass, jzz=self.jzz,
            drag=self.drag, yaw_damp=self.yaw_damp,
            duty_ceiling=self.duty_ceiling, fmax=self.fmax,
            fit_offset=self.fit_offset,
        )

    def to_dict(self):
        d = asdict(self)
        d["onset_step"] = self.onset_step
        return d


def draw_onset(rng):
    return float(rng.uniform(*C.ONSET_WINDOW))


def scenario_rng(*key):
    """A reproducible generator for a scenario-draw key such as (cond, ep_seed).

    Python's builtin hash() is salted per interpreter, so seeding from it makes the
    draw depend on PYTHONHASHSEED: matched WITHIN one run, but different on a rerun,
    which is not an acceptable property for numbers that go into a paper. crc32 over
    the repr is stable across processes and releases.
    """
    return np.random.default_rng(zlib.crc32(repr(key).encode()) & 0xFFFFFFFF)


def make_condition(condition, rng, reference="step", mismatch=True, stress=False):
    """Draw one scenario from a main condition.

    Plant mismatch is applied so the evaluation plant is distinct from the predictor;
    otherwise small prediction errors and certificate compliance would be largely
    built in. Interior draws are +/-10%; stress cells are +/-15% and labelled.
    """
    onset = draw_onset(rng)
    span = 0.15 if stress else 0.10
    mass = C.MASS * (1.0 + rng.uniform(-span, span)) if mismatch else C.MASS
    jzz = C.JZZ * (1.0 + rng.uniform(-span, span)) if mismatch else C.JZZ
    # residual drag / yaw damping: unknown on hardware (Sec 14 lists these as
    # recoverable by identify_nominal() from the C1 runs, which we do not have),
    # so a small bounded amount is drawn as part of the mismatch
    drag = rng.uniform(0.0, 0.02) if mismatch else 0.0
    yaw_damp = rng.uniform(0.0, 0.02) if mismatch else 0.0
    base = dict(onset_s=onset, reference=reference, mass=mass, jzz=jzz,
                drag=drag, yaw_damp=yaw_damp, stress=stress)

    if condition == "healthy":
        return Scenario("healthy", "healthy", intervention="none", **base)
    if condition == "actuator":
        return Scenario("actuator", "actuator", fault_active=True,
                        fault_fraction=0.7, intervention="pulse_skip", **base)
    if condition == "perception":
        return Scenario("perception", "perception", perception="occluded",
                        intervention="measurement", **base)
    if condition == "combined":
        return Scenario("combined", "combined", fault_active=True,
                        fault_fraction=0.7, perception="occluded",
                        intervention="pulse_skip+measurement", **base)
    raise ValueError(condition)


MAIN_CONDITIONS = ("healthy", "actuator", "perception", "combined")


def calibration_mixture(rng, reference="step"):
    """The declared exchangeable population for conformal calibration: an
    independently sampled mixture of the four main conditions with fixed
    probabilities. A balanced performance matrix is NOT this population."""
    cond = rng.choice(MAIN_CONDITIONS, p=[0.25, 0.25, 0.25, 0.25])
    return make_condition(str(cond), rng, reference=reference)


# ==========================================================================
# causal history features, manuscript Eq. (3)
# ==========================================================================
N_FEAT_PER_STEP = 2 + 1 + 6 + 3 + 6  # innov(2) avail(1) dxhat(6) u(3) eps0(6)


def build_history(log_arrays, k, L=C.HISTORY_L):
    """iota_k = vec{ (zeta^o, m^o)_{k-L:k}, dxhat_{k-L+1:k}, u_{k-L:k-1},
                     eps0_{k-L:k-1} }

    History is formed BEFORE selecting command k: eps0_{k-1} uses the newly
    available xhat_k and the previously transmitted u_{k-1}. Hidden impairments,
    onset times and probe outcomes are excluded by construction - none of them are
    arguments to this function.

    `u_nom_tx` is the NOMINAL-EQUIVALENT transmitted wrench, a function of the
    commanded pulses alone. Using the post-fault wrench here, as an earlier version
    did, handed the encoder a direct measurement of the hidden actuation fault and
    made the no-fault-label premise false: the fault then had to be *inferred* from
    nothing, because it was already being observed.

    Returns (L+1, N_FEAT_PER_STEP) with invalid entries zeroed and their
    availability flag left visible, plus a mask.
    """
    xh = log_arrays["x_hat"]
    u = log_arrays["u_nom_tx"]
    valid = log_arrays["pose_valid"]
    innov = log_arrays["innov"]

    feats = np.zeros((L + 1, N_FEAT_PER_STEP), dtype=np.float32)
    mask = np.zeros(L + 1, dtype=np.float32)
    for j in range(L + 1):
        i = k - L + j
        if i < 0:
            continue
        mask[j] = 1.0
        col = 0
        feats[j, col:col + 2] = innov[i]
        col += 2
        feats[j, col] = float(valid[i])
        col += 1
        if i >= 1:
            feats[j, col:col + 6] = _state_delta(xh[i - 1], xh[i])
        col += 6
        if i >= 1:
            feats[j, col:col + 3] = u[i - 1]
        col += 3
        if i >= 1:
            # nominal prediction residual eps0 = xhat_i - f0(xhat_{i-1}, u_{i-1})
            pred = jetson_nominal_step(xh[i - 1], u[i - 1])
            d = _state_delta(pred, xh[i])
            feats[j, col:col + 6] = d
        col += 6
    return feats, mask


def _state_delta(a, b):
    d = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    d[4] = wrap_pi(np.asarray(b)[4] - np.asarray(a)[4])
    return d


# feature normalisation is computed on TRAINING data only
FEATURE_SCALE = np.array(
    [0.3, 0.3, 1.0] + [0.2, 0.2, 0.1, 0.1, 0.1, 0.1] + [1.0, 1.0, 0.4]
    + [0.2, 0.2, 0.1, 0.1, 0.1, 0.1], dtype=np.float32
)


def to_body_frame(x, vec6):
    """Rotate a state-space vector into the body frame of `x`.

    The residual is predicted in body-frame canonical coordinates so that
    d_theta(T_g x, u, z) = L_g d_theta(x, u, z) with
    L_g = blkdiag(R_g, 1, R_g, 1). Componentwise WORLD-frame clipping would not be
    rotation equivariant, which is why the +/-0.5 clip is applied here instead.
    """
    psi = x[4]
    c, s = np.cos(psi), np.sin(psi)
    R = np.array([[c, s], [-s, c]])  # world -> body
    out = np.array(vec6, dtype=float).copy()
    out[0:2] = R @ vec6[0:2]
    out[2:4] = R @ vec6[2:4]
    return out


def from_body_frame(x, vec6):
    psi = x[4]
    c, s = np.cos(psi), np.sin(psi)
    R = np.array([[c, -s], [s, c]])  # body -> world
    out = np.array(vec6, dtype=float).copy()
    out[0:2] = R @ vec6[0:2]
    out[2:4] = R @ vec6[2:4]
    return out

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


# Sec 5.2 SCALING AUDIT, stated rather than implied. These divisors are HARDCODED
# constants, not statistics computed from the training split, despite the comment that
# previously sat on this array claiming otherwise. They are frozen and disclosed as
# hardcoded so that M1, M2, M3, M4 and M-motion remain exactly comparable; changing to
# train-set-only normalisation would be a new pipeline version requiring every learned
# method to be retrained and a fresh test manifest, which this campaign does not do.
FEATURE_SCALE = np.array(
    [0.3, 0.3, 1.0] + [0.2, 0.2, 0.1, 0.1, 0.1, 0.1] + [1.0, 1.0, 0.4]
    + [0.2, 0.2, 0.1, 0.1, 0.1, 0.1], dtype=np.float32
)
FEATURE_SCALE_PROVENANCE = ("HARDCODED constants, frozen and disclosed. NOT computed "
                            "from the training split.")

# Sec 5.1 feature audit: the exact composition of the 18-feature, (L+1)=11-token causal
# history, named so the manuscript cannot describe a stream the code does not carry.
FEATURE_GROUPS = (
    ("innovation", 0, 2, "estimator innovation diagnostic scalars"),
    ("validity", 2, 3, "pose-availability scalar"),
    ("state_increment", 3, 9, "estimated-state increments"),
    ("prev_command", 9, 12, "previous transmitted nominal-equivalent command"),
    ("nominal_residual", 12, 18, "nominal prediction-residual components"),
)

# M-motion (Sec 4/5.3): the encoder input drops the two innovation scalars and the one
# validity channel and retains state increments, previous transmitted command and
# nominal residual. Because the first layer is a linear projection, zeroing a column is
# exactly equivalent to deleting that column together with its weights.
#
# It is NOT a vision-free controller: the retained increments and residuals are computed
# from the vision-based estimator, so this measures the incremental value of the EXPLICIT
# diagnostic channels only.
MOTION_ONLY_MASK = np.ones(N_FEAT_PER_STEP, dtype=np.float32)
MOTION_ONLY_MASK[0:3] = 0.0


def feature_mask(name):
    """Named encoder-input masks. `full` is every channel; `motion_command_only` is the
    M-motion ablation."""
    if name in (None, "full"):
        return np.ones(N_FEAT_PER_STEP, dtype=np.float32)
    if name == "motion_command_only":
        return MOTION_ONLY_MASK.copy()
    raise ValueError(f"unknown feature mask {name!r}")


# ==========================================================================
# Sec 6.1: the machine-readable scenario population
# ==========================================================================
def population_manifest(span=0.10):
    """The exact probability law of every exogenous random variable, exported from the
    frozen configuration rather than described in prose.

    Sec 6.1 is explicit that "same frozen distribution" is not an acceptable
    specification, so every support, unit, draw order and condition override is written
    out here and hashed into every result artefact. Draw ORDER matters: it is the order
    in which `make_condition` consumes the generator, and changing it changes every
    scenario even at identical seeds.
    """
    return {
        "version": "scenario_population_v1",
        "control_period_s": C.TS,
        "episode_seconds": C.EPISODE_SECONDS,
        "episode_steps": int(C.EPISODE_STEPS),
        "conditions": list(MAIN_CONDITIONS),
        "seed_to_draw": {
            "rule": "numpy default_rng seeded by zlib.crc32(repr((condition, "
                    "ep_seed, *extra)).encode()) & 0xFFFFFFFF",
            "why": "Python's builtin hash() is salted per interpreter, so seeding from "
                   "it makes the draw depend on PYTHONHASHSEED: matched within a run "
                   "but different on a rerun.",
            "independent_across_conditions": True,
        },
        "draw_order": [
            "onset_s", "mass_factor", "jzz_factor", "drag", "yaw_damp",
        ],
        "variables": {
            "onset_s": {
                "law": "uniform", "support": [float(C.ONSET_WINDOW[0]),
                                              float(C.ONSET_WINDOW[1])],
                "unit": "s", "endpoints": "closed low, open high (numpy uniform)",
                "grid": "onset_step = int(round(onset_s / TS))",
                "applies_to": "all four conditions, INCLUDING healthy, where it is a "
                              "pseudo-onset that defines the scoring window only and "
                              "triggers no impairment",
            },
            "mass_factor": {
                "law": "uniform", "support": [1.0 - span, 1.0 + span],
                "unit": "dimensionless multiplier on MASS",
                "nominal_mass_kg": float(C.MASS),
                "independent_of": "jzz_factor (separate draws, no correlation)",
            },
            "jzz_factor": {
                "law": "uniform", "support": [1.0 - span, 1.0 + span],
                "unit": "dimensionless multiplier on JZZ",
                "nominal_jzz_kgm2": float(C.JZZ),
            },
            "drag": {"law": "uniform", "support": [0.0, 0.02],
                     "unit": "N per (m/s), linear translational drag"},
            "yaw_damp": {"law": "uniform", "support": [0.0, 0.02],
                         "unit": "N m per (rad/s), linear yaw damping"},
        },
        "initial_state": {
            "law": "deterministic", "value": [0.0] * 6,
            "note": "x0 = 0 exactly; the initial state is NOT randomised in the "
                    "primary study, so it contributes no variance and must not be "
                    "described as a draw.",
        },
        "condition_overrides": {
            "healthy": {"fault_active": False, "perception": "healthy",
                        "intervention": "none"},
            "actuator": {"fault_active": True, "fault_fraction": 0.7,
                         "perception": "healthy", "intervention": "pulse_skip"},
            "perception": {"fault_active": False, "perception": "occluded",
                           "intervention": "measurement"},
            "combined": {"fault_active": True, "fault_fraction": 0.7,
                         "perception": "occluded",
                         "intervention": "pulse_skip+measurement"},
        },
        "actuator_fault_law": {
            "thrusters": [6, 7],
            "labels": "T7/T8 in one-based manuscript numbering",
            "fault_fraction": 0.7,
            "semantics": "RETAINED firing-cycle fraction: ~70% of otherwise eligible "
                         "cycles fire and ~30% are skipped. NOT a continuous 70% "
                         "thrust-amplitude scale and NOT 70% skipped.",
            "counter_rule": "should_fire = (nxt * fault_fraction - fired) >= 0.5, "
                            "evaluated per cycle; on a fire, `fired` increments; "
                            "`nxt` increments every cycle",
            "visibility": "hidden; realised only inside the plant and never an "
                          "encoder input",
        },
        "allocator": {
            "duty_law_s": "t_on = 4.829 * F / 25 - 0.07686",
            "duty_ceiling_frac": 0.40,
            "duty_ceiling_s": float(C.PWM_PERIOD),
            "slot_s": float(C.TS),
            "min_pulse_s": 0.012,
            "min_pulse_threshold_N": 0.001,
            "operation_order": [
                "threshold: requests at or below 0.001 N are dropped to zero",
                "duty law evaluated on the remaining request",
                "minimum-pulse promotion to 0.012 s",
                "clip to the 0.040 s duty ceiling",
            ],
            "open_valve_force_N": 1.2,
            "thrust_gain": float(C.THRUST_GAIN),
        },
        "perception_degradation": {
            "mode": "occluded",
            "note": "VO surrogate degradation: dropout and inflated measurement "
                    "noise. Realised inside the estimator surrogate; its parameters "
                    "are frozen in scsim/estimator.py and hashed in the config "
                    "manifest.",
        },
        "stress_span_excluded": {
            "value": 0.15,
            "why": "The +/-15% mass/inertia setting is an out-of-distribution stress "
                   "cell and is NOT part of the primary four-condition estimand.",
        },
        "config_manifest_hash": C.manifest_hash(),
    }


def population_hash(manifest=None):
    """SHA-256 of the canonical JSON form of the population manifest."""
    import hashlib
    import json
    man = population_manifest() if manifest is None else manifest
    blob = json.dumps(man, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


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

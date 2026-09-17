"""Frozen configuration for the planar spacecraft simulation.

Every value carries a provenance tag matching build_scSim.md:
  CONFIRMED  - read from the Jetson deployment code
  MEASURED   - measured from rovio_ws/experiments logs
  OPEN       - provisional, no measurement provenance
  SIM        - a simulation-study choice with no hardware counterpart

Provenance is machine-readable so the run manifest can reproduce it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json as _json
import json
import os as _os
from dataclasses import dataclass, field, asdict

import numpy as np

# --------------------------------------------------------------------------
# provenance registry
# --------------------------------------------------------------------------
PROVENANCE: dict[str, str] = {}


def _tag(name: str, why: str):
    PROVENANCE[name] = why


# --------------------------------------------------------------------------
# timing
# --------------------------------------------------------------------------
TS = 0.1  # control period [s]
CONTROL_HZ = 10.0
PLANT_SUBSTEPS = 20  # Ts/20 = 5 ms; finer than Ts/10 so 12 ms pulses resolve
_tag("TS", "CONFIRMED: hardcoded 0.1 s, control rate 10 Hz")
_tag("PLANT_SUBSTEPS", "SIM: Ts/20=5ms, finer than the Ts/10 floor in Sec 3")

# --------------------------------------------------------------------------
# rigid body (Sec 2)
# --------------------------------------------------------------------------
MASS = 25.0  # kg
JZZ = 2.0  # kg m^2
_tag("MASS", "OPEN: round number, no measurement provenance (Sec 2)")
_tag("JZZ", "OPEN: round number, no measurement provenance (Sec 2)")

# --------------------------------------------------------------------------
# wrench caps (Sec 3 steps 2 and 6)
# --------------------------------------------------------------------------
FX_MAX = 5.0  # N
FY_MAX = 5.0  # N
MZ_MAX_DECLARED = 2.0  # N m, what the MPC believes
YAW_SHARE = 0.40
MZ_CAP = YAW_SHARE * MZ_MAX_DECLARED  # 0.8 N m, the actual cap applied
_tag("MZ_CAP", "CONFIRMED: yaw_share 0.40 x Mz_max 2.0 = 0.8 N m")

TINY_AXIS_FRAC = 0.05  # Sec 3 step 3
_tag("TINY_AXIS_FRAC", "CONFIRMED: force axis < 5% of dominant axis is zeroed")

DEADBAND_FORCE = 0.1  # N,   Sec 3 step 4
DEADBAND_YAW = 0.02  # N m, Sec 3 step 4
_tag("DEADBAND_FORCE", "CONFIRMED: safety_filter deadband on commanded wrench")

THRUST_GAIN = 2.0  # Sec 3 step 5, applied to all three components
_tag("THRUST_GAIN", "CONFIRMED: multiplies all three components incl. yaw")

# --------------------------------------------------------------------------
# geometry and allocation (Sec 4)
# --------------------------------------------------------------------------
GEOM_L = 0.20
GEOM_B = 0.20
FMAX_PER_THRUSTER = 1.2  # N

# order: FX-MZ-, FX-MZ+, FY-MZ-, FY-MZ+, FX+MZ-, FX+MZ+, FY+MZ-, FY+MZ+
THRUSTER_NAMES = (
    "FX-MZ-", "FX-MZ+", "FY-MZ-", "FY-MZ+",
    "FX+MZ-", "FX+MZ+", "FY+MZ-", "FY+MZ+",
)

G_MAP = np.array(
    [
        [-1.0, -1.0, 0.0, 0.0, +1.0, +1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, -1.0, 0.0, 0.0, +1.0, +1.0],
        [-0.2, +0.2, -0.2, +0.2, -0.2, +0.2, -0.2, +0.2],
    ]
)
_tag("G_MAP", "CONFIRMED: Sec 4 thruster map with geom_l=geom_b=0.20 m")

W_TAU = np.array([1.0, 1.0, 8.0])  # yaw weighted 8x
ALLOC_REG_L2 = 1e-4  # ||F||^2
ALLOC_REG_L1 = 5e-4  # sum(F)
ALLOC_REG_USE = 1e-3  # F' diag(1+3h) F
USE_HIST_DECAY = 0.995
TAU_DEADZONE = 1e-6  # ||tau|| below this returns zeros
_tag("W_TAU", "CONFIRMED: diag(1,1,8), yaw preserved over translation")
_tag("USE_HIST_DECAY", "CONFIRMED: EWMA decay 0.995 updated every cycle")

USE_ACCUMULATOR = False
_tag("USE_ACCUMULATOR", "CONFIRMED: dt_accum carry-forward is disabled")

# --------------------------------------------------------------------------
# duty conversion (Sec 5)
# --------------------------------------------------------------------------
F_CL = 25.0  # PWM period frequency [Hz] -> T = 40 ms
PWM_PERIOD = 1.0 / F_CL  # 0.040 s, the duty ceiling inside a 100 ms slot
FIT_SLOPE = 4.829
FIT_OFFSET = -0.07686  # s
MIN_ON_TIME = 0.012  # s, min_on_time_ms = 12.0
PULSE_ZERO_THRESHOLD = 0.001  # N
_tag("FIT_SLOPE", 'CONFIRMED: "Table 6 @ 50 psi", uniform across all 8 thrusters')
_tag("PWM_PERIOD", "CONFIRMED: 40 ms ceiling in a 100 ms slot = 0.40 duty ceiling")
_tag("MIN_ON_TIME", "CONFIRMED: F>0.001 N stretched to 12 ms, else zeroed")

VALVE_THRUST = 1.2  # N delivered while a valve is open
_tag(
    "VALVE_THRUST",
    "OPEN but load-bearing: provisional reading that F is commanded thrust and "
    "the valve delivers ~1.2 N open. Reproduces the measured acceleration (Sec 7).",
)

PULSE_LEFT_ALIGNED = True
VALVE_INSTANTANEOUS = True
_tag("PULSE_LEFT_ALIGNED", "OPEN: pulse phase needs INSboard firmware; provisional")

# --------------------------------------------------------------------------
# fault injection (Sec 6)
# --------------------------------------------------------------------------
FAULT_THRUSTERS = (6, 7)  # zero-based; T7/T8 = FY+MZ-, FY+MZ+
_tag("FAULT_THRUSTERS", "CONFIRMED: always indices 6,7 at every level")
_tag(
    "FAULT_MECHANISM",
    "CONFIRMED: deterministic pulse skip, no RNG, no thrust reduction, "
    "applied after allocation and after the logged wrench is published",
)

# --------------------------------------------------------------------------
# hardware-matched deployed MPC (Sec 9)
# --------------------------------------------------------------------------
N_HORIZON_HW = 12
_tag("N_HORIZON_HW", "CONFIRMED: N=12 on hardware, not the manuscript's 10")

W_NOMINAL = np.array([30.0, 5.0, 0.1, 0.05, 0.1, 1.0])  # pos vel psi r u du
W_FLOOR = np.array([5.0, 1.0, 0.01, 0.01, 0.01, 0.1])
W_ANG_SLACK = 2e3
W_HEADBAND = 10.0
QN_SCALE = 4.0
ANG_RATE_SOFT = 1.8  # rad/s, soft via slack
ANG_RATE_HARD = 2.5  # rad/s, hard
HEADBAND = np.deg2rad(15.0)
_tag("W_NOMINAL", "CONFIRMED: deployed nominal weights, Sec 9 table")
_tag("QN_SCALE", "CONFIRMED: Q_N = 4Q on pos, vel, yaw, yaw rate; no terminal input")

# OSQP settings, deliberately loose first pass (Sec 9)
OSQP_EPS_1 = 1e-2
OSQP_EPS_2 = 1e-3
_tag("OSQP_EPS_1", "CONFIRMED: loose first pass so most logged solutions are coarse")

# solver-failure fallback, a near-coast
FALLBACK_KP_POS = 0.5
FALLBACK_CLIP_F = 0.2
FALLBACK_KP_HEAD = 0.1
FALLBACK_CLIP_M = 0.02

# pseudo-Huber scales for the proposed Eq. (16) cost
HUBER_S = np.array([0.50, 0.50, 0.25, 0.25, 0.20, 0.20])
_tag("HUBER_S", "SIM: Eq.(16) s_j not specified in the manuscript; declared here")

# --------------------------------------------------------------------------
# estimator surrogate (Sec 8)
# --------------------------------------------------------------------------
POS_LPF_TAU = 0.5  # s, hardcoded; declared 0.4 is dead code
YAW_LPF_TAU = 0.5  # s, on the sin/cos pair
VEL_BLEND_LPF = 0.8  # velocity = 0.8*d(LPF pos)/dt + 0.2*VO twist
YAWRATE_BLEND_LPF = 0.7
VEL_CLIP = 2.0  # m/s
YAWRATE_CLIP = 2.0  # rad/s
MIN_FD_DT = 0.010  # s
GATE_POS_JUMP = 0.5  # m within < 0.2 s -> reject
GATE_YAW_JUMP = np.deg2rad(90.0)
GATE_DT = 0.2  # s
_tag("POS_LPF_TAU", "CONFIRMED: hardcoded 0.5 s; pos_lpf_tau_s=0.4 is dead code")
_tag("VEL_BLEND_LPF", "CONFIRMED: 0.8 finite-difference / 0.2 VO twist blend")

# VO surrogate measurement model. These are the ONLY free parameters in the whole
# build: they are fitted so the closed-loop estimation error reproduces the Sec 7
# envelopes. Sec 7 is explicit that this is the intended procedure - "fit the
# unmodeled layer to hit them; do not tune the estimator to be good".
# Covariance and feature count are unavailable from the logs (rovio_aligner.py never
# copies the covariance fields, and feature count was never published as a scalar),
# so there is no measured noise parameter to use instead.
VO_PROFILES = {
    "healthy": dict(pos_noise=0.030, yaw_noise=0.020, bias_rw=0.0060,
                    yaw_bias_rw=0.0030, twist_noise=0.020, dropout_p=0.02,
                    dropout_len=(1, 3), scale_err=0.0),
    "mild": dict(pos_noise=0.055, yaw_noise=0.035, bias_rw=0.028,
                 yaw_bias_rw=0.012, twist_noise=0.05, dropout_p=0.07,
                 dropout_len=(2, 6), scale_err=0.04),
    "occluded": dict(pos_noise=0.100, yaw_noise=0.060, bias_rw=0.085,
                     yaw_bias_rw=0.030, twist_noise=0.10, dropout_p=0.18,
                     dropout_len=(3, 12), scale_err=0.10),
}
_tag(
    "VO_PROFILES",
    "SIM, FITTED: the only free parameters in the build. Fitted in Stage 3/4 so the "
    "closed-loop estimation error reproduces the Sec 7 envelopes. Not measured "
    "ROVIO noise parameters - the logged covariance channel is all zeros.",
)

# Stage 3/4 overwrite this file with the fitted profiles; loaded here so every
# downstream stage uses the frozen fit.
_FIT_PATH = _os.path.join(_os.path.dirname(__file__), "..", "results",
                          "vo_fit.json")
VO_FIT_LOADED = False
try:
    with open(_FIT_PATH) as _f:
        _fit = _json.load(_f)
    for _k, _v in _fit.get("profiles", {}).items():
        if _k in VO_PROFILES:
            _v = dict(_v)
            if "dropout_len" in _v:
                _v["dropout_len"] = tuple(_v["dropout_len"])
            VO_PROFILES[_k].update(_v)
    VO_FIT_LOADED = True
except (OSError, ValueError):
    pass

# camera intrinsics, if a projection model is ever needed
CAM_FX, CAM_FY, CAM_CX, CAM_CY = 649.919, 649.516, 310.643, 211.249
_tag("CAM_FX", "CONFIRMED: cam0.yaml, the file ROVIO actually reads")

# --------------------------------------------------------------------------
# reference / task (Sec 10)
# --------------------------------------------------------------------------
WP1 = np.array([0.0, -2.0])
WP2 = np.array([+1.0, -2.0])
WP_SWITCH_TOL = 0.15  # m on |y - y_wp1|
L_TASK = 3.0  # m commanded Manhattan path
TARGET_REACHED_THRESHOLD = 0.05
_tag("WP1", "CONFIRMED: traj_simple_y.py setpoint sequence, position-triggered")
_tag("L_TASK", "CONFIRMED: 3.0 m commanded Manhattan path length")

# --------------------------------------------------------------------------
# simulation study protocol (Simulation_Validation_Protocol.md)
# --------------------------------------------------------------------------
EPISODE_SECONDS = 60.0
EPISODE_STEPS = int(round(EPISODE_SECONDS / TS))  # 600
ONSET_WINDOW = (15.0, 20.0)  # s, uniform draw
N_SEEDS = 3
EPISODES_PER_CONDITION = 60  # within the protocol's 50-100
N_CAL_EPISODES = 200
N_TEST_EPISODES = 100
DELTA_D = 0.025
DELTA_E = 0.025
RECOVERY_POS_TOL = 0.05 * L_TASK  # 0.15 m
RECOVERY_YAW_TOL = np.deg2rad(5.0)
RECOVERY_DWELL = 2.0  # s
_tag("EPISODES_PER_CONDITION", "SIM: protocol says 50-100 matched episodes")
_tag("RECOVERY_POS_TOL", "SIM: protocol's proposed 0.05*L_task, not a hardware spec")

# smooth-eta severity sweep, a DISTINCT intervention from the pulse skip
ETA_LEVELS = (1.0, 0.7, 0.4, 0.2)
POSE_NOISE_MULT = (1, 2, 4)
DROPOUT_BLOCKS = (0.0, 0.2, 0.5, 1.0)
_tag(
    "ETA_LEVELS",
    "SIM: smooth-eta is a distinct intervention, NOT '70% effectiveness' of the "
    "hardware pulse-skip fault. Labelled separately everywhere.",
)

# --------------------------------------------------------------------------
# hardware anchoring targets (Sec 7)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class AnchorTargets:
    accel_p95_lo: float = 0.025  # m/s^2
    accel_p95_hi: float = 0.063
    accel_median: float = 0.035
    accel_chain_pred: float = 0.96 / 25.0  # 0.0384
    est_pos_p95_lo: float = 0.22  # m, healthy
    est_pos_p95_hi: float = 0.65
    est_yaw_p95_lo: float = 0.10  # rad
    est_yaw_p95_hi: float = 0.27
    occ_pos_p95_lo: float = 0.79  # m, zero-context occluded (V2)
    occ_pos_p95_hi: float = 4.86
    occ_learned_p95_lo: float = 0.33  # m, learned occluded (V4)
    occ_learned_p95_hi: float = 1.03
    rmse_healthy: float = 1.034  # m, Table I
    rmse_healthy_sd: float = 0.043
    peak_healthy: float = 2.013
    dt_median: float = 0.1000
    dt_p95: float = 0.1006

    # achievable set, Sec 4
    achievable_force: float = 2.4  # N, two thrusters x 1.2 N
    achievable_yaw: float = 0.96  # N m, pure couple on 1,3,5,7


ANCHORS = AnchorTargets()

# hardware Table I, for side-by-side reporting. Keys are "condition|context" so the
# manifest stays JSON-serialisable.
HARDWARE_TABLE = {
    ("healthy", "zero"): dict(n=5, rmse=1.034, rmse_sd=0.043, mae=0.874, mae_sd=0.098, peak=2.013, peak_sd=0.025),
    ("act70", "zero"): dict(n=5, rmse=1.105, rmse_sd=0.108, mae=0.982, mae_sd=0.110, peak=2.015, peak_sd=0.078),
    ("act70", "fixed"): dict(n=5, rmse=1.028, rmse_sd=0.142, mae=0.863, mae_sd=0.178, peak=1.992, peak_sd=0.022),
    ("act70", "learned"): dict(n=5, rmse=0.950, rmse_sd=0.022, mae=0.831, mae_sd=0.023, peak=1.686, peak_sd=0.149),
    ("act50", "zero"): dict(n=3, rmse=1.089, rmse_sd=0.023, mae=0.939, mae_sd=0.022, peak=3.047, peak_sd=1.761),
    ("act30", "zero"): dict(n=3, rmse=1.315, rmse_sd=0.187, mae=1.204, mae_sd=0.246, peak=2.047, peak_sd=0.076),
    ("act30", "learned"): dict(n=5, rmse=0.781, rmse_sd=0.020, mae=0.701, mae_sd=0.012, peak=1.344, peak_sd=0.066),
    ("occl", "zero"): dict(n=5, rmse=1.895, rmse_sd=0.087, mae=1.739, mae_sd=0.085, peak=2.881, peak_sd=0.237),
    ("occl", "fixed"): dict(n=3, rmse=1.352, rmse_sd=0.157, mae=1.267, mae_sd=0.185, peak=2.006, peak_sd=0.002),
    ("occl", "learned"): dict(n=5, rmse=0.798, rmse_sd=0.249, mae=0.645, mae_sd=0.201, peak=1.513, peak_sd=0.480),
}

# --------------------------------------------------------------------------
# learned context architecture (Sec 9 of the manuscript)
# --------------------------------------------------------------------------
HISTORY_L = 10
D_LATENT = 32
N_LAYERS = 3
N_HEADS = 4
D_WIDTH = 128
RESIDUAL_CLIP = 0.5  # per-state, in the body-frame canonical convention
_tag("RESIDUAL_CLIP", "CONFIRMED in deployment code; applied in body frame here")

LAMBDA_H = 0.5  # multistep weight
LAMBDA_I = 1.0  # behavioral-supervision weight; 0.0 for the ablation
C_Q = 1.0
LAMBDA_CROSS = 1.0
MULTISTEP_H = 5


def manifest() -> dict:
    """Machine-readable manifest of every frozen value plus its provenance."""
    mod = globals()
    out = {}
    for k, v in sorted(mod.items()):
        if k.startswith("_") or k.isupper() is False:
            continue
        if isinstance(v, np.ndarray):
            out[k] = v.tolist()
        elif isinstance(v, dict):
            # collapse tuple keys so the manifest stays JSON-serialisable
            out[k] = {("|".join(kk) if isinstance(kk, tuple) else str(kk)): vv
                      for kk, vv in v.items()}
        elif isinstance(v, (int, float, str, bool, tuple, list)):
            out[k] = v
    out["_provenance"] = dict(sorted(PROVENANCE.items()))
    out["_anchors"] = asdict(ANCHORS)
    return out


def manifest_hash() -> str:
    return hashlib.sha256(
        json.dumps(manifest(), sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


if __name__ == "__main__":
    m = manifest()
    print(json.dumps(m, indent=2, default=str)[:2000])
    print("...")
    print("manifest hash:", manifest_hash())
    print("n params:", len(m) - 2, " n provenance tags:", len(PROVENANCE))

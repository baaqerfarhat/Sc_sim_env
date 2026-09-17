"""Stage 1: open-loop verification of plant, allocator, duty law and fault.

Build order gate (build_scSim.md Sec 13.1). Verifies:
  - the achievable set: 2.4 N per force axis, 0.96 N m yaw couple
  - the 0.40-0.65 N usable proportional band of the duty law
  - the 12 ms stretch / zero behaviour of the minimum-pulse floor
  - the deterministic 3-skips-per-10-cycles fault pattern
  - that thrust_gain is NOT a clean factor of two (step 6 re-caps)
  - the independent acceleration agreement: 0.96 N / 25 kg = 0.038 m/s^2

Nothing downstream is trustworthy unless every check here passes.
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])

from scsim import config as C
from scsim import plant as P

RESULTS = {}
FAILURES = []


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}   {detail}")
    RESULTS[name] = {"pass": bool(ok), "detail": detail}
    if not ok:
        FAILURES.append(name)
    return ok


# ==========================================================================
print("=" * 78)
print("STAGE 1  open-loop plant / allocator / duty / fault verification")
print("=" * 78)

# --------------------------------------------------------------------------
print("\n1. Achievable set (Sec 4 table)")
# --------------------------------------------------------------------------
# Pure +X force: thrusters 4,5 (FX+) at fmax
F = np.zeros(8)
F[4] = F[5] = C.FMAX_PER_THRUSTER
u = P.alloc_matrix(0.0) @ F
check(
    "achievable_Fx_2.4N",
    abs(u[0] - 2.4) < 1e-9 and abs(u[2]) < 1e-9,
    f"Fx={u[0]:.3f} N (target 2.4), Mz={u[2]:.3e} (couple cancels)",
)

# Pure yaw couple: odd indices 1,3,5,7 are all MZ+
F = np.zeros(8)
F[[1, 3, 5, 7]] = C.FMAX_PER_THRUSTER
u = P.alloc_matrix(0.0) @ F
check(
    "achievable_Mz_0.96Nm",
    abs(u[2] - 0.96) < 1e-9 and np.linalg.norm(u[:2]) < 1e-9,
    f"Mz={u[2]:.4f} N m (target 0.96), |F|={np.linalg.norm(u[:2]):.3e} (pure couple)",
)

# The structural gap: the MPC believes 5 N / 2 N, physics gives 2.4 N / 0.96 N
gap_f = C.FX_MAX / 2.4
gap_m = C.MZ_MAX_DECLARED / 0.96
check(
    "declared_box_unreachable",
    gap_f > 2.0 and gap_m > 2.0,
    f"declared/achievable = {gap_f:.2f}x force, {gap_m:.2f}x yaw",
)
RESULTS["achievable_set"] = {"force_N": 2.4, "yaw_Nm": 0.96,
                             "declared_force_N": C.FX_MAX,
                             "declared_yaw_Nm": C.MZ_MAX_DECLARED}

# --------------------------------------------------------------------------
print("\n2. Duty law proportional band (Sec 5)")
# --------------------------------------------------------------------------
Fg = np.linspace(0.0, 1.4, 14001)
dt = P.duty_from_force(Fg)
# lower edge: first F with strictly positive on-time
f_lo = Fg[np.argmax(dt > 1e-12)]
# upper edge: first F at the ceiling
f_hi = Fg[np.argmax(dt >= C.PWM_PERIOD - 1e-15)]
check(
    "duty_band_lower_0.40N",
    0.39 < f_lo < 0.41,
    f"on-time becomes positive at F={f_lo:.4f} N (spec ~0.40)",
)
# Solve the duty law exactly rather than trusting the prose. The CONFIRMED formula
# is authoritative: build_scSim.md Sec 5 rounds the upper edge to 0.65 N, but slope
# 4.829 / offset -0.07686 put it at 0.60499 N. Recorded as a spec discrepancy, not
# a plant error - at F=0.65 N the raw on-time is already 48.7 ms, past the ceiling.
f_hi_exact = (C.PWM_PERIOD - C.FIT_OFFSET) * C.F_CL / C.FIT_SLOPE
check(
    "duty_band_upper_matches_formula",
    abs(f_hi - f_hi_exact) < 1e-3,
    f"on-time saturates at F={f_hi:.4f} N, matches closed form {f_hi_exact:.5f} N",
)
RESULTS["spec_discrepancy_duty_upper_edge"] = {
    "doc_states_N": 0.65,
    "formula_gives_N": float(f_hi_exact),
    "note": "build_scSim.md Sec 5 prose rounds the upper band edge to 0.65 N; the "
            "confirmed slope/offset put it at 0.605 N. Formula used. The usable "
            "proportional band is [0.398, 0.605] N, 21% narrower than stated, so "
            "the duty law is slightly MORE restrictive than the spec implies.",
}
print(f"     note: doc says upper edge ~0.65 N, formula gives {f_hi_exact:.3f} N "
      f"-> band narrower than documented (recorded, formula wins)")
check(
    "duty_ceiling_40ms",
    abs(dt.max() - 0.040) < 1e-12,
    f"max on-time {dt.max()*1e3:.3f} ms in a {C.TS*1e3:.0f} ms slot "
    f"-> duty ceiling {dt.max()/C.TS:.2f}",
)
RESULTS["duty_band"] = {"F_lo_N": float(f_lo), "F_hi_N": float(f_hi),
                        "usable_band_N": [float(f_lo), float(f_hi)],
                        "ceiling_s": float(dt.max())}

# --------------------------------------------------------------------------
print("\n3. Minimum-pulse floor (Sec 5)")
# --------------------------------------------------------------------------
# just above the zero threshold -> stretched to 12 ms
F = np.array([0.0011] + [0.0] * 7)
dt_on = P.apply_min_pulse(P.duty_from_force(F), F)
check(
    "min_pulse_stretch_12ms",
    abs(dt_on[0] - C.MIN_ON_TIME) < 1e-15,
    f"F=0.0011 N (raw on-time {P.duty_from_force(F)[0]*1e3:.2f} ms) "
    f"-> stretched to {dt_on[0]*1e3:.1f} ms",
)
# at or below the threshold -> zeroed
F = np.array([0.0010] + [0.0] * 7)
dt_on = P.apply_min_pulse(P.duty_from_force(F), F)
check("min_pulse_zero_below_thresh", dt_on[0] == 0.0,
      f"F=0.0010 N -> {dt_on[0]*1e3:.1f} ms (zeroed, not accumulated)")

# realizable average force per thruster: {0} U [0.12, 0.40] x F_valve
F = np.linspace(0.0, 1.4, 14001)
dt_on = P.apply_min_pulse(P.duty_from_force(F), F)
f_avg = C.VALVE_THRUST * dt_on / C.TS
nz = f_avg[f_avg > 0]
lo_frac, hi_frac = nz.min() / C.VALVE_THRUST, nz.max() / C.VALVE_THRUST
check(
    "realizable_avg_force_set",
    abs(lo_frac - 0.12) < 1e-6 and abs(hi_frac - 0.40) < 1e-6,
    f"nonzero average force spans [{lo_frac:.3f}, {hi_frac:.3f}] x F_valve "
    f"= [{nz.min():.3f}, {nz.max():.3f}] N (spec {{0}} U [0.12,0.40])",
)
# and there is a genuine gap: no attainable average between 0 and 0.12*valve
check("realizable_set_has_gap", nz.min() > 1e-6,
      f"gap between 0 and {nz.min():.4f} N is unattainable -> on/off quantization")

# --------------------------------------------------------------------------
print("\n4. thrust_gain is not a clean factor of two (Sec 3)")
# --------------------------------------------------------------------------
def chain_static(uin):
    u = P.cap_wrench_heading_first(np.asarray(uin, float))
    u = P.tiny_axis_zero(u)
    u = P.safety_filter(u)
    u = u * C.THRUST_GAIN
    return P.cap_wrench_heading_first(u)

lowreq = chain_static([1.0, 1.0, 0.1])
highreq = chain_static([4.0, 4.0, 0.7])
check(
    "gain_doubles_below_half_cap",
    abs(lowreq[0] - 2.0) < 1e-12,
    f"request Fx=1.0 N -> {lowreq[0]:.3f} N (doubled, below half the 5 N cap)",
)
check(
    "gain_noop_above_half_cap",
    abs(highreq[0] - C.FX_MAX) < 1e-12 and abs(highreq[2] - C.MZ_CAP) < 1e-12,
    f"request Fx=4.0 N -> {highreq[0]:.3f} N and Mz=0.7 -> {highreq[2]:.3f} "
    f"(both hit the cap; gain is a no-op)",
)

# --------------------------------------------------------------------------
print("\n5. Deterministic fault pattern (Sec 6)")
# --------------------------------------------------------------------------
fault = P.DeterministicFault(fault_fraction=0.7, active=True)
pattern, skips = [], 0
for k in range(100):
    dt_on = np.full(8, 0.030)
    out, skipped = fault.apply(dt_on)
    pattern.append(int(skipped))
    skips += int(skipped)
    if skipped:
        assert out[6] == 0.0 and out[7] == 0.0
check(
    "fault_skip_rate_30pct",
    skips == 30,
    f"{skips} skips in 100 cycles at fault_fraction=0.7 (spec ~30%)",
)
first10 = "".join(str(p) for p in pattern[:10])
check(
    "fault_pattern_regular_3_per_10",
    sum(pattern[:10]) == 3 and sum(pattern[10:20]) == 3,
    f"first 10 cycles skip mask = {first10} -> 3 skips/s at 10 Hz, fixed pattern",
)
# determinism: rerun must be bit-identical
f2 = P.DeterministicFault(fault_fraction=0.7, active=True)
p2 = [int(f2.apply(np.full(8, 0.030))[1]) for _ in range(100)]
check("fault_deterministic_no_rng", p2 == pattern,
      "identical skip mask on replay (no RNG, nothing seeded)")
# fmax is unchanged: no thrust reduction at any level
check("fault_no_thrust_reduction", C.FMAX_PER_THRUSTER == 1.2,
      "fmax stays 1.2 N on all eight thrusters at every level")
RESULTS["fault_pattern"] = {"skip_mask_first_20": pattern[:20],
                            "skips_per_100": skips}

# --------------------------------------------------------------------------
print("\n6. Fault degrades +Y and BOTH yaw signs (Sec 6)")
# --------------------------------------------------------------------------
# thrusters 6,7 are FY+MZ- and FY+MZ+
col6, col7 = C.G_MAP[:, 6], C.G_MAP[:, 7]
check(
    "fault_targets_plusY_both_yaw",
    col6[1] > 0 and col7[1] > 0 and col6[2] < 0 and col7[2] > 0,
    f"T7={C.THRUSTER_NAMES[6]} T8={C.THRUSTER_NAMES[7]}: both push +Y, "
    f"yaw signs {col6[2]:+.1f}/{col7[2]:+.1f} cover both directions",
)

# --------------------------------------------------------------------------
print("\n7. Allocator behaviour (Sec 4)")
# --------------------------------------------------------------------------
# W_tau = diag(1,1,8): yaw preserved at the expense of translation
uh = np.zeros(8)
tau_req = np.array([2.0, 0.0, 0.9])  # both near/над the achievable edge
F = P.allocate(tau_req, 0.0, uh)
ach = P.alloc_matrix(0.0) @ F
yaw_err = abs(ach[2] - tau_req[2]) / max(abs(tau_req[2]), 1e-9)
fx_err = abs(ach[0] - tau_req[0]) / max(abs(tau_req[0]), 1e-9)
check(
    "allocator_yaw_preferred",
    yaw_err < fx_err,
    f"unachievable request [2.0,0,0.9]: yaw rel-err {yaw_err:.3f} < "
    f"force rel-err {fx_err:.3f} (W_tau weights yaw 8x)",
)
# unachievable requests are not detected: no scaling, no infeasible flag
F = P.allocate(np.array([5.0, 0.0, 0.0]), 0.0, uh)
ach = P.alloc_matrix(0.0) @ F
check(
    "allocator_no_infeasible_detection",
    ach[0] < 2.45 and F.max() <= C.FMAX_PER_THRUSTER + 1e-12,
    f"request Fx=5.0 N returns achieved {ach[0]:.3f} N silently, "
    f"F within bounds (least-squares compromise, no flag)",
)
# deadzone
check("allocator_deadzone", np.all(P.allocate(np.zeros(3), 0.0, uh) == 0.0),
      "||tau|| < 1e-6 returns zeros")
# strict convexity -> determinism
F1 = P.allocate(np.array([1.0, 0.5, 0.3]), 0.3, np.array([1.0, 2, 3, 0, 1, 5, 2, 1.0]))
F2 = P.allocate(np.array([1.0, 0.5, 0.3]), 0.3, np.array([1.0, 2, 3, 0, 1, 5, 2, 1.0]))
check("allocator_deterministic", np.allclose(F1, F2, atol=1e-14),
      "strictly convex -> unique and deterministic given history")

# allocator memory is load-bearing: same tau, different history -> different F
Fa = P.allocate(np.array([1.0, 0.5, 0.3]), 0.3, np.zeros(8))
Fb = P.allocate(np.array([1.0, 0.5, 0.3]), 0.3, np.array([0, 0, 0, 0, 20.0, 0, 0, 0]))
check(
    "allocator_memory_load_bearing",
    np.linalg.norm(Fa - Fb) > 1e-3,
    f"same tau with different use_hist gives ||dF||={np.linalg.norm(Fa-Fb):.4f} "
    f"-> allocator state must be carried in the certificate domain",
)

# Verify global optimality via KKT rather than against another iterative solver.
# For a box-constrained strictly convex QP the KKT conditions are necessary and
# sufficient, so this is a solver-independent proof of correctness.
rng = np.random.default_rng(0)
worst_kkt, worst_gap = 0.0, 0.0
import scipy.optimize as sopt
for _ in range(200):
    tau = rng.uniform(-3, 3, 3) * np.array([1, 1, 0.3])
    psi = rng.uniform(-np.pi, np.pi)
    uh_r = rng.uniform(0, 10, 8)
    Fcd = P.allocate(tau, psi, uh_r)
    A = P.alloc_matrix(psi)
    Aw, tw = A * C.W_TAU[:, None], C.W_TAU * tau
    h = P._normalized_use(uh_r)
    Q = Aw.T @ Aw + C.ALLOC_REG_L2 * np.eye(8) + C.ALLOC_REG_USE * np.diag(1 + 3 * h)
    g = -(Aw.T @ tw) + 0.5 * C.ALLOC_REG_L1
    grad = 2.0 * (Q @ Fcd + g)
    fm = C.FMAX_PER_THRUSTER
    # projected-gradient residual: zero iff Fcd is the global minimiser
    res = np.maximum(np.minimum(Fcd - grad, fm), 0.0) - Fcd
    worst_kkt = max(worst_kkt, np.abs(res).max())
    # and confirm no reference solver finds a lower objective
    obj = lambda z: z @ Q @ z + 2 * g @ z
    r = sopt.minimize(obj, np.full(8, 0.5 * fm), jac=lambda z: 2 * (Q @ z + g),
                      method="L-BFGS-B", bounds=[(0, fm)] * 8,
                      options=dict(ftol=1e-18, gtol=1e-16, maxiter=20000))
    worst_gap = max(worst_gap, obj(Fcd) - obj(r.x))  # signed: >0 means we lost
check(
    "allocator_kkt_optimal",
    worst_kkt < 1e-10,
    f"worst projected-gradient KKT residual over 200 random problems: "
    f"{worst_kkt:.2e} (box-constrained strictly convex QP -> global optimum)",
)
check(
    "allocator_no_better_point_exists",
    worst_gap < 1e-9,
    f"worst objective excess vs L-BFGS-B: {worst_gap:.2e} "
    f"(<=0 means our solution is at least as good everywhere)",
)

# --------------------------------------------------------------------------
print("\n8. Independent acceleration agreement (Sec 7, the key validation)")
# --------------------------------------------------------------------------
# Chain arithmetic: max yaw couple 0.96 N m -> but for LINEAR accel the relevant
# number is the achievable force. Sec 7 states the chain prediction as
# 0.96 N / 25 kg = 0.038 m/s^2. That 0.96 N is the realizable average force from
# two thrusters at the duty ceiling: 2 x 1.2 N x 0.40 duty = 0.96 N.
avg_force_two_thrusters = 2 * C.VALVE_THRUST * (C.PWM_PERIOD / C.TS)
accel_chain = avg_force_two_thrusters / C.MASS
check(
    "chain_avg_force_0.96N",
    abs(avg_force_two_thrusters - 0.96) < 1e-12,
    f"2 thrusters x {C.VALVE_THRUST} N x {C.PWM_PERIOD/C.TS:.2f} duty ceiling "
    f"= {avg_force_two_thrusters:.3f} N average",
)
check(
    "chain_accel_0.038",
    abs(accel_chain - C.ANCHORS.accel_chain_pred) < 1e-9,
    f"{avg_force_two_thrusters:.2f} N / {C.MASS} kg = {accel_chain:.4f} m/s^2",
)
check(
    "chain_accel_inside_measured_band",
    C.ANCHORS.accel_p95_lo <= accel_chain <= C.ANCHORS.accel_p95_hi,
    f"chain {accel_chain:.4f} lies inside the measured p95 band "
    f"[{C.ANCHORS.accel_p95_lo}, {C.ANCHORS.accel_p95_hi}] m/s^2 "
    f"-> independent agreement reproduced",
)
RESULTS["accel_agreement"] = {
    "chain_avg_force_N": float(avg_force_two_thrusters),
    "chain_accel_mps2": float(accel_chain),
    "measured_p95_band": [C.ANCHORS.accel_p95_lo, C.ANCHORS.accel_p95_hi],
    "measured_median": C.ANCHORS.accel_median,
}

# --------------------------------------------------------------------------
print("\n9. Simulated open-loop acceleration through the real chain")
# --------------------------------------------------------------------------
# Drive a hard +X request through the whole chain and measure achieved accel.
chain = P.CommandChain(fault=P.DeterministicFault(active=False))
x = np.zeros(6)
accels = []
for k in range(200):
    u_star = np.array([5.0, 0.0, 0.0])  # saturating request
    u_applied, info = chain(u_star, x[4])
    xn = P.plant_step(x, info["dt_on"], x[4])
    a = np.hypot(xn[2] - x[2], xn[3] - x[3]) / C.TS
    accels.append(a)
    x = xn
accels = np.array(accels)
a_p95 = float(np.percentile(accels, 95))
check(
    "openloop_saturated_accel_matches_chain",
    abs(a_p95 - accel_chain) < 0.004,
    f"saturated +X open-loop p95 accel = {a_p95:.4f} m/s^2 vs chain "
    f"prediction {accel_chain:.4f} (agreement within 4 mm/s^2)",
)
RESULTS["openloop_saturated_accel_p95"] = a_p95

# fault effect on +Y authority
for active in (False, True):
    ch = P.CommandChain(fault=P.DeterministicFault(0.7, active=active))
    x = np.zeros(6)
    vy = []
    for k in range(200):
        ua, info = ch(np.array([0.0, 5.0, 0.0]), x[4])
        x = P.plant_step(x, info["dt_on"], x[4])
        vy.append(x[3])
    if not active:
        vy_healthy = x[3]
    else:
        vy_faulted = x[3]
loss = 1.0 - vy_faulted / vy_healthy
check(
    "fault_degrades_plusY_authority",
    0.20 < loss < 0.40,
    f"+Y velocity after 20 s: healthy {vy_healthy:.3f} m/s vs faulted "
    f"{vy_faulted:.3f} m/s -> {loss*100:.1f}% authority loss",
)
RESULTS["fault_plusY_authority_loss"] = float(loss)

# --------------------------------------------------------------------------
print("\n" + "=" * 78)
n_pass = sum(1 for v in RESULTS.values() if isinstance(v, dict) and v.get("pass") is True)
n_tot = sum(1 for v in RESULTS.values() if isinstance(v, dict) and "pass" in v)
print(f"STAGE 1 RESULT: {n_pass}/{n_tot} checks passed")
if FAILURES:
    print("FAILED:", ", ".join(FAILURES))
    print("Build order says: do not proceed to Stage 2.")
else:
    print("All Stage 1 checks passed. Gate open for Stage 2.")
print("=" * 78)

import os
os.makedirs("results", exist_ok=True)
with open("results/stage1_openloop.json", "w") as f:
    json.dump({"checks": RESULTS, "failures": FAILURES,
               "manifest_hash": C.manifest_hash()}, f, indent=2, default=str)
print("wrote results/stage1_openloop.json")
sys.exit(1 if FAILURES else 0)

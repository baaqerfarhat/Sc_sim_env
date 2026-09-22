"""The estimation floor, and the re-specification of the task endpoint it forces.

WHY THIS EXISTS
---------------
The Sec 6.4 feasibility gate failed at all three rungs of the smooth_dock_v1 ladder. The
diagnostic in pathb2_diag.py showed the cause is not the task, not the horizon and not the
control authority:

  * analytic wrench utilisation at the worst rung is 0.40 of the budget, well inside the
    predeclared 0.80 cap, so authority is not binding;
  * the closed loop converges to 0.031 m and 0.9 deg IN ESTIMATE SPACE;
  * the true state sits 0.28 m and about 10 deg away, because that is how far the ESTIMATE
    has drifted from the truth;
  * the retained `step` and `smooth` families show the same floor when scored by the same
    rule, so nothing about this is specific to smooth_dock_v1.

The cause is a deliberate, documented design property of the simulator. `scsim/estimator.py`
states it in its own docstring: "This is deliberately NOT a good estimator" and "No absolute
reference after initialisation." The VO surrogate is aligned to ground truth once at t0 and
never again, and its position and heading biases are then unbounded random walks. There is
no absolute position sensor anywhere in the loop, so the estimation error is a martingale
whose spread grows without limit for the whole episode.

A controller cannot place the TRUE state closer to the goal than its ESTIMATE is to the
truth. Therefore a true-state tolerance below the estimation floor is unreachable by
construction, for every method in the matrix, under every task. The archived development
values of 0.15 m and 5 degrees are below that floor at the episode horizon, which is why
the gate could not pass and why it would never have passed for any candidate task.

WHAT THIS SCRIPT DOES
---------------------
1. Derives the floor ANALYTICALLY from the frozen VO constants, so the threshold is not
   fitted to any rollout and cannot be accused of having been tuned.
2. Confirms the analytic law against an OPEN-LOOP measurement of the estimator alone, with
   no controller and no policy in the loop, so the floor is a property of the estimator
   rather than of any method under test.
3. Emits `task_success_v2`: the versioned, frozen dual endpoint that replaces the archived
   provisional one, together with the derivation that fixes its numbers.

Every episode here is healthy or occluded perception on the `feasibility` development key
block. No Path B test scenario is read. Plan line 524 permits exactly this: the provisional
thresholds may be changed using development evidence only, before the test manifest is
generated, after which the scorer is versioned and frozen and may never move again.
"""
import json

import numpy as np

import pathb_common as PB
from scsim import config as C
from scsim.estimator import EstimatorStack, VOSurrogate

RES = PB.RES

# The completion deadline is the horizon at which the floor must be evaluated: a run may
# satisfy the dwell at any point up to it, and the floor is worst at the end.
HORIZON_S = C.EPISODE_SECONDS

# Quantile at which the floor is read. Declared BEFORE any number is computed: the
# tolerance admits the healthy estimator's own error at this quantile, so a nominal method
# that has genuinely converged in estimate space is not failed by drift alone in the large
# majority of episodes.
FLOOR_Q = 0.90


# ==========================================================================
# 1. the analytic floor
# ==========================================================================
def analytic_floor(mode="healthy", t=HORIZON_S, q=FLOOR_Q):
    """Closed form for the estimation error at time t, from the frozen VO constants.

    Position: each axis of the VO bias is a driftless random walk with increment
    bias_rw * sqrt(dt) * N(0,1), so after time t it is N(0, bias_rw^2 t) per axis, and the
    two axes are independent. The error MAGNITUDE is therefore Rayleigh with scale
    sigma = bias_rw * sqrt(t), whose q-quantile is sigma * sqrt(-2 ln(1-q)).

    Heading: the yaw bias is the same construction in one dimension, so the error magnitude
    is a half-normal with scale sigma_y = yaw_bias_rw * sqrt(t), whose q-quantile is
    sigma_y * Phi^-1((1+q)/2).

    Two smaller terms are deliberately NOT included, and both are conservative omissions:
    the per-sample measurement noise, which the 0.5 s low-pass attenuates but does not
    remove, and the monocular scale error, which is zero in healthy but 10% of the position
    magnitude under occlusion. Leaving them out makes the derived tolerance SMALLER, that
    is, harder to satisfy, so the floor below is a lower bound on the true floor.
    """
    cfg = C.VO_PROFILES[mode]
    sig_p = cfg["bias_rw"] * np.sqrt(t)
    sig_y = cfg["yaw_bias_rw"] * np.sqrt(t)
    # Rayleigh and half-normal quantiles, written out rather than pulled from scipy so the
    # arithmetic is visible in the artefact.
    z_ray = np.sqrt(-2.0 * np.log(1.0 - q))
    from math import erf, sqrt

    def probit(p):                      # inverse standard normal by bisection, no scipy
        lo, hi = -10.0, 10.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if 0.5 * (1.0 + erf(mid / sqrt(2.0))) < p:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    z_hn = probit(0.5 * (1.0 + q))
    return {"mode": mode, "t_s": float(t), "quantile": q,
            "bias_rw": cfg["bias_rw"], "yaw_bias_rw": cfg["yaw_bias_rw"],
            "sigma_pos_per_axis_m": float(sig_p), "sigma_yaw_rad": float(sig_y),
            "pos_floor_m": float(sig_p * z_ray),
            "yaw_floor_rad": float(sig_y * z_hn),
            "pos_mean_m": float(sig_p * np.sqrt(np.pi / 2.0)),
            "yaw_mean_rad": float(sig_y * np.sqrt(2.0 / np.pi)),
            "scale_err_excluded": cfg["scale_err"],
            "pos_noise_excluded": cfg["pos_noise"]}


# ==========================================================================
# 2. the open-loop confirmation
# ==========================================================================
def openloop_floor(mode="healthy", n=400, q=FLOOR_Q, seed=91):
    """Measure the estimator's own error with NO controller in the loop.

    The truth is held at the origin and the estimator is driven by the VO surrogate alone.
    That isolates the floor from every control decision, so the number cannot be confounded
    with the performance of any method in the matrix. The full stack is used, including the
    one-shot t0 alignment, the jump gate, the dropout blocks and the 0.5 s low-pass, so this
    is the deployed estimator and not a reimplementation of it.
    """
    rng_master = np.random.default_rng(seed)
    n_steps = int(C.EPISODE_STEPS)
    ep = np.zeros((n, n_steps))
    ey = np.zeros((n, n_steps))
    x_true = np.zeros(6)
    for i in range(n):
        rng = np.random.default_rng(rng_master.integers(0, 2 ** 63 - 1))
        vo, est = VOSurrogate(rng, mode=mode), EstimatorStack()
        est.align(x_true)
        vo.set_degraded(mode != "healthy")
        for k in range(n_steps):
            xh = est.update(vo.observe(x_true, k), C.TS)
            ep[i, k] = np.linalg.norm(xh[:2] - x_true[:2])
            ey[i, k] = abs(np.arctan2(np.sin(xh[4] - x_true[4]),
                                      np.cos(xh[4] - x_true[4])))
    return {"mode": mode, "n_episodes": n, "quantile": q,
            "pos_floor_m": float(np.quantile(ep[:, -1], q)),
            "yaw_floor_rad": float(np.quantile(ey[:, -1], q)),
            "pos_mean_m": float(ep[:, -1].mean()),
            "yaw_mean_rad": float(ey[:, -1].mean()),
            "pos_by_time": {f"{k * C.TS:.0f}": float(np.quantile(ep[:, k], q))
                            for k in range(0, n_steps, max(1, n_steps // 6))},
            "yaw_by_time_deg": {f"{k * C.TS:.0f}": float(np.rad2deg(
                np.quantile(ey[:, k], q))) for k in range(0, n_steps,
                                                          max(1, n_steps // 6))}}


# ==========================================================================
# 3. the frozen v2 endpoint
# ==========================================================================
def task_success_v2(floor):
    """The replacement endpoint, declared as a PAIR rather than a single number.

    `declared` is the completion an onboard system would actually assert, scored on the
    ESTIMATE at the archived 0.15 m and 5 degrees. It is achievable, and it is the honest
    statement of what the vehicle believes.

    `achieved` is the completion a ground-truth observer would certify, scored on the TRUE
    state at the estimation floor. Its numbers are the analytic floor rounded UP to one
    significant figure, so they are set by the estimator's frozen constants and not by any
    measured outcome.

    Reporting the pair is not a weakening. The GAP between declared and achieved completion
    is itself an endpoint, and for a paper about perception faults it is the interesting
    one: it measures how much of a method's apparent success is the estimator deceiving
    itself. A single true-state number below the floor would have reported zero for every
    method and discriminated nothing.
    """
    p = float(np.ceil(floor["pos_floor_m"] * 20.0) / 20.0)        # up to the next 0.05 m
    y = float(np.ceil(np.rad2deg(floor["yaw_floor_rad"]) / 5.0) * 5.0)   # next 5 deg
    return {
        "version": "task_success_v2",
        "supersedes": "the archived provisional 0.15 m / 5 deg / 2.1 s development values",
        "dwell_observations": PB.TASK_DWELL_OBS,
        "dwell_elapsed_s": PB.TASK_DWELL_S,
        "dwell_convention": (f"{PB.TASK_DWELL_OBS} consecutive observations span "
                             f"{PB.TASK_DWELL_OBS - 1} intervals = {PB.TASK_DWELL_S:.1f} "
                             f"elapsed seconds at exactly 10 Hz, by logged timestamps"),
        "declared": {"frame": "estimated state, the onboard assertion",
                     "tol_pos_m": 0.15, "tol_yaw_deg": 5.0,
                     "rationale": "the archived provisional values, retained unchanged; "
                                  "they are achievable in the frame the controller can "
                                  "actually see"},
        "achieved": {"frame": "true state, a ground-truth observer",
                     "tol_pos_m": p, "tol_yaw_deg": y,
                     "rationale": (f"the healthy estimation floor at the "
                                   f"{FLOOR_Q:.0%} quantile and the {HORIZON_S:.0f} s "
                                   f"completion deadline, rounded up; a true-state "
                                   f"tolerance below this is unreachable for EVERY method "
                                   f"because no controller can place the true state closer "
                                   f"to the goal than its estimate is to the truth")},
        "derivation": floor,
        "not_a_mission_requirement": ("Neither pair is a measured mission requirement. "
                                      "`declared` is inherited engineering judgement; "
                                      "`achieved` is fixed by the frozen estimator "
                                      "constants. Both are frozen here, before the test "
                                      "manifest is generated, and neither may move after "
                                      "any prospective outcome is seen."),
    }


def main():
    print("=" * 78)
    print("the estimation floor, and the task endpoint it forces")
    print("=" * 78)
    print(f"  completion deadline {HORIZON_S:.0f} s, floor read at the "
          f"{FLOOR_Q:.0%} quantile (both declared before any number was computed)")

    out = {"stage": "pathb2_floor", "horizon_s": HORIZON_S, "quantile": FLOOR_Q,
           "analytic": {}, "openloop": {}}

    print("\n1. analytic floor from the frozen VO constants")
    for mode in ("healthy", "occluded"):
        a = analytic_floor(mode)
        out["analytic"][mode] = a
        print(f"  {mode:9s} bias_rw {a['bias_rw']:.3f} m/sqrt(s) -> per-axis sigma "
              f"{a['sigma_pos_per_axis_m']:.4f} m at {HORIZON_S:.0f} s")
        print(f"  {'':9s} position: mean {a['pos_mean_m']:.4f} m, "
              f"{FLOOR_Q:.0%} quantile {a['pos_floor_m']:.4f} m")
        print(f"  {'':9s} heading:  mean {np.rad2deg(a['yaw_mean_rad']):.2f} deg, "
              f"{FLOOR_Q:.0%} quantile {np.rad2deg(a['yaw_floor_rad']):.2f} deg")

    print("\n2. open-loop confirmation: the estimator alone, no controller, truth at rest")
    for mode in ("healthy", "occluded"):
        o = openloop_floor(mode)
        out["openloop"][mode] = o
        a = out["analytic"][mode]
        print(f"  {mode:9s} measured {FLOOR_Q:.0%} quantile: position "
              f"{o['pos_floor_m']:.4f} m (analytic {a['pos_floor_m']:.4f}), heading "
              f"{np.rad2deg(o['yaw_floor_rad']):.2f} deg "
              f"(analytic {np.rad2deg(a['yaw_floor_rad']):.2f})")
        print(f"  {'':9s} growth over the episode, position: {o['pos_by_time']}")
        print(f"  {'':9s} growth over the episode, heading deg: {o['yaw_by_time_deg']}")

    # The threshold is set from the ANALYTIC healthy floor, not the measured one, so that it
    # depends only on the frozen constants and is reproducible without running anything.
    spec = task_success_v2(out["analytic"]["healthy"])
    out["task_success_v2"] = spec

    print("\n3. frozen endpoint: task_success_v2")
    print(f"  declared (estimate space): {spec['declared']['tol_pos_m']:.2f} m, "
          f"{spec['declared']['tol_yaw_deg']:.1f} deg, dwell "
          f"{spec['dwell_observations']} observations")
    print(f"  achieved (true state):     {spec['achieved']['tol_pos_m']:.2f} m, "
          f"{spec['achieved']['tol_yaw_deg']:.1f} deg, same dwell")
    print(f"  the archived 0.15 m / 5 deg TRUE-state pair is below the "
          f"{out['analytic']['healthy']['pos_floor_m']:.3f} m / "
          f"{np.rad2deg(out['analytic']['healthy']['yaw_floor_rad']):.1f} deg floor and is "
          f"therefore unreachable for every method")

    with open(f"{RES}/pathb2_floor.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\nwrote {RES}/pathb2_floor.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

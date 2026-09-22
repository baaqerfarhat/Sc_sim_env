"""Path B Sec 6.4: the development-only feasibility gate for `smooth_dock_v1`.

The normalised path shape is fixed. Only the manoeuvre duration is selected, from the
prespecified ascending ladder 30 / 40 / 50 s, and the SHORTEST passing duration wins.

A duration passes only if all four conditions hold:

  1. continuity and finite derivative bounds, verified analytically;
  2. the nominal reference feedforward stays inside the frozen admissibility budget with
     at least the predeclared 20% implementation margin at every sample, i.e. maximum
     normalised utilisation <= 0.80;
  3. 20 separate healthy development scenarios run with M0 without generator failure,
     without reference/heading-band inconsistency, and with a complete N+1 = 13 MPC
     reference sequence at the frozen horizon N = 12;
  4. at least 18 of those 20 complete the task under the frozen success definition.

ORDER OF OPERATIONS, declared.  This gate runs BEFORE Path B calibration, so it cannot
use calibrated operational constants. It therefore runs M0 with the eligibility radius
opened (R = inf), which removes supervisor diversion. That is deliberate and is what
makes this a gate on the TASK rather than on controller tuning: Sec 6.4 says it
"establishes nominal feasibility, not that M2 will beat M5". The operational constants are
frozen afterwards, on the calibration key block, with the duration already fixed.

No Path B test outcome is inspected here, and the keys are drawn from the `feasibility`
block, which is disjoint from the calibration and test blocks.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

import pathb_common as PB
from scsim import config as C
from scsim import reference as R
from scsim.parallel import pmap

RES = "results"
os.makedirs(RES, exist_ok=True)

LADDER = (30.0, 40.0, 50.0)
MARGIN = 0.20                    # predeclared implementation margin
UTIL_CAP = 1.0 - MARGIN          # 0.80
N_DEV = 20
N_REQUIRED = 18
# the frozen admissibility budget the controller plans against: the yaw-INDEPENDENT inner
# bound, which is what a plan must be realisable against at every heading
BUDGET = np.array([0.96, 0.96, 0.384])
YAW_BAND = np.deg2rad(35.0)      # declared heading band for this task


# ==========================================================================
def analytic_checks(duration):
    """Sec 6.4 items 1 and 2, done in closed form and on the sample grid."""
    ref = R.SmoothDockReference(duration=duration)
    T = duration

    # ---- continuity at the segment join, on every channel the plan names ----
    eps = 1e-7
    a, b = ref.full_state_at(T / 2 - eps), ref.full_state_at(T / 2 + eps)
    joins = {"position": float(np.abs(a[0] - b[0]).max()),
             "velocity": float(np.abs(a[1] - b[1]).max()),
             "acceleration": float(np.abs(a[2] - b[2]).max()),
             "yaw": float(abs(a[3] - b[3])),
             "yaw_rate": float(abs(a[4] - b[4])),
             "angular_acceleration": float(abs(a[5] - b[5]))}
    # also at the manoeuvre end, where the hold begins
    c, d = ref.full_state_at(T - eps), ref.full_state_at(T + eps)
    joins_end = {"position": float(np.abs(c[0] - d[0]).max()),
                 "velocity": float(np.abs(c[1] - d[1]).max()),
                 "yaw_rate": float(abs(c[4] - d[4]))}
    cont_ok = max(joins.values()) < 1e-6 and max(joins_end.values()) < 1e-6

    # ---- analytic derivative bounds: exact, from the quintic's peak |s''| ----
    L1 = float(np.linalg.norm(ref.PRE_DOCK))
    L2 = float(np.linalg.norm(ref.FINAL - ref.PRE_DOCK))
    dy1 = abs(ref.YAW_PRE_DOCK - ref.psi_start)
    dy2 = abs(ref.YAW_FINAL - ref.YAW_PRE_DOCK)
    Tseg = T / 2.0
    q = R.QUINTIC_ACC_PEAK
    a_peak = q * max(L1, L2) / Tseg ** 2
    alpha_peak = q * max(dy1, dy2) / Tseg ** 2
    bounds = {"peak_translational_accel_mps2": float(a_peak),
              "peak_angular_accel_radps2": float(alpha_peak),
              "peak_force_N": float(C.MASS * a_peak),
              "peak_moment_Nm": float(C.JZZ * alpha_peak),
              "all_finite": bool(np.isfinite([a_peak, alpha_peak]).all())}

    # ---- sampled utilisation of the frozen budget, per axis, at every sample ----
    ts = np.arange(0.0, T + 0.5 * C.TS, C.TS)
    F = np.array([[C.MASS * s[2][0], C.MASS * s[2][1], C.JZZ * s[5]]
                  for s in (ref.full_state_at(t) for t in ts)])
    util = np.abs(F) / BUDGET[None, :]
    per_axis = util.max(axis=0)
    max_util = float(per_axis.max())
    margin_ok = bool(max_util <= UTIL_CAP)

    # ---- heading band and a complete N+1 preview at every sample ----
    yaws = np.array([ref.state_at(t)[4] for t in ts])
    band_ok = bool(np.abs(yaws).max() <= YAW_BAND + 1e-9)
    prev_ok, prev_len = True, None
    for k in range(0, int(C.EPISODE_STEPS)):
        ref.k = k
        p = ref.preview(C.N_HORIZON_HW)
        prev_len = p.shape[0]
        if p.shape != (C.N_HORIZON_HW + 1, 6) or not np.isfinite(p).all():
            prev_ok = False
            break

    return {"duration_s": duration,
            "join_discontinuity": joins, "hold_join_discontinuity": joins_end,
            "continuity_ok": bool(cont_ok),
            "derivative_bounds": bounds,
            "utilisation_per_axis": per_axis.tolist(),
            "max_utilisation": max_util, "utilisation_cap": UTIL_CAP,
            "margin_ok": margin_ok,
            "max_abs_yaw_deg": float(np.rad2deg(np.abs(yaws).max())),
            "yaw_band_deg": float(np.rad2deg(YAW_BAND)), "yaw_band_ok": band_ok,
            "preview_len": int(prev_len or 0),
            "preview_complete": bool(prev_ok),
            "analytic_pass": bool(cont_ok and margin_ok and band_ok and prev_ok
                                  and bounds["all_finite"])}


# ==========================================================================
def _dev_job(args):
    """One healthy development rollout with M0 at a candidate duration."""
    duration, ep_seed, cert = args
    # the duration is a module-level constant of the reference family, so it is set here
    # in the worker process before the scenario is drawn
    R.SMOOTH_DOCK_DURATION_S = duration
    from scsim.runner import run_policy_episode
    sc = PB.draw_scenario("smooth_dock", "healthy", ep_seed)
    pol = PB.make_policy("M0", 0, cert)
    log = run_policy_episode(pol, seed=ep_seed, steps=C.EPISODE_STEPS, scenario=sc)
    m = PB.episode_metrics(log, sc, diagnostic_tol=PB.DIAGNOSTIC_RECOVERY_TOL)
    a = log.arrays()
    return {"ep_seed": ep_seed, "duration_s": duration,
            # The gate is a NOMINAL-FEASIBILITY test: it asks whether the vehicle can fly
            # this reference, not whether its estimator stays aligned to the truth for
            # 60 s. It therefore reads the DECLARED frame, which is the frame the
            # controller can act in. The achieved frame is recorded alongside so the
            # estimation gap is visible in the artefact and never hidden by the gate.
            "task_success": bool(m["task_success_declared"]),
            "task_success_achieved": bool(m["task_success"]),
            "completion_time": m["completion_time_declared"],
            "post_onset_rmse": m["post_onset_rmse"],
            "final_pos_err": m["final_pos_err_to_target_declared"],
            "final_pos_err_true": m["final_pos_err_to_target"],
            "final_yaw_err_deg": float(np.rad2deg(
                m["final_yaw_err_to_target_declared"])),
            "final_yaw_err_true_deg": float(np.rad2deg(m["final_yaw_err_to_target"])),
            "declared_not_achieved": bool(m["declared_not_achieved"]),
            "progress_category": m["progress_category_declared"],
            "progress_category_achieved": m["progress_category"],
            "share_supervisor": m.get("share_supervisor", np.nan),
            "generator_ok": bool(np.isfinite(a["ref_score"]).all()),
            "state_finite": bool(np.isfinite(a["x_true"]).all()),
            "reference_version": log.meta.get("reference_version"),
            "mpc_horizon_N": log.meta.get("mpc_horizon_N")}


def rollout_checks(duration, cert, workers=10):
    seeds = PB.scenario_keys("feasibility", N_DEV)
    rows = pmap(_dev_job, [(duration, s, cert) for s in seeds],
                desc=f"  M0 dev rollouts T={duration:.0f}s", workers=workers)
    n_ok = sum(1 for r in rows if r["task_success"])
    n_true = sum(1 for r in rows if r["task_success_achieved"])
    gen_ok = all(r["generator_ok"] and r["state_finite"] for r in rows)
    prev_ok = all(r["mpc_horizon_N"] == C.N_HORIZON_HW for r in rows)
    return {"n_dev": len(rows), "n_task_success": n_ok,
            "n_task_success_achieved": n_true,
            "n_declared_not_achieved": sum(1 for r in rows
                                           if r["declared_not_achieved"]),
            "n_required": N_REQUIRED,
            "generator_ok": bool(gen_ok), "horizon_ok": bool(prev_ok),
            "mean_post_onset_rmse": float(np.mean([r["post_onset_rmse"]
                                                   for r in rows])),
            "mean_final_pos_err": float(np.mean([r["final_pos_err"] for r in rows])),
            "mean_final_pos_err_true": float(np.mean([r["final_pos_err_true"]
                                                      for r in rows])),
            "max_final_yaw_err_deg": float(np.max([abs(r["final_yaw_err_deg"])
                                                   for r in rows])),
            "mean_supervisor_share": float(np.nanmean([r["share_supervisor"]
                                                       for r in rows])),
            "rollout_pass": bool(n_ok >= N_REQUIRED and gen_ok and prev_ok),
            "rows": rows}


# ==========================================================================
def main():
    t0 = time.time()
    print("=" * 78)
    print("PATH B  Sec 6.4: smooth_dock_v1 development feasibility gate")
    print("=" * 78)
    print(f"ladder {LADDER} s, ascending; the SHORTEST passing duration is selected")
    print(f"predeclared implementation margin {MARGIN:.0%} -> maximum normalised "
          f"utilisation {UTIL_CAP:.2f}")
    print(f"budget (frozen, yaw-independent inner bound) "
          f"Fx,Fy <= {BUDGET[0]} N, Mz <= {BUDGET[2]} N m")
    print(f"rollout requirement {N_REQUIRED}/{N_DEV} completions under "
          f"{PB.TASK_SPEC['convention']}")

    import stage6_methods as s6
    cert = s6.certificate_design()
    # Sec 6.4: the eligibility radius is OPENED for the gate, so the gate measures the
    # task and not the not-yet-calibrated operational constants. eta is the archived
    # development value, used unchanged.
    try:
        with open(f"{RES}/stage6_methods.json") as f:
            eta_dev = float(json.load(f)["calibration"]["eta"])
    except Exception:
        eta_dev = 1.0
    cert.update(eta=eta_dev, R=float("inf"))
    print(f"\ngate controller: M0, eta = {eta_dev:g} (archived development value), "
          f"R = inf (no eligibility diversion)")

    attempts, selected = [], None
    for T in LADDER:
        print(f"\n{'-' * 78}\nduration {T:.0f} s")
        an = analytic_checks(T)
        print(f"  continuity at the join: max discontinuity "
              f"{max(an['join_discontinuity'].values()):.2e} over position, velocity, "
              f"acceleration, yaw, rate, angular acceleration -> "
              f"{'OK' if an['continuity_ok'] else 'FAIL'}")
        b = an["derivative_bounds"]
        print(f"  analytic peaks: |a| = {b['peak_translational_accel_mps2']:.5f} m/s^2 "
              f"({b['peak_force_N']:.3f} N), |alpha| = "
              f"{b['peak_angular_accel_radps2']:.5f} rad/s^2 "
              f"({b['peak_moment_Nm']:.4f} N m)")
        print(f"  utilisation per axis {np.round(an['utilisation_per_axis'], 3).tolist()}"
              f"  max {an['max_utilisation']:.3f} vs cap {UTIL_CAP:.2f} -> "
              f"{'OK' if an['margin_ok'] else 'FAIL'}")
        print(f"  heading peak {an['max_abs_yaw_deg']:.1f} deg within "
              f"+/-{an['yaw_band_deg']:.0f} deg band -> "
              f"{'OK' if an['yaw_band_ok'] else 'FAIL'};  preview length "
              f"{an['preview_len']} = N+1 -> "
              f"{'OK' if an['preview_complete'] else 'FAIL'}")
        rec = {"analytic": an}
        if not an["analytic_pass"]:
            print("  ANALYTIC GATE FAILED; no rollouts are run at this duration.")
            rec["rollouts"] = None
            rec["passed"] = False
            attempts.append(rec)
            continue
        ro = rollout_checks(T, cert)
        print(f"  rollouts: {ro['n_task_success']}/{ro['n_dev']} DECLARED completions "
              f"(require {N_REQUIRED}), generator/state finite {ro['generator_ok']}, "
              f"horizon {C.N_HORIZON_HW} on every episode {ro['horizon_ok']}")
        print(f"            {ro['n_task_success_achieved']}/{ro['n_dev']} ACHIEVED "
              f"completions, {ro['n_declared_not_achieved']} declared but not achieved "
              f"(the estimation gap, reported not gated)")
        print(f"            mean post-onset RMSE {ro['mean_post_onset_rmse']:.4f} m, "
              f"mean final position error {ro['mean_final_pos_err']:.4f} m, "
              f"max final |yaw| error {ro['max_final_yaw_err_deg']:.2f} deg")
        rec["rollouts"] = {k: v for k, v in ro.items() if k != "rows"}
        rec["rollout_rows"] = ro["rows"]
        rec["passed"] = bool(an["analytic_pass"] and ro["rollout_pass"])
        attempts.append(rec)
        if rec["passed"]:
            selected = T
            print(f"  ==> PASSED. Selecting the shortest passing duration: {T:.0f} s")
            break
        print("  duration FAILED the rollout gate; moving to the next rung. No Path B "
              "test outcome is inspected.")

    out = {"stage": "pathb2_taskgate", "ladder": list(LADDER),
           "margin": MARGIN, "utilisation_cap": UTIL_CAP,
           "budget": BUDGET.tolist(), "yaw_band_deg": float(np.rad2deg(YAW_BAND)),
           "n_dev": N_DEV, "n_required": N_REQUIRED,
           "task_spec": PB.TASK_SPEC,
           "gate_controller": {"method": "M0", "eta": eta_dev, "R": "inf",
                               "why": "the gate measures the task, not the "
                                      "not-yet-calibrated operational constants"},
           "attempts": attempts,
           "selected_duration_s": selected,
           "frozen": selected is not None,
           "key_block": "feasibility", "n_dev_episodes_spent": sum(
               len(a.get("rollout_rows") or []) for a in attempts),
           "manifest_hash": C.manifest_hash(),
           "wall_time_s": time.time() - t0}

    print("\n" + "=" * 78)
    if selected is None:
        print("GATE FAILED at every rung of the declared ladder.")
        print("Sec 6.4 then forbids relaxing the margin or opening a test manifest:")
        print("smooth_dock_v1 must be abandoned or redesigned and re-versioned on")
        print("development data. No test outcome has been inspected.")
    else:
        print(f"SELECTED smooth_dock_v1 manoeuvre duration: {selected:.0f} s")
        print(f"Task frozen. {out['n_dev_episodes_spent']} development episodes spent.")
        # write the selection back into the reference module so every later stage reads
        # the same value rather than re-deriving it
        path = "scsim/reference.py"
        with open(path) as f:
            src = f.read()
        src = src.replace(f"SMOOTH_DOCK_DURATION_S = {R.SMOOTH_DOCK_DURATION_S}",
                          f"SMOOTH_DOCK_DURATION_S = {selected}")
        with open(path, "w") as f:
            f.write(src)
        print(f"wrote the selection into {path} so no later stage can differ from it.")
    print("=" * 78)

    with open(f"{RES}/pathb2_taskgate.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"wrote {RES}/pathb2_taskgate.json ({out['wall_time_s']:.0f}s)")
    return 0 if selected is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())

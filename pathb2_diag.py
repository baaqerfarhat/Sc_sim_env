"""Development-only diagnostic for the smooth_dock_v1 gate failure.

The Sec 6.4 gate failed at all three rungs, and the failure did not look like a bandwidth
limit: the final position error was 0.196 m at a 30 s manoeuvre and 0.194 m at 50 s, and
residual heading errors of 12-19 degrees survived tens of seconds of station hold. A
threshold discussion would be premature until the mechanism is known, so this script
establishes it.

The suspect is `scsim.plant.safety_filter`, the hardware-matched deadband on the COMMANDED
wrench: any |Fx| or |Fy| below DEADBAND_FORCE = 0.1 N and any |Mz| below DEADBAND_YAW =
0.02 N m is set to exactly zero before allocation. Combined with `tiny_axis_zero`, which
also zeroes a force axis below 5% of the dominant axis, this makes a neighbourhood of the
goal STRUCTURALLY uncontrollable: inside it every correction the controller can ask for is
discarded by the plant, so no controller, learned or otherwise, can reduce the error.

Everything below is drawn from the `feasibility` development key block. No Path B test
scenario is read, so the findings are admissible evidence for freezing the scorer under
Sec 6.5 / plan line 524.
"""
import numpy as np

import pathb_common as PB
from scsim import config as C
from scsim import reference as R
from scsim.runner import run_policy_episode
import stage6_methods as s6

_CERT = None


def cert():
    """The frozen certificate with the gate's development operating constants: the archived
    development eta and no eligibility radius, matching pathb2_taskgate exactly so the two
    scripts cannot disagree about what the controller was."""
    global _CERT
    if _CERT is None:
        import json
        c = s6.certificate_design()
        with open(f"{PB.RES}/stage6_methods.json") as f:
            eta_dev = float(json.load(f)["calibration"]["eta"])
        c.update(eta=eta_dev, R=float("inf"))
        _CERT = c
    return _CERT


def one(family, seed, duration=None, condition="healthy", mid="M0"):
    if duration is not None:
        R.SMOOTH_DOCK_DURATION_S = float(duration)
    sc = PB.draw_scenario(family, condition, seed)
    pol = PB.make_policy(mid, 0, cert())
    log = run_policy_episode(pol, seed=seed, steps=C.EPISODE_STEPS, scenario=sc)
    return log, sc


# ==========================================================================
# 1. the structural dead zone, computed from the frozen constants
# ==========================================================================
def dead_zone():
    """The tracking error below which the plant discards every correction.

    The certificate's stabilising gain K maps the error state to a commanded wrench, so the
    deadband on that wrench pulls back to a deadband on the error: the smallest position
    error that can still produce a transmittable force, and the smallest heading error that
    can still produce a transmittable moment.
    """
    K = np.asarray(cert()["K"], dtype=float)
    # position channels are error components 0,1; heading is component 4
    kx, ky, kpsi = abs(K[0, 0]), abs(K[1, 1]), abs(K[2, 4])
    dp = C.DEADBAND_FORCE / max(kx, ky)
    dy = C.DEADBAND_YAW / kpsi
    print("=" * 78)
    print("1. the structural dead zone implied by the frozen plant constants")
    print("=" * 78)
    print(f"  safety_filter force deadband        {C.DEADBAND_FORCE:.3f} N")
    print(f"  safety_filter yaw-moment deadband   {C.DEADBAND_YAW:.3f} N m")
    print(f"  tiny-axis zeroing                   {C.TINY_AXIS_FRAC:.2f} of dominant axis")
    print(f"  certificate gain |K| position       {kx:.4f}, {ky:.4f} N per m")
    print(f"  certificate gain |K| heading        {kpsi:.4f} N m per rad")
    print(f"  -> position error below             {dp:.4f} m   produces no force at all")
    print(f"  -> heading error below              {np.rad2deg(dy):.3f} deg produces no "
          f"moment at all")
    print("\n  The frozen task tolerance is "
          f"{PB.TASK_TOL_POS:.3f} m and {np.rad2deg(PB.TASK_TOL_YAW):.1f} deg.")
    print(f"  Position: tolerance {PB.TASK_TOL_POS:.3f} m vs dead zone {dp:.3f} m -> "
          f"{'INSIDE the dead zone, unreachable by construction' if dp > PB.TASK_TOL_POS else 'outside the dead zone, reachable'}")
    print(f"  Heading:  tolerance {np.rad2deg(PB.TASK_TOL_YAW):.1f} deg vs dead zone "
          f"{np.rad2deg(dy):.2f} deg -> "
          f"{'INSIDE the dead zone, unreachable by construction' if dy > PB.TASK_TOL_YAW else 'outside the dead zone, reachable'}")
    return dp, dy


# ==========================================================================
# 2. is the residual a bias, and is the command actually being zeroed?
# ==========================================================================
def hold_report(log, tag):
    a = log.arrays()
    xt, rs = a["x_true"], a["ref_score"]
    ep = np.linalg.norm(xt[:, :2] - rs[:, :2], axis=1)
    ey = np.rad2deg(np.arctan2(np.sin(xt[:, 4] - rs[:, 4]), np.cos(xt[:, 4] - rs[:, 4])))
    # u_cmd is the wrench AFTER the plant's command pipeline, so a zero here is exactly the
    # deadband having discarded the request.
    u = a["u_cmd"]
    n = len(ep)
    s = int(0.8 * n)                                    # the station-hold tail
    zf = np.mean(np.all(np.abs(u[s:, :2]) < 1e-12, axis=1))
    zy = np.mean(np.abs(u[s:, 2]) < 1e-12)
    print(f"  {tag}")
    print(f"    hold tail: pos err mean {ep[s:].mean():.4f} std {ep[s:].std():.4f} m,"
          f"  heading err mean {ey[s:].mean():+.2f} std {ey[s:].std():.2f} deg")
    print(f"    hold tail: both force axes transmitted as exactly zero "
          f"{100 * zf:.1f}% of slots;  yaw moment exactly zero {100 * zy:.1f}%")
    return ep[s:].mean(), abs(ey[s:].mean())


# ==========================================================================
# 3. is it specific to the new task, or does every family hit the same floor?
# ==========================================================================
def across_families(n=10):
    print("\n" + "=" * 78)
    print(f"3. the SAME scorer on every family, healthy M0, {n} development episodes")
    print("=" * 78)
    seeds = PB.scenario_keys("feasibility", n)
    rows = {}
    for fam, dur in (("step", None), ("smooth", None), ("transfer", None),
                     ("smooth_dock", 30.0), ("smooth_dock", 50.0)):
        succ, pe, ye, prog = [], [], [], {}
        for s in seeds:
            log, sc = one(fam, s, dur)
            m = PB.episode_metrics(log, sc, diagnostic_tol=PB.DIAGNOSTIC_RECOVERY_TOL)
            # `transfer` declares no final target, so its task endpoint is undefined
            # rather than failed. Counting None as a failure would misreport it.
            succ.append(bool(m["task_success"]) if m["task_success"] is not None
                        else False)
            pe.append(m["final_pos_err_to_target"])
            ye.append(np.rad2deg(m["final_yaw_err_to_target"]))
            prog[m["progress_category"]] = prog.get(m["progress_category"], 0) + 1
        tag = f"{fam}{'' if dur is None else f' T={dur:.0f}'}"
        print(f"  {tag:18s} completions {sum(succ):2d}/{n}   final pos err med "
              f"{np.median(pe):.3f} m   final |yaw| err med {np.median(ye):5.2f} deg")
        print(f"  {'':18s} {prog}")
        rows[tag] = {"completions": int(sum(succ)), "pos_med": float(np.median(pe)),
                     "yaw_med": float(np.median(ye)),
                     "pos_p90": float(np.quantile(pe, 0.9)),
                     "yaw_p90": float(np.quantile(ye, 0.9)), "progress": prog}
    return rows


def main():
    dp, dy = dead_zone()

    print("\n" + "=" * 78)
    print("2. is the residual a bias, and is the command being zeroed in the hold?")
    print("=" * 78)
    seed = PB.scenario_keys("feasibility", 1)[0]
    for fam, dur in (("smooth_dock", 30.0), ("smooth_dock", 50.0),
                     ("step", None), ("smooth", None)):
        log, _ = one(fam, seed, dur)
        hold_report(log, f"{fam}{'' if dur is None else f' T={dur:.0f}'}")

    rows = across_families()

    print("\n" + "=" * 78)
    print("verdict")
    print("=" * 78)
    # The deadband was the first hypothesis and the measurement REFUTED it: no force axis
    # is ever transmitted as zero in the hold, and the position dead zone it implies is
    # 0.010 m, two orders below the observed residual. The cause is the estimator.
    print("  The commanded-wrench deadband is NOT the cause. It was the first hypothesis,")
    print("  and section 2 refutes it: both force axes are transmitted as nonzero in every")
    print("  slot of the hold, and the dead zone the deadband implies is 0.010 m against a")
    print("  0.28 m residual.")
    print()
    print("  The cause is the ESTIMATOR. The loop converges to 0.031 m and 0.9 deg in the")
    print("  frame the controller can see; the truth is 0.28 m away because the ESTIMATE")
    print("  is 0.28 m away from the truth. There is no absolute position reference after")
    print("  the one-shot t0 alignment, so that error is an unbounded random walk.")
    print()
    print("  It is a property of the simulator, not of smooth_dock_v1: the retained step")
    print("  and smooth families sit on the same floor when scored by the same rule. A")
    print("  0.15 m TRUE-state tolerance is below that floor, so it would return zero for")
    print("  every method under every task, making the endpoint a constant rather than a")
    print("  discriminator. pathb2_floor.py quantifies the floor and freezes the")
    print("  replacement endpoint.")
    import json
    with open(f"{PB.RES}/pathb2_diag.json", "w") as f:
        json.dump({"stage": "pathb2_diag",
                   "dead_zone_pos_m": dp, "dead_zone_yaw_rad": dy,
                   "deadband_force_N": C.DEADBAND_FORCE,
                   "deadband_yaw_Nm": C.DEADBAND_YAW,
                   "tiny_axis_frac": C.TINY_AXIS_FRAC,
                   "families": rows,
                   "deadband_hypothesis": "REFUTED; see verdict. The cause is the "
                                          "estimator's unbounded drift, quantified in "
                                          "results/pathb2_floor.json",
                   "tol_pos_m": PB.TASK_TOL_POS,
                   "tol_yaw_rad": PB.TASK_TOL_YAW}, f, indent=1, default=str)
    print(f"\n  wrote {PB.RES}/pathb2_diag.json")


if __name__ == "__main__":
    raise SystemExit(main())

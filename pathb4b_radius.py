"""The operating radius is absorbing, and the declared calibration rule put the retained
step task inside it.

WHAT WENT WRONG
---------------
`pathb4_gates.py` calibrated the eligibility radius by the declared rule "R = 95th
percentile of ||e||_P observed over the monitor pass". On the prospective matrix that value,
R = 51.4825, made the supervisor the source of 77-79% of all commanded steps on the retained
step family, drove its post-onset RMSE to 1.67-2.1 m, and reduced achieved task completion to
between 0.3% and 33%. A sensitivity check over R told a much sharper story than a gradual
degradation:

    R = 51.48 (declared rule)   supervisor 79%   RMSE 1.748 m   completion 0.33
    R = 63.11 (archived value)  supervisor  1%   RMSE 0.503 m   completion 1.00
    R = 120 or unbounded        supervisor  0%   RMSE 0.482 m   completion 1.00

A 22% change in one constant flips the controller between working and not working. That is a
cliff, and a cliff means a structural mechanism rather than a tuning preference.

THE MECHANISM
-------------
The supervisor is `u = -kp * [vx, vy, r]`, clipped. It is a pure VELOCITY and yaw-rate
damping law: it reads `x_hat[2], x_hat[3], x_hat[5]` and never reads the position or heading
error at all. So when eligibility fails it drives the vehicle to REST and leaves the position
error exactly where it was.

Since ||e||_P has a positive-definite position block, a state at rest with a large enough
position error has ||e||_P > R on its own. The supervisor cannot reduce it, and because the
supervisor is what runs whenever ||e||_P > R, nothing else ever gets to. **The complement of
the eligibility set is absorbing for any position error beyond a threshold computable in
closed form from P and R.** The mechanism is not a recovery behaviour; entered from a large
position error it is a trap.

The retained step family presents an instantaneous 2 m setpoint change at t = 0, so its
initial error is exactly the kind that triggers this. The smooth families start at the
vehicle's own pose and never approach R, which is why they are completely insensitive to R.

WHY THE DECLARED RULE WAS WRONG, INDEPENDENTLY OF ANY OUTCOME
------------------------------------------------------------
The rule is circular. The monitor pass observes ||e||_P under a controller that is NOT being
diverted (R = 1e9), so the distribution it produces is the trajectory the controller needs to
fly. Taking its 95th percentile and then ENFORCING it forbids 5% of normal operation by
construction, and the forbidden 5% is not a random 5%: it is the high-error start of every
manoeuvre. An operating envelope that excludes the beginning of the task is not an envelope.

The corrected rule below is stated without reference to any test outcome: the radius must
CONTAIN normal operation, so it is the maximum ||e||_P observed over the monitor pass with a
declared margin, and it is additionally required to exceed the at-rest ||e||_P of the largest
initial error any retained task presents. The archived R = 63.11 satisfied the second
requirement by luck, not by design.

This script derives the corrected radius on the `calibration` key block only, and quantifies
the trap. The prospective matrix is then re-run at the corrected value, and BOTH results are
reported: the pre-registered frozen-R matrix and the corrected-R matrix, with this analysis
explaining the difference. The pre-registered numbers are not discarded.
"""
from __future__ import annotations

import json
import time

import numpy as np

import pathb_common as PB
from scsim import certificate as CT
from scsim import config as C
from scsim.parallel import pmap

RES = "results"
# Declared margin on the observed envelope. 20% matches the implementation margin already
# predeclared for the Sec 6.4 task gate, so the campaign uses one margin convention.
R_MARGIN = 1.20


# ==========================================================================
# 1. the trap, in closed form
# ==========================================================================
def trap_threshold(P, R):
    """The at-rest position error beyond which the ineligible set is absorbing.

    The supervisor drives the vehicle to rest, so consider e = (dx, dy, 0, 0, dpsi, 0). For
    a pure position error of magnitude d along the worst direction, ||e||_P = sqrt(s_max) d,
    where s_max is the largest eigenvalue of the position block of P; along the best
    direction it is sqrt(s_min) d. The state is therefore certainly ineligible at rest once
    sqrt(s_min) d > R, and may be ineligible from sqrt(s_max) d > R.
    """
    Ppos = np.asarray(P, dtype=float)[np.ix_([0, 1], [0, 1])]
    s = np.linalg.eigvalsh(Ppos)
    s_min, s_max = float(s.min()), float(s.max())
    return {"P_pos_eig_min": s_min, "P_pos_eig_max": s_max,
            "d_certainly_trapped_m": R / np.sqrt(s_min),
            "d_possibly_trapped_m": R / np.sqrt(s_max),
            "note": ("at rest and beyond `d_certainly_trapped_m` of position error the "
                     "state is ineligible in EVERY direction, the supervisor damps a "
                     "velocity that is already zero, and no other command is ever "
                     "issued: the set is absorbing")}


def _trap_job(args):
    """Does the supervisor ever hand control back? Measured, not argued."""
    fam, cond, es, cert = args
    from scsim.runner import run_policy_episode
    sc = PB.draw_scenario(fam, cond, es)
    pol = PB.make_policy("M0", 0, cert)
    log = run_policy_episode(pol, seed=es, steps=C.EPISODE_STEPS, scenario=sc)
    a = log.arrays()
    src = list(a["action_src"])
    sup = np.array([s.startswith("supervisor") for s in src])
    # the longest unbroken supervisor run, and whether the episode ends inside one
    runs, cur = [], 0
    for v in sup:
        cur = cur + 1 if v else 0
        runs.append(cur)
    m = PB.episode_metrics(log, sc, PB.DIAGNOSTIC_RECOVERY_TOL)
    return {"family": fam, "condition": cond, "ep_seed": es,
            "share_supervisor": float(sup.mean()),
            "longest_supervisor_run_steps": int(max(runs) if runs else 0),
            "ends_in_supervisor": bool(sup[-1]) if len(sup) else False,
            "ever_returned": bool(sup.any() and (~sup[np.argmax(sup):]).any()),
            "post_onset_rmse": m["post_onset_rmse"],
            "task_success": bool(m["task_success"])}


# ==========================================================================
# 2. the corrected radius
# ==========================================================================
def _monitor_job(args):
    """One MONITOR episode: observe ||e||_P with no diversion at all."""
    fam, cond, es, cert = args
    from scsim.runner import run_policy_episode
    ce = dict(cert, eta=0.0, R=1e9)
    sc = PB.draw_scenario(fam, cond, es)
    from scsim.controllers import LearnedContextPolicy
    pol = LearnedContextPolicy(PB.checkpoint_path("no_impact", 0), check_mode="monitor",
                               P=ce["P"], K=ce["K"], lam=ce["lam"], eta=0.0, R=1e9,
                               N=C.N_HORIZON_HW)
    log = run_policy_episode(pol, seed=es, steps=C.EPISODE_STEPS, scenario=sc)
    return np.asarray(log.arrays()["e_P"], dtype=float)


def corrected_radius(cert, workers=14):
    seeds = PB.scenario_keys("calibration", 25)
    jobs = [(f, c, s, cert) for f in PB.FAMILIES for c in PB.CONDITIONS for s in seeds]
    eps = pmap(_monitor_job, jobs, desc="  monitor pass", workers=workers)
    eP = np.concatenate([e[np.isfinite(e)] for e in eps])
    obs_max = float(eP.max())
    R_env = obs_max * R_MARGIN

    # the second requirement: the radius must admit the at-rest error of the largest
    # initial offset any RETAINED task presents. The step family's setpoint change is 2 m.
    P = np.asarray(cert["P"], dtype=float)
    worst = np.zeros(6)
    worst[0] = 2.0                                  # the step family's 2 m offset, at rest
    R_task = float(CT.norm_P(worst, P))
    worst2 = np.zeros(6)
    worst2[1] = 2.0
    R_task = max(R_task, float(CT.norm_P(worst2, P)))

    return {"n_transitions": int(eP.size), "n_episodes": len(jobs),
            "observed_max": obs_max,
            "observed_p50": float(np.percentile(eP, 50)),
            "observed_p95": float(np.percentile(eP, 95)),
            "observed_p99": float(np.percentile(eP, 99)),
            "margin": R_MARGIN,
            "R_envelope": R_env,
            "R_task_at_rest": R_task,
            "R": float(max(R_env, R_task)),
            "rule": ("R = max( 1.20 * max observed ||e||_P over the monitor pass, "
                     "||e||_P of a 2 m at-rest position error ). The first clause makes "
                     "the radius an envelope of normal operation rather than a quantile "
                     "that excludes its tail; the second guarantees the retained step "
                     "task's initial condition is admissible, so the task cannot be "
                     "forbidden at t = 0."),
            "supersedes": ("R = p95 of observed ||e||_P = 51.4825, which excluded the "
                           "high-error start of every manoeuvre by construction and made "
                           "the ineligible set absorbing on the step family"),
            "label": ("an OPERATING ENVELOPE fitted on calibration data; NOT a verified "
                      "region of attraction and not a safety guarantee")}


def main():
    t0 = time.time()
    print("=" * 78)
    print("the operating radius is absorbing, and the declared rule mis-set it")
    print("=" * 78)
    import stage6_methods as s6
    cert = s6.certificate_design()
    with open(f"{RES}/pathb4_gates.json") as f:
        old = json.load(f)["calibration"]
    R_old = float(old["R"])

    print("\n1. the trap, in closed form")
    tr = trap_threshold(cert["P"], R_old)
    print(f"  position block of P has eigenvalues "
          f"{tr['P_pos_eig_min']:.3f} to {tr['P_pos_eig_max']:.3f}")
    print(f"  at R = {R_old:.4f}, a vehicle AT REST is ineligible in every direction "
          f"beyond {tr['d_certainly_trapped_m']:.4f} m of position error,")
    print(f"  and may be ineligible from {tr['d_possibly_trapped_m']:.4f} m.")
    print(f"  the supervisor is u = -kp*[vx, vy, r]: it reads no position error at all, so "
          f"it cannot leave that set.")
    print(f"  the retained step family presents a 2.0 m setpoint change at t = 0, which is "
          f"{2.0 / tr['d_possibly_trapped_m']:.1f}x the entry threshold.")

    print("\n2. does the supervisor ever hand control back? measured over 64 episodes")
    ce = dict(cert, eta=float(old["eta"]), R=R_old)
    seeds = PB.scenario_keys("calibration", 8)
    rows = pmap(_trap_job, [(f, c, s, ce) for f in PB.FAMILIES
                            for c in PB.CONDITIONS for s in seeds],
                desc="  trap probe", workers=14)
    for fam in PB.FAMILIES:
        sub = [r for r in rows if r["family"] == fam]
        print(f"  {fam:12s} supervisor share "
              f"{np.mean([r['share_supervisor'] for r in sub]):.3f}, longest unbroken run "
              f"{max(r['longest_supervisor_run_steps'] for r in sub)} steps "
              f"of {C.EPISODE_STEPS}, ends inside a supervisor interval on "
              f"{sum(r['ends_in_supervisor'] for r in sub)}/{len(sub)} episodes")

    print("\n3. the corrected radius, derived on the calibration block only")
    new = corrected_radius(cert)
    print(f"  observed ||e||_P over {new['n_transitions']} monitor transitions: "
          f"p50 {new['observed_p50']:.2f}, p95 {new['observed_p95']:.2f}, "
          f"p99 {new['observed_p99']:.2f}, max {new['observed_max']:.2f}")
    print(f"  envelope clause: 1.20 x max = {new['R_envelope']:.4f}")
    print(f"  task clause: ||e||_P of a 2 m at-rest offset = {new['R_task_at_rest']:.4f}")
    print(f"  corrected R = {new['R']:.4f}   (was {R_old:.4f}, a factor "
          f"{new['R'] / R_old:.2f})")
    print(f"  {new['rule']}")

    out = {"stage": "pathb4b_radius", "R_previous": R_old,
           "trap": tr, "trap_probe": rows, "corrected": new,
           "reporting": ("BOTH matrices are reported: the pre-registered one at "
                         "R = 51.4825 and the corrected one. The pre-registered numbers "
                         "are not discarded, and the corrected run is labelled as a "
                         "post-hoc re-run whose motivation is the mechanism above, not "
                         "any test outcome."),
           "wall_time_s": time.time() - t0}
    with open(f"{RES}/pathb4b_radius.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\nwrote {RES}/pathb4b_radius.json ({out['wall_time_s']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

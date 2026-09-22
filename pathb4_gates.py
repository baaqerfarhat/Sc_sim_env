"""Path B calibration and the two Priority-2 development gates (plan Sec 7).

Three parts, in this order:

  A  CALIBRATION.  The operational constants (eligibility radius R, allowance eta) are
     fitted on the `calibration` key block, across BOTH families and all four conditions,
     with the policy in MONITOR mode so the thresholds are fitted to slacks the
     thresholds themselves did not influence. Then frozen. The ~0.662 m diagnostic
     recovery tolerance is carried over from the archive unchanged, because Sec 9.6 keeps
     it as a labelled historical diagnostic rather than a Path B endpoint.

  B  INSTRUMENTATION SMOKE GATE (Sec 7 Priority 2).  2 families x 4 conditions x 2
     development scenarios x 3 controllers = 48 episodes. Verifies logging completeness,
     N+1 = 13 MPC references at N = 12, totality of the action taxonomy, fault-slot
     execution, fallback storage, non-mutating trials and timing. Also verifies
     EMPIRICALLY that M0 and M5 are checkpoint-independent, which is what Sec 4.1
     requires before they may be run once per scenario instead of once per seed.

  C  M3/M4 SEMANTIC STOP GATE (Sec 7 Priority 2).  The same 16 scenario units, all five
     M3 checkpoints, paired M3/M4 deployments: 16 x 5 x 2 = 160 episodes. If every pair
     is bitwise identical and M3's enabled repeated-check rejection counter is zero, M4
     is omitted from the prospective matrix and the repeated-check PERFORMANCE claim is
     removed, keeping only the semantic/replay finding.

None of these episodes enters any effect estimate.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

import pathb_common as PB
from scsim import config as C
from scsim.parallel import pmap

RES = "results"
os.makedirs(RES, exist_ok=True)

N_CALIB_PER_CELL = 25
DIAGNOSTIC_TOL = 0.662           # carried over from the archive, labelled, not refitted


# ==========================================================================
# A. calibration
# ==========================================================================
def _monitor_job(args):
    """One monitor-mode rollout: the checks are evaluated and logged but never acted on."""
    family, cond, ep_seed, cert = args
    from scsim.controllers import LearnedContextPolicy
    from scsim.runner import run_policy_episode
    sc = PB.draw_scenario(family, cond, ep_seed)
    pol = LearnedContextPolicy(PB.checkpoint_path("no_impact", 0),
                               check_mode="monitor", P=cert["P"], K=cert["K"],
                               lam=cert["lam"], eta=0.0, R=1e9,
                               N=C.N_HORIZON_HW)
    log = run_policy_episode(pol, seed=ep_seed, steps=C.EPISODE_STEPS, scenario=sc)
    a = log.arrays()
    return {"e_P": [v for v in a["e_P"] if np.isfinite(v)],
            "slack_cmd": [v for v in a["slack_cmd"] if np.isfinite(v)],
            "family": family, "condition": cond}


def _eta_job(args):
    family, cond, ep_seed, cert = args
    from scsim.runner import run_policy_episode
    sc = PB.draw_scenario(family, cond, ep_seed)
    log = run_policy_episode(PB.make_policy("M2", 0, cert), seed=ep_seed,
                             steps=C.EPISODE_STEPS, scenario=sc)
    m = PB.episode_metrics(log, sc, DIAGNOSTIC_TOL)
    return {"post_onset_rmse": m["post_onset_rmse"],
            "share_supervisor": m.get("share_supervisor", np.nan),
            "share_mpc": m.get("share_mpc", np.nan)}


def calibrate(cert, workers=14):
    print("\n" + "=" * 78)
    print("A  calibration on the `calibration` key block (MONITOR mode, then frozen)")
    print("=" * 78)
    seeds = PB.scenario_keys("calibration", N_CALIB_PER_CELL)
    jobs = [(f, c, s, cert) for f in PB.FAMILIES for c in PB.CONDITIONS
            for s in seeds]
    got = pmap(_monitor_job, jobs, desc="  monitor pass", workers=workers)
    eP = [v for g in got for v in g["e_P"]]
    slack = [v for g in got for v in g["slack_cmd"]]
    R = float(np.percentile(eP, 95)) if eP else 1e9
    deficits = [-v for v in slack if v < 0]
    frac_viol = float(np.mean([v < 0 for v in slack])) if slack else np.nan
    eta_conformal = float(np.percentile(deficits, 97.5)) if deficits else 0.0
    print(f"  {len(jobs)} monitor episodes over {len(PB.FAMILIES)} families x "
          f"{len(PB.CONDITIONS)} conditions x {N_CALIB_PER_CELL} keys")
    print(f"  eligibility radius R = p95 of ||e||_P over {len(eP)} transitions "
          f"= {R:.4f}")
    print(f"  the decrease inequality is violated by the candidate in "
          f"{frac_viol * 100:.1f}% of monitored steps")
    print(f"  conformal eta at delta=0.025 would be {eta_conformal:.4f}")

    # eta by the DECLARED rule: minimise calibration-split post-onset RMSE on a fixed
    # grid. This is controller tuning on data disjoint from the test, and it is labelled
    # as such; it is NOT the manuscript's conformal procedure.
    # The ladder is extended well past the archived eta = 2 on purpose. A selection rule
    # that minimises RMSE on a grid whose largest value wins has not selected anything: it
    # has hit the boundary, and the honest reading is "as permissive as we happened to
    # test". Running out to 64 and to the no-check limit makes the curve's shape, and hence
    # whether the first-action screen helps at all, an observable rather than an assumption.
    # Selecting a LARGE eta is adverse to the manuscript's own claim, which is why the grid
    # must be wide enough to let that answer appear.
    grid = sorted({0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 64.0, float("inf"),
                   round(eta_conformal, 4)})
    sub = seeds[:8]
    curve = []
    for e in grid:
        ce = dict(cert, eta=e, R=R)
        jj = [(f, c, s, ce) for f in PB.FAMILIES for c in PB.CONDITIONS for s in sub]
        rows = pmap(_eta_job, jj, desc=f"  eta={e:g}", workers=workers)
        curve.append({"eta": e,
                      "post_onset_rmse": float(np.mean([r["post_onset_rmse"]
                                                        for r in rows])),
                      "share_mpc": float(np.nanmean([r["share_mpc"] for r in rows])),
                      "share_supervisor": float(np.nanmean([r["share_supervisor"]
                                                            for r in rows]))})
    # eta = inf is the NO-CHECK limit and is carried on the curve as a reference point, not
    # as a selectable operating point: selecting it would delete the mechanism the paper is
    # about, and the finite grid is what the declared rule ranges over.
    finite = [c for c in curve if np.isfinite(c["eta"])]
    best = min(finite, key=lambda c: c["post_onset_rmse"])
    interior = bool(0 < finite.index(best) < len(finite) - 1)
    print("  eta selection (declared rule: minimise calibration post-onset RMSE):")
    for c in curve:
        mark = "  <- selected" if c["eta"] == best["eta"] else ""
        if not np.isfinite(c["eta"]):
            mark = "  (no-check limit, reference only)"
        print(f"    eta={c['eta']:7.4g}  RMSE {c['post_onset_rmse']:.4f}  "
              f"MPC share {c['share_mpc']:.3f}  supervisor "
              f"{c['share_supervisor']:.3f}{mark}")
    print(f"  the minimum is {'INTERIOR to' if interior else 'at the BOUNDARY of'} the "
          f"finite ladder"
          + ("" if interior else ", so the curve is reported as monotone over the tested "
                                "range and no claim is made that this eta is optimal"))
    no_check = [c for c in curve if not np.isfinite(c["eta"])]
    if no_check:
        gap = no_check[0]["post_onset_rmse"] - best["post_onset_rmse"]
        print(f"  removing the screen entirely changes calibration RMSE by {gap:+.4f} m "
              f"relative to the selected eta")
    return {"R": R, "eta": float(best["eta"]), "eta_conformal": eta_conformal,
            "eta_curve": curve, "eta_minimum_interior": interior,
            "eta_no_check_rmse": (float(no_check[0]["post_onset_rmse"]) if no_check
                                  else None),
            "frac_decrease_violated": frac_viol,
            "n_transitions": len(eP), "n_episodes": len(jobs),
            "diagnostic_tol": DIAGNOSTIC_TOL,
            "diagnostic_tol_label": PB.DIAGNOSTIC_RECOVERY_LABEL,
            "key_block": "calibration",
            "labels": {"R": "operating envelope from observed ||e||_P; NOT a verified "
                            "region of attraction",
                       "eta": "CONTROLLER TUNING by a declared rule on calibration "
                              "data disjoint from the test; NOT the manuscript's "
                              "conformal procedure",
                       "diagnostic_tol": "carried over from the archive unchanged and "
                                         "labelled historical; never merged with task "
                                         "success"}}


# ==========================================================================
# B. instrumentation smoke gate
# ==========================================================================
SMOKE_METHODS = ("M0", "M2", "M5")


def _smoke_job(args):
    mid, seed, family, cond, ep_seed, cert = args
    from scsim.runner import run_policy_episode
    sc = PB.draw_scenario(family, cond, ep_seed)
    log = run_policy_episode(PB.make_policy(mid, seed, cert), seed=ep_seed,
                             steps=C.EPISODE_STEPS, scenario=sc)
    a = log.arrays()
    m = PB.episode_metrics(log, sc, DIAGNOSTIC_TOL)
    # a compact fingerprint of the transmitted packets, for the identity comparisons
    fp = np.asarray(a["pulse_command_s"], dtype=float)
    return {"method": mid, "model_seed": seed, "family": family, "condition": cond,
            "ep_seed": ep_seed,
            "packet_hash": float(np.abs(fp).sum()),
            "packets": fp.tolist(),
            "action_src": list(a["action_src"]),
            "x_true_sum": float(np.abs(a["x_true"]).sum()),
            "src_sum": m["action_src_sum"],
            "n_steps": m["n_steps"],
            "decision_ms_p95": m["decision_ms_p95"],
            "deadline_miss_rate": m["deadline_miss_rate"],
            "horizon_N": log.meta.get("mpc_horizon_N"),
            "H": log.meta.get("train_rollout_depth_H"),
            "n_fault_skips": m["n_fault_skips"],
            "checkpoint_sha256": log.meta.get("checkpoint_sha256"),
            "log_fields": sorted(k for k in a if k != "meta"),
            "post_onset_rmse": m["post_onset_rmse"]}


def smoke_gate(cert, workers=14):
    print("\n" + "=" * 78)
    print("B  instrumentation smoke gate (Sec 7 Priority 2): 48 development episodes")
    print("=" * 78)
    seeds2 = PB.scenario_keys("smoke", 2)
    jobs = [(mid, 0, f, c, s, cert) for mid in SMOKE_METHODS
            for f in PB.FAMILIES for c in PB.CONDITIONS for s in seeds2]
    rows = pmap(_smoke_job, jobs, desc="  smoke", workers=workers)
    print(f"  {len(rows)} episodes = {len(SMOKE_METHODS)} controllers x "
          f"{len(PB.FAMILIES)} families x {len(PB.CONDITIONS)} conditions x 2 scenarios")

    checks = []

    def add(label, passed, detail):
        checks.append({"check": label, "pass": bool(passed), "detail": detail})
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        for ln in detail.split("\n"):
            print(f"         {ln}")

    need = {"x_true", "x_hat", "ref", "ref_next", "ref_score", "u_prop", "u_nom_tx",
            "pulse_command_s", "pulse_actual_s", "action_src", "repair_seed_origin",
            "reject_reason", "ineligible_reason", "projection_applied",
            "compensation_applied", "gate", "accepted", "slack_cmd", "slack_fb",
            "e_P", "decision_ms", "deadline_miss", "innov", "pose_valid", "z_ctx"}
    have = set(rows[0]["log_fields"])
    add("7.2a every declared log channel is present on every episode",
        need <= have and all(need <= set(r["log_fields"]) for r in rows),
        f"{len(need)} required channels present; missing {sorted(need - have) or 'none'}")

    add("7.2b the MPC preview is N+1 = 13 at the frozen horizon N = 12, and H is "
        "recorded separately",
        all(r["horizon_N"] == C.N_HORIZON_HW for r in rows)
        and all(r["H"] == C.MULTISTEP_H for r in rows),
        f"every episode records mpc_horizon_N = {C.N_HORIZON_HW} (preview "
        f"{C.N_HORIZON_HW + 1} indices) and train_rollout_depth_H = {C.MULTISTEP_H}")

    bad_sum = [r for r in rows if abs(r["src_sum"] - 1.0) > 1e-9]
    labels = sorted({s for r in rows for s in r["action_src"]})
    add("7.2c the action taxonomy is total: exactly one source per step, shares sum "
        "to one",
        not bad_sum and set(labels) <= set(PB.ACTION_SOURCES),
        f"{len(rows)} episodes, all shares sum to 1.0 within 1e-9.\n"
        f"labels observed: {labels}\n"
        f"all within the declared 12-label taxonomy: "
        f"{set(labels) <= set(PB.ACTION_SOURCES)}")

    # fault-slot execution: one skip per faulted step at most, and none when healthy
    healthy = [r for r in rows if r["condition"] == "healthy"]
    faulted = [r for r in rows if r["condition"] in ("actuator", "combined")]
    add("7.2d fault-slot execution: no skips when healthy, at most one per step "
        "when faulted",
        all(r["n_fault_skips"] == 0 for r in healthy)
        and all(0 < r["n_fault_skips"] <= r["n_steps"] for r in faulted),
        f"healthy: {sorted({r['n_fault_skips'] for r in healthy})} skips; "
        f"faulted: {min(r['n_fault_skips'] for r in faulted)}-"
        f"{max(r['n_fault_skips'] for r in faulted)} skips over "
        f"{rows[0]['n_steps']} steps")

    p95 = float(np.nanmax([r["decision_ms_p95"] for r in rows]))
    miss = float(np.nanmax([r["deadline_miss_rate"] for r in rows]))
    add("7.2e complete decision latency is measured and inside the period",
        np.isfinite(p95) and p95 < C.TS * 1e3,
        f"worst per-episode p95 decision latency {p95:.1f} ms against the "
        f"{C.TS * 1e3:.0f} ms period;\nworst per-episode deadline-miss rate "
        f"{miss:.4f}. SIMULATION-WORKSTATION timing, not the flight computer.")

    # Sec 4.1: M0 and M5 must be verified checkpoint-independent before being run once
    # per scenario rather than once per seed
    indep = {}
    for mid in ("M0", "M5"):
        jj = [(mid, s, "smooth_dock", "combined", seeds2[0], cert) for s in range(5)]
        got = pmap(_smoke_job, jj, desc=f"  {mid} seed independence", workers=5)
        packets = [np.asarray(g["packets"]) for g in got]
        same = all(np.array_equal(packets[0], p) for p in packets[1:])
        shas = sorted({g["checkpoint_sha256"] for g in got})
        indep[mid] = {"identical_packets": bool(same), "n_checkpoints_probed": len(jj),
                      "distinct_checkpoint_hashes": len(shas),
                      "rmse": sorted({round(g["post_onset_rmse"], 12) for g in got})}
        add(f"4.1 {mid} is checkpoint-INDEPENDENT, verified empirically",
            same,
            f"5 different checkpoints loaded ({len(shas)} distinct file hashes) produce "
            f"bitwise\nidentical commanded packets and a single post-onset RMSE value "
            f"{indep[mid]['rmse']}.\nIt may therefore be run once per scenario. Sec 4.1 "
            f"forbids copying one trajectory\nfive times and reporting the copies as "
            f"seed replicates, and Sec 11.4 forbids\ncounting them as rollouts.")

    return {"n_episodes": len(rows), "checks": checks,
            "seed_independence": indep,
            "worst_decision_ms_p95": p95, "worst_deadline_miss_rate": miss,
            "labels_observed": labels,
            "gate_pass": all(c["pass"] for c in checks)}


# ==========================================================================
# C. M3/M4 semantic stop gate
# ==========================================================================
def _pair_job(args):
    seed, family, cond, ep_seed, cert = args
    from scsim.runner import run_policy_episode
    out = {}
    for mid in ("M3", "M4"):
        sc = PB.draw_scenario(family, cond, ep_seed)
        log = run_policy_episode(PB.make_policy(mid, seed, cert), seed=ep_seed,
                                 steps=C.EPISODE_STEPS, scenario=sc)
        a = log.arrays()
        st = log.meta["policy_stats"]
        out[mid] = {"packets": np.asarray(a["pulse_command_s"], dtype=float),
                    "src": list(a["action_src"]),
                    "x": np.asarray(a["x_true"], dtype=float),
                    "n_reject": int(st.get("n_reject", 0)),
                    "n_would_reject": int(st.get("n_would_reject", 0))}
    a3, a4 = out["M3"], out["M4"]
    return {"seed": seed, "family": family, "condition": cond, "ep_seed": ep_seed,
            "packets_identical": bool(np.array_equal(a3["packets"], a4["packets"])),
            "sources_identical": bool(a3["src"] == a4["src"]),
            "trajectories_identical": bool(np.array_equal(a3["x"], a4["x"])),
            "max_state_diff": float(np.abs(a3["x"] - a4["x"]).max()),
            "m3_n_reject": a3["n_reject"], "m3_n_would_reject": a3["n_would_reject"],
            "m4_n_would_reject": a4["n_would_reject"]}


def stop_gate(cert, workers=14):
    print("\n" + "=" * 78)
    print("C  M3/M4 semantic stop gate (Sec 7 Priority 2): 160 development episodes")
    print("=" * 78)
    seeds2 = PB.scenario_keys("stopgate", 2)
    units = [(f, c, s) for f in PB.FAMILIES for c in PB.CONDITIONS for s in seeds2]
    jobs = [(ms, f, c, s, cert) for ms in PB.SEEDS for (f, c, s) in units]
    rows = pmap(_pair_job, jobs, desc="  M3/M4 pairs", workers=workers)
    n_ep = 2 * len(rows)
    print(f"  {len(units)} scenario units x {len(PB.SEEDS)} M3 checkpoints x 2 "
          f"deployments = {n_ep} episodes")

    all_pkt = all(r["packets_identical"] for r in rows)
    all_src = all(r["sources_identical"] for r in rows)
    all_traj = all(r["trajectories_identical"] for r in rows)
    m3_rej = sum(r["m3_n_reject"] for r in rows)
    m3_would = sum(r["m3_n_would_reject"] for r in rows)
    identical = all_pkt and all_src and all_traj
    omit = bool(identical and m3_rej == 0)
    print(f"  selected packets identical on every pair: {all_pkt}")
    print(f"  action sources identical on every pair:   {all_src}")
    print(f"  trajectories identical on every pair:     {all_traj}  "
          f"(max |state difference| "
          f"{max(r['max_state_diff'] for r in rows):.3e})")
    print(f"  M3 enabled repeated-check rejections:     {m3_rej}")
    print(f"  M3 would-reject count (test evaluated, not acted on): {m3_would}")
    print()
    if omit:
        print("  ==> STOP RULE TRIGGERED. M4 is OMITTED from the prospective matrix and")
        print("      the repeated-check PERFORMANCE claim is removed. Only the")
        print("      semantic/replay finding is reported: over 160 development")
        print("      episodes the repeated post-allocation check never fired and")
        print("      disabling it changed nothing, bitwise.")
    else:
        print("  ==> pairs differ, so the full 2,400-rollout M4 test matrix is RETAINED.")
    return {"n_episodes": n_ep, "n_units": len(units), "n_seeds": len(PB.SEEDS),
            "packets_identical": all_pkt, "sources_identical": all_src,
            "trajectories_identical": all_traj,
            "max_state_diff": float(max(r["max_state_diff"] for r in rows)),
            "m3_repeated_check_rejections": m3_rej,
            "m3_would_reject": m3_would,
            "omit_M4_from_test": omit,
            "consequence": ("M4 omitted; the repeated-check performance claim is "
                            "removed and only the semantic/replay result is reported"
                            if omit else
                            "M4 retained in the prospective matrix"),
            "rows": rows}


# ==========================================================================
def main():
    t0 = time.time()
    print("=" * 78)
    print("PATH B  calibration and the Priority-2 development gates")
    print("=" * 78)
    import stage6_methods as s6
    cert = s6.certificate_design()
    print(f"frozen supervision design: lambda={cert['lam']:.4f} "
          f"|K|max={np.abs(cert['K']).max():.2f}")

    cal = calibrate(cert)
    cert.update(eta=cal["eta"], R=cal["R"])
    print(f"\nFROZEN before any gate or test episode: R = {cal['R']:.4f}, "
          f"eta = {cal['eta']:g}, diagnostic tolerance = {DIAGNOSTIC_TOL} m")

    smoke = smoke_gate(cert)
    stop = stop_gate(cert)

    out = {"stage": "pathb4_gates", "calibration": cal,
           "supervision_design": {"lam": cert["lam"], "lam0": cert["lam0"],
                                  "eta": cert["eta"], "R": cert["R"],
                                  "K_absmax": float(np.abs(cert["K"]).max())},
           "smoke_gate": smoke, "stop_gate": stop,
           "development_episodes_spent": (cal["n_episodes"]
                                          + len(cal["eta_curve"]) * 64
                                          + smoke["n_episodes"] + 10
                                          + stop["n_episodes"]),
           "manifest_hash": C.manifest_hash(),
           "wall_time_s": time.time() - t0}
    passed = smoke["gate_pass"]
    print("\n" + "=" * 78)
    print(f"SMOKE GATE: {'PASS' if passed else 'FAIL'}   "
          f"M4 in the prospective matrix: {not stop['omit_M4_from_test']}")
    print(f"development episodes spent: {out['development_episodes_spent']}")
    print("=" * 78)
    with open(f"{RES}/pathb4_gates.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"wrote {RES}/pathb4_gates.json ({out['wall_time_s'] / 60:.1f} min)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

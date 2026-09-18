"""Stage 6: the six method variants and the matched comparison table.

Protocol Sec 9.1. Rows are condition x method; the paired full-minus-no_impact effect
is the headline number, with block bootstrap over parent episodes and seed-level
results shown alongside the pooled interval.

METHODS (Sec 13 item 6, plus the hardware comparator)
  zero_context      z = 0, no residual. What the hardware actually ran. A DIAGNOSTIC.
  constant_context  residual retrained with ONE learned constant context. This is the
                    variant that answers "does inferring a CHANGING context help?".
  adaptive_mpc      no learned context; bounded regularised RLS on the increments.
  no_impact         full architecture, lambda_I = 0. The behavioural-loss ablation.
  full              the proposed method.
  full_no_check     full, with ONLY the post-allocation acceptance check bypassed.

MATCHING.  Every variant sees the same condition draws, the same episode seeds (hence
the same perception-noise realisation and the same fault phase), the same references,
limits, estimator and timing. Trajectories diverge only through the control.

CALIBRATION IS SEPARATE FROM TEST.  eta, the eligibility radius R and the recovery
tolerance are all fixed on split 0 with the acceptance check disabled, then FROZEN.
Test episodes come from splits 1-4. Choosing a threshold on the test episodes would
invalidate every interval reported here.

HONESTY NOTE.  Stage 7 finds the certificate EMPTY at hardware authority, so the
(P, K, lambda, eta, R) used here is an OPERATIONAL supervision design, not a
certified region. Activity and acceptance numbers below therefore describe a
mechanism being exercised; they are not evidence of a guarantee. Per protocol Sec 9.2,
gate inactivity is not displayed as proof of safety.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from scsim import certificate as CT
from scsim import config as C
from scsim import scenarios as S
from scsim.controllers import (AdaptiveMPCPolicy, ConstantContextPolicy,
                               FallbackOnlyPolicy, LearnedContextPolicy,
                               NominalRecoveryPolicy, ZeroContextPolicy)
from scsim.parallel import pmap
from scsim.runner import run_policy_episode

DATA, RES = "data", "results"
os.makedirs(RES, exist_ok=True)

CONDITIONS = S.MAIN_CONDITIONS      # canonical, so the names cannot drift
MODEL_SEEDS = (0, 1, 2)
N_TEST_PER_COND = 60          # protocol Sec 6: 50-100 matched episodes per condition
N_CALIB_PER_COND = 25
STEPS = C.EPISODE_STEPS
HOLD_STEPS = 20               # 2 s inside tolerance counts as recovered

# Sec 7.1 method matrix. The ID column is what the paper tables cite; the internal
# name is what the code and checkpoints use.
#   M0  nominal_recovery   no learned residual, SAME recovery structure
#   M1  constant_context   trained constant context, prediction losses only
#   M2  no_impact          changing context, prediction losses only
#   M3  full               changing context + behavioural supervision
#   M4  full_no_check      M3 checkpoint, post-allocation acceptance bypassed
#   M5  fallback_only      checked fallback feedback only, no MPC planning
#   M6  adaptive_mpc       adaptation baseline with a documented update law
#   --  zero_context       hardware-matched comparator, DIAGNOSTIC only
METHOD_IDS = {"nominal_recovery": "M0", "constant_context": "M1",
              "no_impact": "M2", "full": "M3", "full_no_check": "M4",
              "fallback_only": "M5", "adaptive_mpc": "M6",
              "zero_context": "HW"}

# methods that do not depend on a training seed
SEEDLESS = ("zero_context", "adaptive_mpc")
LEARNED = ("nominal_recovery", "constant_context", "no_impact", "full",
           "full_no_check", "fallback_only")
METHODS = SEEDLESS + LEARNED

# Sec 8.1: task success thresholds declared BEFORE the final test, and fixed across
# every method. These are provisional development values, not measured spacecraft
# requirements, and they are not guaranteed attainable under the modelled estimator
# and authority: if they are not met, that is reported as a failure with its cause.
# The earlier campaign instead derived its tolerance from the healthy zero-context
# terminal error (0.98 m), which is a baseline-relative threshold that moves whenever
# the baseline moves.
TASK_TOL_POS = 0.15          # m
TASK_TOL_YAW = np.deg2rad(5.0)
TASK_DWELL_STEPS = 20        # 2.0 s at 10 Hz
TASK_DEADLINE_STEPS = C.EPISODE_STEPS

# Protocol Sec 5 requires >=3 training seeds for the variants whose TRAINING differs,
# which is the full / no_impact pair (the intentional lambda_I difference). The other
# two differ from `full` in deployment, not in training: `full_no_check` reuses the
# `full` checkpoint with the check bypassed, and `constant_context` is a single extra
# representation. Those run on seed 0 only, which is where the compute is spent best.
# Sec 8.3: full_no_check must be run for EVERY seed that `full` uses, because the
# comparison is per-checkpoint. Broadcasting a single seed-0 no-check run against all
# three `full` seeds, as the earlier campaign did, is not a same-checkpoint ablation.
SEEDS_FOR = {"no_impact": MODEL_SEEDS, "full": MODEL_SEEDS,
             "full_no_check": MODEL_SEEDS,
             "constant_context": (0,), "nominal_recovery": (0,),
             "fallback_only": MODEL_SEEDS}


# --------------------------------------------------------------------------
def certificate_design():
    """The frozen (P, K) used by every recovery-equipped variant.

    Taken from the Stage 7 design grid at the hardware-matched step family, choosing
    the cell that minimises s_cert / R_max. Loaded from the Stage 7 artefact so the
    two stages cannot disagree.
    """
    import stage7_certificate as s7

    A_list, B_list, _ = s7.domain_vertices("step")
    # PARAM_SPAN is the tolerance at which Stage 7 finds the contraction condition
    # achievable; using +/-10% would make every design non-contracting and the
    # supervision inequality vacuous.
    span = 0.05
    _, _, boxes = s7.domain_vertices("step", mass_span=span, jzz_span=span)
    hw = dict(duty=0.40, fmax=C.FMAX_PER_THRUSTER, offset=C.FIT_OFFSET)
    best = None
    for lam0 in (0.90, 0.95, 0.97, 0.98, 0.99):
        for w in (1e2, 1e4):
            r = CT.solve_lmi(A_list, B_list, lam0, w_effort=w)
            if r is None:
                continue
            P, K = r
            ev = s7.evaluate_certificate(
                P, K, boxes, "step", achievable=np.array([0.96, 0.96, 0.384]),
                chain_factory=s7._chain_factory(hw))
            # ratio is +inf for every non-contracting design, so it cannot rank them.
            # Break that tie on lambda, which is what makes the supervision
            # inequality meaningful: lambda >= 1 permits the error to grow and the
            # acceptance check would then reject almost nothing.
            key = (ev["ratio"], ev["lam"])
            if best is None or key < best[0]:
                best = (key, P, K, lam0, w, ev)
    _, P, K, lam0, w, ev = best
    return {"P": P, "K": K, "lam": float(ev["lam"]), "lam0": lam0, "w_effort": w,
            "param_span": span,
            "eval": {k: v for k, v in ev.items() if k != "b_r_worst_pair"}}


def make_policy(method, model_seed, cert, N=C.N_HORIZON_HW):
    """Construct one policy. Recovery machinery is identical across the variants that
    have it; only the checkpoint and the check mode differ.

    `full_monitor` is a CALIBRATION-ONLY variant: it evaluates the acceptance check and
    records its slack but always transmits the candidate. It never appears in the
    comparison table.
    """
    if method == "zero_context":
        return ZeroContextPolicy(N=N)
    if method == "adaptive_mpc":
        return AdaptiveMPCPolicy(N=N)
    if method in ("nominal_recovery", "fallback_only"):
        cls = (NominalRecoveryPolicy if method == "nominal_recovery"
               else FallbackOnlyPolicy)
        # both reuse the `full` architecture/normalisation but differ in what they
        # consult: M0 zeroes the residual, M5 removes the optimisation
        return cls(f"{DATA}/model_full_s{model_seed}.pt", check_mode="enforce",
                   P=cert["P"], K=cert["K"], lam=cert["lam"], eta=cert["eta"],
                   R=cert["R"], N=N)
    # `constant_context` goes through the SAME policy class and the same recovery
    # machinery as `full`; only the checkpoint differs. A constant-context checkpoint
    # returns its single learned vector from `encode` regardless of the history, so
    # this is exactly the constant-context variant. Giving it a different policy class
    # would confound the representation with the supervision and make the
    # "does a CHANGING context help?" comparison unreadable.
    tag = {"no_impact": "no_impact", "full": "full", "full_no_check": "full",
           "full_monitor": "full", "constant_context": "const"}[method]
    mode = {"no_impact": "enforce", "full": "enforce", "full_no_check": "off",
            "full_monitor": "monitor", "constant_context": "enforce"}[method]
    return LearnedContextPolicy(
        f"{DATA}/model_{tag}_s{model_seed}.pt", check_mode=mode,
        P=cert["P"], K=cert["K"], lam=cert["lam"], eta=cert["eta"],
        R=cert["R"], N=N)


# --------------------------------------------------------------------------
def episode_metrics(log, sc, tol):
    """Per-trial metrics. Physical error is against the ORIGINAL scoring reference."""
    a = log.arrays()
    xt, rs = a["x_true"], a["ref_score"]
    e_pos = np.linalg.norm(xt[:, :2] - rs[:, :2], axis=1)
    e_yaw = np.abs(np.arctan2(np.sin(xt[:, 4] - rs[:, 4]),
                              np.cos(xt[:, 4] - rs[:, 4])))
    st = log.meta["policy_stats"]
    n = len(e_pos)
    # variants without the recovery machinery have no gate and no acceptance check;
    # reporting 0.0 for them would read as "the mechanism was inactive" rather than
    # "the mechanism does not exist", so those cells are NaN. BasePolicy pre-seeds the
    # stat keys, so presence of a key cannot be used to detect this.
    has_rec = bool(log.meta.get("has_recovery", False))
    checking = log.meta.get("check_mode") == "enforce"

    m = {
        "rmse_pos": float(np.sqrt(np.mean(e_pos ** 2))),
        "peak_pos": float(e_pos.max()),
        "rmse_yaw": float(np.sqrt(np.mean(e_yaw ** 2))),
        "peak_yaw": float(e_yaw.max()),
        "final_pos": float(np.mean(e_pos[-50:])),
        "accel_p95": float(np.percentile(a["accel"], 95)),
        "n_steps": n,
        "frac_fallback": st["n_fallback"] / max(st["n_steps"], 1),
        "frac_gate_on": (st["n_active"] / max(st["n_steps"], 1) if has_rec
                         else np.nan),
        # the rejected fraction only exists where the check is ENFORCED; for the
        # no-check ablation it is undefined, not zero
        "frac_reject": (st["n_reject"] / max(st["n_steps"], 1) if checking
                        else np.nan),
        "has_recovery": has_rec, "check_enforced": checking,
        "n_fault_skips": log.meta["n_fault_skips"],
        "solve_ms_p95": float(np.nanpercentile(a["solve_ms"], 95)),
    }

    # ---- action source: which controller actually produced the transmitted action ----
    src = list(a["action_src"]) if "action_src" in a else []
    if src:
        for label in ("candidate", "fallback_checked", "fallback_solver_fail",
                      "supervisor", "fallback_only", "unchecked_solver_fallback"):
            m[f"frac_src_{label}"] = float(sum(1 for s in src if s == label) / len(src))

    # ---- Sec 8.1/8.2 task success against DECLARED thresholds ----
    # Both position and yaw must hold inside tolerance for the full dwell before the
    # deadline. This is a fixed specification, identical for every method, and it is
    # evaluated on every episode including healthy ones.
    inside_task = (e_pos <= TASK_TOL_POS) & (e_yaw <= TASK_TOL_YAW)
    m["task_success"], m["completion_time"] = False, np.nan
    limit = min(n, TASK_DEADLINE_STEPS) - TASK_DWELL_STEPS + 1
    for t in range(max(limit, 0)):
        if inside_task[t:t + TASK_DWELL_STEPS].all():
            m["task_success"] = True
            m["completion_time"] = float((t + TASK_DWELL_STEPS) * C.TS)
            break
    # Sec 8.2: a transient return is not sustained tracking, so record whether the
    # trajectory was still inside tolerance at the end of the episode
    m["task_held_at_end"] = bool(inside_task[-TASK_DWELL_STEPS:].all())
    m["frac_time_in_tol"] = float(inside_task.mean())

    # ---- recovery, measured only when there is something to recover from ----
    onset = sc.onset_step if (sc.fault_active or sc.perception != "healthy") else None
    m["attempted"] = bool(onset is not None and onset + HOLD_STEPS < n)
    m["success"], m["recovery_time"] = False, np.nan
    if m["attempted"]:
        # Sec 8.2: separate MAINTENANCE (already inside tolerance at onset and staying
        # there) from REACQUISITION (thrown out and having to come back). Pooling them
        # lets easy episodes inflate a recovery rate.
        m["was_in_tol_at_onset"] = bool(inside_task[onset])
        m["mode"] = "maintenance" if inside_task[onset] else "reacquisition"
        inside = e_pos <= tol
        for t in range(onset, n - HOLD_STEPS + 1):
            if inside[t:t + HOLD_STEPS].all():
                m["success"] = True
                m["recovery_time"] = float((t - onset) * C.TS)
                break
        # post-onset window is FIXED relative to onset and identical across methods
        m["post_onset_rmse"] = float(np.sqrt(np.mean(e_pos[onset:] ** 2)))
        m["post_onset_peak"] = float(e_pos[onset:].max())
        m["post_onset_rmse_yaw"] = float(np.sqrt(np.mean(e_yaw[onset:] ** 2)))
        # time from onset to the START of a qualifying dwell under the TASK spec
        m["time_to_task_tol"] = np.nan
        for t in range(onset, n - TASK_DWELL_STEPS + 1):
            if inside_task[t:t + TASK_DWELL_STEPS].all():
                m["time_to_task_tol"] = float((t - onset) * C.TS)
                break
    else:
        m["was_in_tol_at_onset"] = bool(inside_task[0])
        m["mode"] = "healthy"
        m["post_onset_rmse"] = m["rmse_pos"]
        m["post_onset_peak"] = m["peak_pos"]
        m["post_onset_rmse_yaw"] = m["rmse_yaw"]
        m["time_to_task_tol"] = m["completion_time"]

    # eligibility interval durations, for the separate duration statistics
    g = np.asarray(a["gate"], dtype=int)
    runs, cur = [], 0
    for v in g:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    m["gate_runs"] = runs
    return m


def _job(args):
    """One (method, model_seed, condition, episode) cell."""
    method, model_seed, cond, ep_seed, cert, tol, N, record_trace = args
    rng = S.scenario_rng(cond, ep_seed)
    sc = S.make_condition(cond, rng)
    pol = make_policy(method, model_seed, cert, N=N)
    log = run_policy_episode(pol, seed=ep_seed, steps=STEPS, scenario=sc)
    m = episode_metrics(log, sc, tol)
    m.update({"method": method, "model_seed": model_seed, "condition": cond,
              "ep_seed": ep_seed, "N": N})
    if record_trace:
        a = log.arrays()
        m["_trace"] = {k: np.asarray(a[k]).tolist() for k in
                       ("x_true", "x_hat", "ref_score", "u_prop", "u_nom_tx",
                        "pulse_command_s", "pulse_actual_s", "gate", "accepted",
                        "slack_cmd", "slack_fb", "action_src", "e_P", "accel",
                        "z_ctx", "fault_skip", "pose_valid")}
        m["_trace"]["onset"] = sc.onset_step
    return m


# --------------------------------------------------------------------------
def calibrate(cert, workers=12):
    """Single calibration pass on split 0, with the acceptance check DISABLED.

    Sets, then freezes:
      tol  recovery tolerance, from the zero-context HEALTHY steady error
      R    eligibility radius, a high quantile of ||e_k||_P actually visited
      eta  acceptance allowance, from the observed one-step slack deficits

    Disabling the check is deliberate: calibrating eta while the check is already
    rejecting would make the threshold depend on itself.

    Sec 6.3 LABELLING. None of these three is a statistical certificate threshold.
    `tol` is a baseline-relative diagnostic (the declared TASK spec is separate and
    fixed in TASK_TOL_POS/YAW). `R` is an operating envelope read off observed
    behaviour. `eta` is selected by calibration-split RMSE, which is CONTROLLER
    TUNING, not the manuscript's conformal procedure; the conformal value is computed
    alongside for comparison and reported. All three are frozen here, before any test
    episode is run, and the test split is never consulted.
    """
    print("\n--- calibration pass (split 0, check disabled)")
    seeds = [10_000 + i for i in range(N_CALIB_PER_COND)]

    # (a) recovery tolerance from the zero-context healthy runs
    jobs = [("zero_context", 0, "healthy", s, cert, np.inf, C.N_HORIZON_HW, False)
            for s in seeds]
    got = pmap(_job, jobs, desc="  calib tol", workers=workers)
    tol = float(np.percentile([g["final_pos"] for g in got], 90))
    print(f"    recovery tolerance   = {tol:.3f} m  "
          f"(p90 of zero-context healthy terminal error)")

    # (b) R and eta from the full policy in MONITOR mode: the check is evaluated and
    # its slack recorded, but never acted on, so eta is fitted to slacks that the
    # threshold itself did not influence
    cert_open = dict(cert, eta=0.0, R=1e9)
    jobs, out_eP, out_slack = [], [], []
    for cond in CONDITIONS:
        for s in seeds:
            jobs.append(("full_monitor", 0, cond, s, cert_open, tol,
                         C.N_HORIZON_HW, True))
    got = pmap(_job, jobs, desc="  calib R,eta", workers=workers)
    for g in got:
        tr = g["_trace"]
        out_eP += [v for v in tr["e_P"] if np.isfinite(v)]
        out_slack += [v for v in tr["slack_cmd"] if np.isfinite(v)]
    R = float(np.percentile(out_eP, 95)) if out_eP else 1e9
    deficits = [-v for v in out_slack if v < 0]
    frac_viol = float(np.mean([v < 0 for v in out_slack])) if out_slack else np.nan
    eta_conformal = float(np.percentile(deficits, 97.5)) if deficits else 0.0
    print(f"    eligibility radius R = {R:.3f}   (p95 of ||e||_P over "
          f"{len(out_eP)} calibration transitions)")
    print(f"    one-step decrease condition is VIOLATED by the candidate in "
          f"{frac_viol * 100:.1f}% of monitored steps")
    print(f"    conformal eta at delta=0.025 would be {eta_conformal:.4f}, which "
          f"accepts ~97.5% and is therefore near-inert")

    # ---- eta chosen by a DECLARED rule on the calibration split ----
    # Conformal calibration of eta targets coverage of a CERTIFICATE claim. Stage 7
    # finds the certified region empty at this authority, so there is no claim to
    # cover and the delta=0.025 quantile just makes the check inert. eta is therefore
    # selected as the value minimising calibration-split RMSE over a declared grid -
    # a model-selection rule on data disjoint from the test episodes.
    grid = [0.0, 0.5, 1.0, 2.0, eta_conformal]
    grid = sorted({round(float(g), 4) for g in grid})
    jobs, curve = [], []
    for e in grid:
        ce = dict(cert, eta=e, R=R)
        for cond in CONDITIONS:
            for s in seeds[:8]:
                jobs.append(("full", 0, cond, s, ce, tol, C.N_HORIZON_HW, False))
    got = pmap(_job, jobs, desc="  calib eta", workers=workers)
    per = len(jobs) // len(grid)
    for i, e in enumerate(grid):
        sub = got[i * per:(i + 1) * per]
        curve.append({"eta": e,
                      "rmse": float(np.mean([r["rmse_pos"] for r in sub])),
                      "peak": float(np.mean([r["peak_pos"] for r in sub])),
                      "frac_reject": float(np.nanmean([r["frac_reject"]
                                                       for r in sub]))})
    best = min(curve, key=lambda c: c["rmse"])
    eta = best["eta"]
    print("    eta selection on the calibration split:")
    for c in curve:
        mark = "  <- selected" if c["eta"] == eta else ""
        print(f"      eta={c['eta']:7.4f}  calib RMSE {c['rmse']:.4f}  "
              f"peak {c['peak']:.3f}  reject {c['frac_reject']:.3f}{mark}")

    return {"tol": tol, "R": R, "eta": eta, "eta_conformal": eta_conformal,
            "eta_curve": curve, "frac_decrease_violated": frac_viol,
            "n_calib_transitions": len(out_eP), "n_deficits": len(deficits),
            "eP_p50": float(np.percentile(out_eP, 50)) if out_eP else None,
            "eP_p99": float(np.percentile(out_eP, 99)) if out_eP else None,
            "selection_rule": "eta minimising calibration-split RMSE over a declared "
                              "grid; test episodes are disjoint",
            "eta_label": "CONTROLLER TUNING, not the manuscript's conformal "
                         "procedure. The conformal delta=0.025 value is reported "
                         "as eta_conformal for comparison.",
            "tol_label": "baseline-relative diagnostic threshold; the declared task "
                         "specification is separate and fixed in advance",
            "R_label": "operating envelope from observed ||e||_P, not a verified "
                       "region of attraction",
            "frozen_before_test": True}


# --------------------------------------------------------------------------
def block_bootstrap_paired(rows_a, rows_b, key, n_boot=4000, seed=0):
    """Paired effect a-b with a block bootstrap over PARENT EPISODES.

    Episodes are the resampling unit and training seeds are resampled with them, so
    neither time samples nor overlapping windows are treated as replicates.
    """
    ia = {(r["condition"], r["ep_seed"], r["model_seed"]): r[key] for r in rows_a}
    ib = {(r["condition"], r["ep_seed"], r["model_seed"]): r[key] for r in rows_b}
    keys = sorted(set(ia) & set(ib), key=str)
    if not keys:
        return None
    d = np.array([ia[k] - ib[k] for k in keys], dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return None
    # block over episode identity (condition, ep_seed), pooling the seeds within
    blocks = {}
    for k in keys:
        blocks.setdefault((k[0], k[1]), []).append(ia[k] - ib[k])
    bk = sorted(blocks, key=str)
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, len(bk), size=len(bk))
        vals = np.concatenate([blocks[bk[j]] for j in pick])
        vals = vals[np.isfinite(vals)]
        stats[i] = vals.mean() if vals.size else np.nan
    return {"mean": float(d.mean()), "lo": float(np.nanpercentile(stats, 2.5)),
            "hi": float(np.nanpercentile(stats, 97.5)), "n_pairs": int(d.size),
            "n_blocks": len(bk),
            "level": "episode, CONDITIONAL on the evaluated checkpoints",
            "n_distinct_scenarios": len({(k[0], k[1]) for k in keys}),
            "n_rollouts": int(d.size)}


def crossed_bootstrap_paired(rows_a, rows_b, key, n_boot=4000, seed=0):
    """Paired effect a-b resampling BOTH training seeds and episode identities.

    Sec 8.3: the episode-level interval above is conditional on the three trained
    checkpoints, so it answers "how would this effect vary over episodes for these
    models". It cannot speak for a broader training-and-deployment population. This
    crossed procedure resamples training seeds and episode identities together,
    preserving seed pairing between the two methods, which widens the interval to
    reflect the training variation. With only three seeds the resulting precision is
    genuinely poor, and that is the honest state of the evidence: more episodes cannot
    substitute for missing seed diversity.
    """
    ia = {(r["condition"], r["ep_seed"], r["model_seed"]): r[key] for r in rows_a}
    ib = {(r["condition"], r["ep_seed"], r["model_seed"]): r[key] for r in rows_b}
    shared = sorted(set(ia) & set(ib), key=str)
    if not shared:
        return None
    seeds = sorted({k[2] for k in shared})
    eps = sorted({(k[0], k[1]) for k in shared}, key=str)
    if len(seeds) < 2:
        return None
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for i in range(n_boot):
        s_pick = [seeds[j] for j in rng.integers(0, len(seeds), size=len(seeds))]
        e_pick = [eps[j] for j in rng.integers(0, len(eps), size=len(eps))]
        vals = []
        for s in s_pick:
            for (c, es) in e_pick:
                k = (c, es, s)
                if k in ia and k in ib:
                    v = ia[k] - ib[k]
                    if np.isfinite(v):
                        vals.append(v)
        stats[i] = np.mean(vals) if vals else np.nan
    d = np.array([ia[k] - ib[k] for k in shared], dtype=float)
    d = d[np.isfinite(d)]
    # seed-level means, reported because three seeds cannot support much else
    per_seed = {}
    for s in seeds:
        v = [ia[k] - ib[k] for k in shared
             if k[2] == s and np.isfinite(ia[k] - ib[k])]
        per_seed[int(s)] = float(np.mean(v)) if v else np.nan
    return {"mean": float(d.mean()), "lo": float(np.nanpercentile(stats, 2.5)),
            "hi": float(np.nanpercentile(stats, 97.5)),
            "n_seeds": len(seeds), "n_distinct_scenarios": len(eps),
            "per_seed_mean": per_seed,
            "level": "crossed over training seeds AND episodes"}


def agg(vals):
    v = np.asarray([x for x in vals if np.isfinite(x)], dtype=float)
    if v.size == 0:
        return {"mean": np.nan, "sd": np.nan, "median": np.nan,
                "iqr": [np.nan, np.nan], "n": 0}
    return {"mean": float(v.mean()), "sd": float(v.std(ddof=1)) if v.size > 1 else 0.0,
            "median": float(np.median(v)),
            "iqr": [float(np.percentile(v, 25)), float(np.percentile(v, 75))],
            "n": int(v.size)}


def main():
    t0 = time.time()
    print("=" * 78)
    print("STAGE 6  method variants and the matched comparison table")
    print("=" * 78)

    cert = certificate_design()
    print(f"\nfrozen supervision design: lambda={cert['lam']:.4f}  "
          f"lam0={cert['lam0']}  w_effort={cert['w_effort']:g}  "
          f"|K|max={np.abs(cert['K']).max():.2f}")
    print(f"  certificate nonempty at this design? {cert['eval']['nonempty']}  "
          f"-> the design below is OPERATIONAL supervision, not a certified region")

    cal = calibrate(cert)
    cert.update(eta=cal["eta"], R=cal["R"])
    tol = cal["tol"]

    # ------------------------------------------------------------------
    # test grid: splits 1-4 -> disjoint episode seeds from calibration
    # ------------------------------------------------------------------
    ep_seeds = [20_000 + i for i in range(N_TEST_PER_COND)]
    jobs = []
    for cond in CONDITIONS:
        for s in ep_seeds:
            for meth in SEEDLESS:
                jobs.append((meth, 0, cond, s, cert, tol, C.N_HORIZON_HW, False))
            for meth in LEARNED:
                for ms in SEEDS_FOR[meth]:
                    jobs.append((meth, ms, cond, s, cert, tol, C.N_HORIZON_HW,
                                 False))
    print(f"\n--- test grid: {len(jobs)} episodes "
          f"({len(METHODS)} methods x {len(CONDITIONS)} conditions x "
          f"{N_TEST_PER_COND} matched seeds)")
    rows = pmap(_job, jobs, desc="  episodes", workers=12)
    for r in rows:
        r.pop("_trace", None)

    out = {"conditions": list(CONDITIONS), "methods": list(METHODS),
           "n_test_per_condition": N_TEST_PER_COND, "model_seeds": list(MODEL_SEEDS),
           "calibration": cal, "recovery_tolerance_m": tol,
           "supervision_design": {
               "lam": cert["lam"], "lam0": cert["lam0"],
               "w_effort": cert["w_effort"], "eta": cert["eta"], "R": cert["R"],
               "K_absmax": float(np.abs(cert["K"]).max()),
               "certificate_nonempty": cert["eval"]["nonempty"],
               "binding": cert["eval"]["binding"],
               "note": "OPERATIONAL supervision design. Stage 7 finds the "
                       "certificate empty at hardware authority, so activity and "
                       "acceptance rates here are not evidence of a guarantee."},
           "manifest_hash": C.manifest_hash(),
           "rows": rows}

    report(out, rows, tol)
    out["wall_time_s"] = time.time() - t0
    with open(f"{RES}/stage6_methods.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote {RES}/stage6_methods.json ({out['wall_time_s'] / 60:.1f} min)")


def report(out, rows, tol):
    print("\n" + "=" * 78)
    print("MAIN COMPARISON TABLE")
    print(f"(recovery tolerance {tol:.3f} m, frozen on the calibration split; "
          f"hold {HOLD_STEPS * C.TS:.1f} s)")
    print("=" * 78)

    print(f"TASK SPEC (declared in advance, fixed across methods): "
          f"pos <= {TASK_TOL_POS:.2f} m AND yaw <= "
          f"{np.rad2deg(TASK_TOL_YAW):.0f} deg held for "
          f"{TASK_DWELL_STEPS * C.TS:.1f} s")
    print("`draws` counts DISTINCT matched scenario draws; `roll` counts rollouts "
          "(draws x checkpoints).")
    print("They are not the same number and only `draws` is an independent-sample "
          "count.\n")

    table = {}
    hdr = (f"{'condition':11s} {'ID':3s} {'method':17s} {'post-onset RMSE':>16s} "
           f"{'full RMSE':>10s} {'p-o peak':>9s} {'task':>8s} {'draws':>6s} "
           f"{'roll':>5s} {'elig':>6s} {'sup':>6s}")
    print(hdr)
    print("-" * len(hdr))
    for cond in CONDITIONS:
        for meth in METHODS:
            sub = [r for r in rows if r["condition"] == cond
                   and r["method"] == meth]
            if not sub:
                continue
            rm = agg([r["rmse_pos"] for r in sub])
            po = agg([r["post_onset_rmse"] for r in sub])
            pk = agg([r["post_onset_peak"] for r in sub])
            att = [r for r in sub if r["attempted"]]
            ns = sum(1 for r in att if r["success"])
            tr = agg([r["recovery_time"] for r in att if r["success"]])
            act = agg([r["frac_gate_on"] for r in sub])
            rej = agg([r["frac_reject"] for r in sub])
            # task success counts EVERY episode in the denominator, including
            # failures and non-completions
            n_task = sum(1 for r in sub if r["task_success"])
            task_rate = n_task / len(sub)
            n_draws = len({(r["condition"], r["ep_seed"]) for r in sub})
            sup = agg([r.get("frac_src_supervisor", np.nan) for r in sub])
            reac = [r for r in att if r.get("mode") == "reacquisition"]
            maint = [r for r in att if r.get("mode") == "maintenance"]
            srate = (ns / len(att)) if att else float("nan")
            table[f"{cond}|{meth}"] = {
                "id": METHOD_IDS[meth],
                "rmse_pos": rm, "peak_pos": agg([r["peak_pos"] for r in sub]),
                "post_onset_peak": pk,
                "success_rate": srate,
                "n_attempted": len(att), "n_success": ns, "recovery_time": tr,
                "task_success_rate": task_rate, "n_task_success": n_task,
                "n_episodes": len(sub), "n_distinct_draws": n_draws,
                "task_held_at_end_rate": float(np.mean(
                    [r["task_held_at_end"] for r in sub])),
                "frac_time_in_tol": agg([r["frac_time_in_tol"] for r in sub]),
                "completion_time": agg([r["completion_time"] for r in sub]),
                "time_to_task_tol": agg([r["time_to_task_tol"] for r in sub]),
                "n_reacquisition": len(reac), "n_maintenance": len(maint),
                "reacq_success_rate": (
                    float(np.mean([r["success"] for r in reac])) if reac
                    else float("nan")),
                "maint_success_rate": (
                    float(np.mean([r["success"] for r in maint])) if maint
                    else float("nan")),
                "frac_gate_on": act, "frac_reject": rej,
                "frac_supervisor": sup,
                "frac_src_candidate": agg(
                    [r.get("frac_src_candidate", np.nan) for r in sub]),
                "frac_src_fallback_checked": agg(
                    [r.get("frac_src_fallback_checked", np.nan) for r in sub]),
                "accel_p95": agg([r["accel_p95"] for r in sub]),
                "frac_fallback": agg([r["frac_fallback"] for r in sub]),
                "post_onset_rmse": po,
                "solve_ms_p95": agg([r["solve_ms_p95"] for r in sub])}
            print(f"{cond:11s} {METHOD_IDS[meth]:3s} {meth:17s} "
                  f"{po['mean']:7.3f}+-{po['sd']:<7.3f} "
                  f"{rm['mean']:10.3f} {pk['median']:9.2f} "
                  f"{n_task:3d}/{len(sub):<4d} {n_draws:6d} {len(sub):5d} "
                  f"{act['mean']:6.3f} {sup['mean']:6.3f}")
        print()
    out["table"] = table
    out["task_spec"] = {"tol_pos_m": TASK_TOL_POS,
                        "tol_yaw_rad": float(TASK_TOL_YAW),
                        "tol_yaw_deg": float(np.rad2deg(TASK_TOL_YAW)),
                        "dwell_s": TASK_DWELL_STEPS * C.TS,
                        "deadline_s": TASK_DEADLINE_STEPS * C.TS,
                        "provenance": "provisional development values declared "
                                      "before the final test; NOT measured "
                                      "spacecraft requirements"}

    # ---- paired effects ----
    print("=" * 78)
    print("TABLE B  causal component comparisons (Sec 7.1 / 12)")
    print("=" * 78)
    print("PRIMARY ENDPOINT, declared in advance: post-onset position RMSE,")
    print("primary comparison M3 - M2 (behavioural supervision).")
    print("Everything else below is exploratory and is labelled as such.\n")
    # Sec 7.1: M2-M1 isolates changing context (both have no behavioural loss);
    # M3-M1 would change two things at once and cannot isolate either.
    pairs = [("full", "no_impact", "M3-M2 behavioural supervision", True),
             ("no_impact", "constant_context", "M2-M1 changing context", False),
             ("full", "nominal_recovery", "M3-M0 learned residual", False),
             ("full", "fallback_only", "M3-M5 MPC beyond fallback", False),
             ("full", "full_no_check", "M3-M4 post-allocation check", False),
             ("full", "adaptive_mpc", "M3-M6 vs adaptive baseline", False),
             ("full", "zero_context", "M3-HW vs hardware comparator", False)]
    eff = {}
    for a, b, label, is_primary in pairs:
        mark = "  <== PRIMARY" if is_primary else "  (exploratory)"
        print(f"\n  {METHOD_IDS[a]}-{METHOD_IDS[b]}  {label}{mark}")
        for cond in CONDITIONS:
            ra = [r for r in rows if r["method"] == a and r["condition"] == cond]
            rb = [r for r in rows if r["method"] == b and r["condition"] == cond]
            # Pair on episode identity AND checkpoint where both sides have seeds.
            # Broadcasting is only permitted when one side genuinely does not depend
            # on the training seed; it is recorded so the reader knows which is which.
            sa = sorted({r["model_seed"] for r in ra})
            sb = sorted({r["model_seed"] for r in rb})
            broadcast = None
            if len(sb) < len(sa):
                rb = [dict(r, model_seed=ms) for r in rb for ms in sa]
                broadcast = b
            elif len(sa) < len(sb):
                ra = [dict(r, model_seed=ms) for r in ra for ms in sb]
                broadcast = a
            for key in ("post_onset_rmse", "rmse_pos", "post_onset_peak",
                        "task_success"):
                st = block_bootstrap_paired(ra, rb, key)
                if st is None:
                    continue
                st["broadcast_side"] = broadcast
                eff[f"{a}-{b}|{cond}|{key}"] = st
                if key == "post_onset_rmse" and broadcast is None:
                    cx = crossed_bootstrap_paired(ra, rb, key)
                    if cx is not None:
                        eff[f"{a}-{b}|{cond}|{key}|crossed"] = cx
            st = eff.get(f"{a}-{b}|{cond}|post_onset_rmse")
            if st:
                sig = "" if (st["lo"] <= 0 <= st["hi"]) else "  *"
                cx = eff.get(f"{a}-{b}|{cond}|post_onset_rmse|crossed")
                extra = (f"   crossed [{cx['lo']:+.4f}, {cx['hi']:+.4f}]"
                         if cx else "")
                print(f"    {cond:11s} d(post-onset RMSE) {st['mean']:+7.4f} m  "
                      f"episode-CI [{st['lo']:+7.4f}, {st['hi']:+7.4f}]{sig}"
                      f"{extra}")
                print(f"    {'':11s}   {st['n_distinct_scenarios']} distinct "
                      f"scenario draws, {st['n_rollouts']} rollouts"
                      + (f", {broadcast} broadcast across seeds"
                         if broadcast else ""))
    out["paired_effects"] = eff
    out["primary_endpoint"] = {
        "metric": "post_onset_rmse",
        "comparison": "full - no_impact (M3 - M2)",
        "declared": "before the final test run",
        "task_tolerance_m": TASK_TOL_POS,
        "interpretation": "effect size is judged against the task tolerance as "
                          "well as against its confidence interval"}

    # ---- seed-level results, required with only three seeds ----
    print("\n" + "=" * 78)
    print("SEED-LEVEL RMSE (protocol Sec 9.1: show seeds, not only pooled)")
    print("=" * 78)
    seedtab = {}
    print(f"{'method':17s} {'condition':11s} " +
          "".join(f"{'seed ' + str(s):>12s}" for s in MODEL_SEEDS))
    for meth in LEARNED:
        for cond in CONDITIONS:
            vals = []
            for ms in MODEL_SEEDS:
                sub = [r["rmse_pos"] for r in rows if r["method"] == meth
                       and r["condition"] == cond and r["model_seed"] == ms]
                vals.append(float(np.mean(sub)) if sub else np.nan)
            seedtab[f"{meth}|{cond}"] = vals
            print(f"{meth:17s} {cond:11s} " +
                  "".join("         -  " if not np.isfinite(v) else f"{v:12.4f}"
                          for v in vals))
    out["seed_level_rmse"] = seedtab

    # ---- anchoring preserved? ----
    print("\n" + "=" * 78)
    ap = agg([r["accel_p95"] for r in rows if r["condition"] == "healthy"])
    print(f"achieved-acceleration p95 across all healthy runs: "
          f"{ap['mean']:.4f} +- {ap['sd']:.4f} m/s^2   "
          f"(hardware band {C.ANCHORS.accel_p95_lo}-{C.ANCHORS.accel_p95_hi})")
    band = C.ANCHORS.accel_p95_lo <= ap["mean"] <= C.ANCHORS.accel_p95_hi
    print(f"  still inside the measured hardware band: {band}")
    out["anchor_preserved"] = {"accel_p95": ap, "in_band": bool(band)}


if __name__ == "__main__":
    main()

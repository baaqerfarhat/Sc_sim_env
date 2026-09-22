"""Path B Sec 9-10: estimands, the crossed scenario-paired bootstrap, and the claim gates.

THE ESTIMANDS (Sec 9.2), implemented exactly as written.

For method m, family f, condition c, scenario s, first average over that method's five
independently trained checkpoints:

    mean_RMSE(m,f,c,s) = (1/5) sum_seeds RMSE
    d21(f,c,s) = mean_RMSE(M2,f,c,s) - mean_RMSE(M1,f,c,s)
    d25(f,c,s) = mean_RMSE(M2,f,c,s) -      RMSE(M5,f,c,s)

Scenarios are therefore paired, but M1 and M2 training seeds are NOT falsely paired merely
because they share numerical seed labels. The condition-balanced family estimand gives
each condition equal weight:

    Delta(f) = (1/4) sum_conditions mean over the 60 scenario-specific differences

THE BOOTSTRAP (Sec 9.3), also exactly as written: analysis seed 260921, 10,000 resamples,
scenario IDs resampled within condition with every method's outcome kept paired, training
seeds resampled independently with the SAME resampled M2 seed vector reused across every
contrast involving M2 in a replicate, M5 paired to one seedless outcome per scenario,
R-off-clean and M4 resampled JOINTLY with the checkpoint they reuse, and M3/M2 resampled
jointly only because provenance verifies the matched initialisation and data-order policy.

THE GATES (Sec 10) decide manuscript WORDING only. The two co-primary comparisons carry
central 97.5% intervals (1.25th and 98.75th percentiles) as a Bonferroni allowance at a
nominal familywise 5% level. Everything else is descriptive.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

import pathb_common as PB

RES = "results"
ANALYSIS_SEED = 260921
N_BOOT = 10_000
# Sec 9.3: nominal 95% everywhere, plus a central 97.5% interval for the two co-primary
# gates as the multiplicity allowance
PCTL_95 = (2.5, 97.5)
PCTL_CO_PRIMARY = (1.25, 98.75)

# Sec 9.3: which contrasts may be resampled with JOINTLY paired training seeds, and why
JOINT_SEED_PAIRS = {
    ("M3", "M2"): "M3 and M2 at the same seed share initialisation, data order and "
                  "minibatch order by construction (independent RNG substreams per "
                  "job), verified in pathb3_train.json",
    ("M2", "M4"): "M4 reuses its corresponding M3 checkpoint",
    ("M3", "M4"): "M4 reuses its corresponding M3 checkpoint",
    ("M2", "Roff"): "R-off-clean is a deployment-only variant of the SAME M2 checkpoint",
}


# ==========================================================================
def load_rows(sfx=""):
    with open(f"{RES}/pathb5_test{sfx}.json") as f:
        art = json.load(f)
    return art, art["rows"]


def seed_means(rows, key):
    """mean over a method's own checkpoints, per (method, family, condition, scenario).

    Returns {(method, family, cond, ep_seed): {seed: value}} so the bootstrap can resample
    seeds, plus the plain five-seed mean used for the point estimate.
    """
    by = {}
    for r in rows:
        v = r.get(key)
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            continue
        k = (r["method"], r["family"], r["condition"], r["ep_seed"])
        s = r["model_seed"] if r["seeded"] else "_seedless"
        by.setdefault(k, {})[s] = float(v)
    return by


def point_estimate(by, a, b, family):
    """Delta(family) for contrast a-b: condition-balanced mean of scenario-paired
    differences of within-method seed means."""
    per_cond, detail = [], {}
    for cond in PB.CONDITIONS:
        diffs = []
        for (m, f, c, es), vals in by.items():
            if m != a or f != family or c != cond:
                continue
            kb = (b, f, c, es)
            if kb not in by:
                continue
            diffs.append(np.mean(list(vals.values()))
                         - np.mean(list(by[kb].values())))
        if diffs:
            detail[cond] = {"mean": float(np.mean(diffs)), "n_scenarios": len(diffs)}
            per_cond.append(np.mean(diffs))
    return (float(np.mean(per_cond)) if per_cond else np.nan), detail


def crossed_bootstrap(by, a, b, family, rng, n_boot=N_BOOT):
    """Sec 9.3 crossed scenario-paired bootstrap for one contrast on one family."""
    # organise by condition so scenarios are resampled WITHIN condition
    cells = {c: [] for c in PB.CONDITIONS}
    seeds_a, seeds_b = set(), set()
    for (m, f, c, es), vals in by.items():
        if f != family:
            continue
        if m == a:
            kb = (b, f, c, es)
            if kb in by:
                cells[c].append((es, vals, by[kb]))
                seeds_a |= set(vals)
                seeds_b |= set(by[kb])
    if not any(cells.values()):
        return None
    seeds_a = sorted(seeds_a, key=str)
    seeds_b = sorted(seeds_b, key=str)
    joint = ((a, b) in JOINT_SEED_PAIRS or (b, a) in JOINT_SEED_PAIRS)

    stats = np.empty(n_boot)
    for i in range(n_boot):
        # one resampled seed vector per method, reused across every condition in this
        # replicate; joint when the pairing is verified, independent otherwise
        pa = [seeds_a[j] for j in rng.integers(0, len(seeds_a), len(seeds_a))]
        if joint and len(seeds_a) == len(seeds_b):
            pb = [seeds_b[seeds_a.index(s)] for s in pa]
        else:
            pb = [seeds_b[j] for j in rng.integers(0, len(seeds_b), len(seeds_b))]
        per_cond = []
        for c in PB.CONDITIONS:
            items = cells[c]
            if not items:
                continue
            pick = rng.integers(0, len(items), len(items))
            d = []
            for j in pick:
                _, va, vb = items[j]
                ma = np.mean([va[s] for s in pa if s in va])
                mb = np.mean([vb[s] for s in pb if s in vb])
                d.append(ma - mb)
            per_cond.append(np.mean(d))
        stats[i] = np.mean(per_cond) if per_cond else np.nan
    return stats


def summarise(by, a, b, family, rng, co_primary=False):
    pt, detail = point_estimate(by, a, b, family)
    if not np.isfinite(pt):
        return None
    stats = crossed_bootstrap(by, a, b, family, rng)
    lo95, hi95 = np.nanpercentile(stats, PCTL_95)
    out = {"contrast": f"{a}-{b}", "family": family, "mean": pt,
           "ci95": [float(lo95), float(hi95)],
           "excludes_zero_95": bool(not (lo95 <= 0 <= hi95)),
           "per_condition": detail,
           "n_boot": N_BOOT, "analysis_seed": ANALYSIS_SEED,
           "joint_seed_resampling": ((a, b) in JOINT_SEED_PAIRS
                                     or (b, a) in JOINT_SEED_PAIRS),
           "joint_reason": JOINT_SEED_PAIRS.get((a, b),
                                                JOINT_SEED_PAIRS.get((b, a))),
           }
    if co_primary:
        lo, hi = np.nanpercentile(stats, PCTL_CO_PRIMARY)
        out["ci975"] = [float(lo), float(hi)]
        out["excludes_zero_975"] = bool(not (lo <= 0 <= hi))
    return out


# ==========================================================================
def per_seed_means(rows, a, family, key="post_onset_rmse"):
    """Sec 9.3: report all five seed-level means, because five seeds cannot support
    much else."""
    out = {}
    for s in PB.SEEDS:
        v = [r[key] for r in rows if r["method"] == a and r["family"] == family
             and r["model_seed"] == s and np.isfinite(r.get(key, np.nan))]
        out[int(s)] = float(np.mean(v)) if v else np.nan
    return out


def descriptive_table(rows):
    """Sec 13.1 Table 2: outcomes per family, condition and method."""
    tab = {}
    for f in PB.FAMILIES:
        for c in PB.CONDITIONS:
            for mid in PB.METHODS:
                sub = [r for r in rows if r["method"] == mid and r["family"] == f
                       and r["condition"] == c]
                if not sub:
                    continue
                units = {(r["family"], r["condition"], r["ep_seed"]) for r in sub}
                cks = {r["checkpoint_sha256"] for r in sub}

                def ag(k):
                    v = np.asarray([r.get(k, np.nan) for r in sub], dtype=float)
                    v = v[np.isfinite(v)]
                    return ({"mean": float(v.mean()),
                             "sd": float(v.std(ddof=1)) if v.size > 1 else 0.0,
                             "median": float(np.median(v)), "n": int(v.size)}
                            if v.size else {"mean": np.nan, "sd": np.nan,
                                            "median": np.nan, "n": 0})
                ts = [r for r in sub if r["task_success"] is not None]
                td = [r for r in sub if r["task_success_declared"] is not None]
                tab[f"{f}|{c}|{mid}"] = {
                    "n_unique_scenarios": len(units), "n_rollouts": len(sub),
                    "n_checkpoints": len(cks), "seeded": PB.METHODS[mid]["seeded"],
                    "post_onset_rmse": ag("post_onset_rmse"),
                    "rmse_pos": ag("rmse_pos"),
                    "post_onset_peak": ag("post_onset_peak"),
                    "post_onset_rmse_yaw": ag("post_onset_rmse_yaw"),
                    # task_success_v2 is a dual endpoint and the two frames are reported
                    # side by side, never merged. `achieved` is the true state a
                    # ground-truth observer certifies; `declared` is what the vehicle
                    # asserts from its own estimate. Their difference is the estimation
                    # gap and is an endpoint in its own right.
                    "task_success_rate": (float(np.mean([r["task_success"]
                                                         for r in ts]))
                                          if ts else np.nan),
                    "n_task_success": int(sum(1 for r in ts if r["task_success"])),
                    "n_task_scored": len(ts),
                    "task_success_rate_declared": (
                        float(np.mean([r["task_success_declared"] for r in td]))
                        if td else np.nan),
                    "n_task_success_declared": int(sum(1 for r in td
                                                       if r["task_success_declared"])),
                    "declared_not_achieved_rate": (
                        float(np.mean([bool(r["declared_not_achieved"]) for r in sub]))
                        if sub else np.nan),
                    "achieved_not_declared_rate": (
                        float(np.mean([bool(r["achieved_not_declared"]) for r in sub]))
                        if sub else np.nan),
                    "effort_force_mean": ag("effort_force_mean"),
                    "impulse_proxy_Ns": ag("impulse_proxy_Ns"),
                    "command_rate_norm": ag("command_rate_norm"),
                    "share_mpc": ag("share_mpc"),
                    "share_repair_replacement": ag("share_repair_replacement"),
                    "share_fallback": ag("share_fallback"),
                    "share_supervisor": ag("share_supervisor"),
                    "share_m5_feedback": ag("share_m5_feedback"),
                    "rej_first_screen": ag("rej_first_screen"),
                    "rej_repeated_check": ag("rej_repeated_check"),
                    "decision_ms_p95": ag("decision_ms_p95"),
                    "deadline_miss_rate": ag("deadline_miss_rate"),
                    "diag_recovery_rate": float(np.mean(
                        [bool(r["diag_recovery_success"]) for r in sub])),
                    **{f"src_{s}": ag(f"src_{s}") for s in PB.ACTION_SOURCES},
                }
    return tab


# ==========================================================================
def main():
    t0 = time.time()
    # The same analysis is run twice, once on the pre-registered matrix and once on the
    # corrected-radius re-run, and both are reported. Nothing is pooled across the two.
    import sys
    sfx = "_Rcorrected" if "--corrected" in sys.argv else ""
    print("=" * 78)
    print("PATH B  Sec 9-10: estimands, crossed bootstrap, claim gates"
          + ("  [CORRECTED RADIUS]" if sfx else "  [PRE-REGISTERED]"))
    print("=" * 78)
    art, rows = load_rows(sfx)
    print(f"\n{len(rows)} rollouts from manifest {art['manifest']['sha256'][:16]}")
    print(f"analysis seed {ANALYSIS_SEED}, {N_BOOT} resamples, "
          f"nominal 95% intervals and central 97.5% for the two co-primary gates")

    by = seed_means(rows, "post_onset_rmse")
    rng = np.random.default_rng(ANALYSIS_SEED)

    # ---- co-primary ----
    print("\n" + "=" * 78)
    print("CO-PRIMARY ESTIMANDS (Sec 1.2 / 9.2)")
    print("=" * 78)
    co = {}
    for name, a, b, family, desc in PB.CO_PRIMARY:
        s = summarise(by, a, b, family, rng, co_primary=True)
        if s is None:
            print(f"  {name}: MISSING")
            continue
        s["name"], s["description"] = name, desc
        s["per_seed_M2"] = per_seed_means(rows, "M2", family)
        if PB.METHODS[b]["seeded"]:
            s[f"per_seed_{b}"] = per_seed_means(rows, b, family)
        co[name] = s
        sig95 = "*" if s["excludes_zero_95"] else " "
        sig975 = "*" if s["excludes_zero_975"] else " "
        print(f"\n  {name} = Delta({family}) for {a}-{b}: {desc}")
        print(f"    point estimate {s['mean']:+.4f} m")
        print(f"    95%   [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}] {sig95}")
        print(f"    97.5% [{s['ci975'][0]:+.4f}, {s['ci975'][1]:+.4f}] {sig975}"
              f"   <- the co-primary gate interval")
        for c, d in s["per_condition"].items():
            print(f"      {c:11s} {d['mean']:+.4f} m over {d['n_scenarios']} scenarios")

    # ---- secondary ----
    print("\n" + "=" * 78)
    print("SECONDARY CONTRASTS (descriptive, Sec 9.3)")
    print("=" * 78)
    sec = {}
    for a, b, desc in PB.SECONDARY:
        for family in PB.FAMILIES:
            s = summarise(by, a, b, family, rng)
            if s is None:
                continue
            s["description"] = desc
            sec[f"{a}-{b}|{family}"] = s
    print(f"  {'contrast':12s} {'family':12s} {'mean':>9s} {'95% interval':>24s}  "
          f"description")
    for k, s in sec.items():
        mark = " *" if s["excludes_zero_95"] else "  "
        print(f"  {s['contrast']:12s} {s['family']:12s} {s['mean']:+9.4f} "
              f"[{s['ci95'][0]:+9.4f}, {s['ci95'][1]:+9.4f}]{mark} "
              f"{s['description']}")

    # ---- task-success differences, same resampling, BOTH frames ----
    # Reported descriptively. Sec 10.1 is explicit that an RMSE gate does not authorise a
    # task-utility claim, so these can neither broaden nor rescue the primary endpoints.
    task = {}
    for endpoint, label in (("task_success", "achieved, true state"),
                            ("task_success_declared", "declared, estimated state")):
        by_task = seed_means(rows, endpoint)
        for _, a, b, family, _ in PB.CO_PRIMARY:
            s = summarise(by_task, a, b, family, rng)
            if s is not None:
                s["endpoint"], s["frame"] = endpoint, label
                task[f"{a}-{b}|{family}|{endpoint}"] = s
    print("\n" + "=" * 78)
    print("TASK COMPLETION DIFFERENCES (descriptive; both frames, never merged)")
    print("=" * 78)
    for k, s in task.items():
        print(f"  {s['contrast']:10s} {s['family']:12s} {s['frame']:26s} "
              f"{s['mean']:+.4f}  95% [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}]"
              f"{' *' if s['excludes_zero_95'] else ''}")

    # ---- the estimation gap, a finding of this campaign rather than of the plan ----
    # The simulator has no absolute position reference after the one-shot t0 alignment, so
    # the estimate/truth error is an unbounded random walk (results/pathb2_floor.json). That
    # makes the two task frames diverge, and the divergence is a perception result: it
    # measures how often a method believes it has docked when it has not. It is reported
    # here for every condition because occlusion is exactly where it should be worst.
    print("\n" + "=" * 78)
    print("THE ESTIMATION GAP (declared but not achieved), by condition")
    print("=" * 78)
    gap = {}
    print(f"  {'method':9s} {'family':12s} " + "".join(f"{c[:10]:>12s}"
                                                       for c in PB.CONDITIONS))
    for mid in PB.METHODS:
        for f in PB.FAMILIES:
            cells = {}
            for c in PB.CONDITIONS:
                sub = [r for r in rows if r["method"] == mid and r["family"] == f
                       and r["condition"] == c]
                if sub:
                    cells[c] = float(np.mean([bool(r["declared_not_achieved"])
                                              for r in sub]))
            if not cells:
                continue
            gap[f"{mid}|{f}"] = cells
            print(f"  {mid:9s} {f:12s} " + "".join(
                f"{cells.get(c, float('nan')):12.3f}" for c in PB.CONDITIONS))

    # ---- Sec 10 claim gates ----
    print("\n" + "=" * 78)
    print("CLAIM GATES (Sec 10: these decide WORDING, not desirability)")
    print("=" * 78)
    gates = {}

    def verdict(s):
        if s is None:
            return "unresolved", "no estimate available"
        if s["mean"] < 0 and s.get("excludes_zero_975"):
            return "supported", ("point estimate below zero with the co-primary "
                                 "97.5% interval entirely below zero")
        if s["mean"] > 0 and s.get("excludes_zero_975"):
            return "adverse", ("point estimate ABOVE zero with the co-primary 97.5% "
                               "interval entirely above zero: the comparator is "
                               "better")
        return "unresolved", "the co-primary 97.5% interval contains zero"

    g1 = co.get("D21")
    v, why = verdict(g1)
    gates["dynamic_context_rmse"] = {
        "section": "10.1", "verdict": v, "reason": why, "estimand": "D21 (step family)",
        "wording": {
            "supported": "Changing context attains lower condition-balanced post-onset "
                         "position RMSE than the trained static-context baseline on the "
                         "retained step task.",
            "adverse": "The trained static-context baseline attains lower "
                       "condition-balanced post-onset position RMSE than changing "
                       "context; report as adverse.",
            "unresolved": "The dynamic-context RMSE comparison is unresolved at the "
                          "declared multiplicity allowance."}[v],
        "limits": ("A successful RMSE gate does not authorise an overall task-utility "
                   "claim. Task success, effort, failures and timing are reported "
                   "descriptively and cannot broaden or rescue this endpoint.")}

    g2 = co.get("D25")
    v2, why2 = verdict(g2)
    gates["learned_mpc_pipeline_rmse"] = {
        "section": "10.2", "verdict": v2, "reason": why2,
        "estimand": "D25 (smooth_dock_v1 family)",
        "wording": {
            "supported": "The complete learned-MPC pipeline attains lower "
                         "condition-balanced post-onset position RMSE than nominal "
                         "feedback/repair on the prespecified smooth preview mission.",
            "adverse": "Nominal feedback/repair attains lower condition-balanced "
                       "post-onset position RMSE than the complete learned-MPC "
                       "pipeline. Say so plainly.",
            "unresolved": "M5 is indistinguishable from the learned-MPC pipeline on "
                          "this endpoint. Say so plainly."}[v2],
        "limits": ("Even a successful gate establishes neither overall task utility nor "
                   "a planning-only advantage, because M2-M5 changes both learned "
                   "prediction and predictive optimisation.")}

    # 10.3 multimodal stream claim
    mm = {f: sec.get(f"M2-Mmotion|{f}") for f in PB.FAMILIES}
    better = [f for f, s in mm.items() if s and s["mean"] < 0 and s["excludes_zero_95"]]
    worse = [f for f, s in mm.items() if s and s["mean"] > 0 and s["excludes_zero_95"]]
    gates["multimodal_streams"] = {
        "section": "10.3",
        "verdict": ("supported" if len(better) == len(PB.FAMILIES)
                    else "adverse" if worse else "unresolved"),
        "families_favouring_M2": better, "families_favouring_Mmotion": worse,
        "wording": ("Explicit estimator-diagnostic channels improve tracking over an "
                    "otherwise identical encoder without them."
                    if len(better) == len(PB.FAMILIES) else
                    "The incremental value of the explicit estimator-diagnostic "
                    "channels is not established. The title is retained, the input "
                    "composition is described precisely, and no modality-fusion "
                    "benefit is claimed."),
        "limits": ("M-motion still contains vision-influenced estimated states and "
                   "residuals, so any claim is limited to the EXPLICIT diagnostic "
                   "channels and not to all perception information.")}

    # 10.4 behavioural loss
    bl = {f: sec.get(f"M3-M2|{f}") for f in PB.FAMILIES}
    gates["behavioural_loss"] = {
        "section": "10.4", "lambda_I_selected_on_dev": 0.0,
        "verdict": "adverse" if any(s and s["mean"] > 0 and s["excludes_zero_95"]
                                    for s in bl.values()) else "unresolved",
        "per_family": {f: (None if s is None else s["mean"]) for f, s in bl.items()},
        "wording": ("Behavioural supervision is reported as an ablation that did not "
                    "help. The development grid selected weight zero, so M2 is the "
                    "selected method and M3 is a labelled negative ablation. It is not "
                    "revived as a benefit without a new training design and a new "
                    "untouched test.")}

    # 10.5 repeated check and repair
    with open(f"{RES}/pathb4_gates.json") as f:
        gate_art = json.load(f)
    sg = gate_art["stop_gate"]
    rep = {f: sec.get(f"M2-Roff|{f}") for f in PB.FAMILIES}
    gates["repeated_check"] = {
        "section": "10.5",
        "verdict": ("redundant_under_preceding_screen" if sg["omit_M4_from_test"]
                    else "measured_in_test"),
        "development_evidence": {
            "n_episodes": sg["n_episodes"],
            "packets_identical": sg["packets_identical"],
            "sources_identical": sg["sources_identical"],
            "trajectories_identical": sg["trajectories_identical"],
            "m3_rejections": sg["m3_repeated_check_rejections"]},
        "wording": ("The repeated post-allocation check is REDUNDANT under the screen "
                    "that precedes it: over the development stop-gate episodes it never "
                    "fired and disabling it changed the selected packets, action sources "
                    "and trajectories not at all, bitwise. It is described as redundant, "
                    "not as beneficial, and no performance effect is claimed."
                    if sg["omit_M4_from_test"] else
                    "The repeated check changed behaviour on at least one development "
                    "pair, so its effect is estimated in the prospective matrix.")}
    gates["finite_repair"] = {
        "section": "10.5",
        "verdict": ("supported" if all(s and s["mean"] < 0 and s["excludes_zero_95"]
                                       for s in rep.values())
                    else "adverse" if any(s and s["mean"] > 0
                                          and s["excludes_zero_95"]
                                          for s in rep.values())
                    else "unresolved"),
        "per_family": {f: (None if s is None else s["mean"]) for f, s in rep.items()},
        "wording": ("Finite proposal repair improves tracking, measured against a clean "
                    "R-off variant in which both arms trial-allocate their own proposal "
                    "and both apply the same screens to the resulting transmitted "
                    "command. The historical M7 is NOT this experiment and is not "
                    "relabelled as it."),
        "note": ("M2 - R-off-clean is the repair effect. The historical M7 changed the "
                 "command the earlier screen was evaluated on as well as the repair, so "
                 "it is not an acceptable repair ablation.")}
    gates["certificate_and_safety"] = {
        "section": "10.6", "verdict": "not_claimed",
        "wording": ("No verified invariant region, calibrated safety probability, "
                    "collision-free, continuous-time safety or guaranteed recovery "
                    "claim is made. The transmitted-command proposition remains "
                    "conditional on its explicit discrepancy assumptions.")}

    for k, g in gates.items():
        print(f"\n  {g['section']:5s} {k:28s} -> {g['verdict'].upper()}")
        print(f"        {g['wording'][:150]}")

    out = {"stage": "pathb6_analysis" + sfx,
           "operating_radius_mode": art.get("operating_radius_mode",
                                            "pre-registered p95 rule"),
           "operating_constants": art.get("operational_constants"),
           "analysis_seed": ANALYSIS_SEED, "n_boot": N_BOOT,
           "pctl_95": list(PCTL_95), "pctl_co_primary": list(PCTL_CO_PRIMARY),
           "co_primary": co, "secondary": sec, "task_success_diff": task,
           "estimation_gap": gap,
           "task_spec": PB.TASK_SPEC,
           "gates": gates,
           "table": descriptive_table(rows),
           "per_seed_rmse": {f"{m}|{f}": per_seed_means(rows, m, f)
                             for m in PB.METHODS if PB.METHODS[m]["seeded"]
                             for f in PB.FAMILIES},
           "estimand_definition": {
               "primary_endpoint": "post-onset physical position RMSE, from the onset "
                                   "or pseudo-onset through the episode end",
               "seed_handling": "average within method over its own five checkpoints "
                                "BEFORE differencing; M1 and M2 seed labels are not "
                                "treated as paired",
               "condition_weighting": "each of the four conditions weighted equally",
               "joint_seed_pairs": {f"{a}-{b}": why
                                    for (a, b), why in JOINT_SEED_PAIRS.items()},
               "healthy_window_note": ("the healthy window is the pseudo-onset to "
                                       "episode end, NOT the whole episode as in the "
                                       "archive; the two are never pooled")},
           "wall_time_s": time.time() - t0}
    with open(f"{RES}/pathb6_analysis{sfx}.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\nwrote {RES}/pathb6_analysis{sfx}.json ({out['wall_time_s']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

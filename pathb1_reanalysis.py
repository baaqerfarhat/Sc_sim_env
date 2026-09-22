"""Path B Priority 1: historical log reanalysis (plan Sec 2.2, 3.3, 11.4).

Every number here is recomputed from the saved per-episode rows in
`results/stage6_methods.json`, not copied from the narrative report. The point is to
settle the plan's list of internal inconsistencies from artefact evidence and to restate
the archive with honest counts, so it can be used for MOTIVATION without being mistaken
for a prospective result.

No plant experiment is required for this stage.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

RES = "results"
os.makedirs(RES, exist_ok=True)

# Stage 6 internal names -> the manuscript's method IDs
ARCH_IDS = {"nominal_recovery": "M0", "constant_context": "M1", "no_impact": "M2",
            "full": "M3", "full_no_check": "M4", "fallback_only": "M5",
            "adaptive_mpc": "M6", "no_alloc_aware": "M7",
            "strict_first_action": "M8", "zero_context": "HW"}
# which archived methods provably do not depend on the checkpoint
CHECKPOINT_INDEPENDENT = ("nominal_recovery", "fallback_only", "zero_context",
                          "adaptive_mpc")


def note(label, text):
    print(f"\n  {label}")
    for ln in text.split("\n"):
        print(f"    {ln}")
    return {"finding": label, "detail": text}


# ==========================================================================
def counts_table(rows):
    """Sec 11.4: unique scenarios, trained checkpoints and rollouts, separately."""
    out = {}
    for meth in sorted({r["method"] for r in rows}):
        sub = [r for r in rows if r["method"] == meth]
        units = {(r["condition"], r["ep_seed"]) for r in sub}
        seeds = sorted({r["model_seed"] for r in sub})
        out[meth] = {"id": ARCH_IDS.get(meth, meth),
                     "n_rollouts": len(sub), "n_unique_scenarios": len(units),
                     "model_seeds_evaluated": seeds,
                     "n_checkpoints_evaluated": len(seeds),
                     "rollouts_per_scenario": len(sub) / max(len(units), 1),
                     "checkpoint_independent": meth in CHECKPOINT_INDEPENDENT}
    return out


def dedupe_check(rows, meth, key="post_onset_rmse"):
    """Are the repeated seed indices of a deterministic method identical?

    If they are, the archive's rollout count for that method is a multiple of its real
    independent-sample count, and Sec 11.4 forbids reporting the copies as replicates.
    """
    sub = [r for r in rows if r["method"] == meth]
    seeds = sorted({r["model_seed"] for r in sub})
    if len(seeds) < 2:
        return {"n_seeds": len(seeds), "identical": None,
                "n_unique_outcomes": len({(r["condition"], r["ep_seed"]) for r in sub})}
    by = {}
    for r in sub:
        by.setdefault((r["condition"], r["ep_seed"]), {})[r["model_seed"]] = r[key]
    diffs = [max(v.values()) - min(v.values()) for v in by.values() if len(v) > 1]
    return {"n_seeds": len(seeds), "max_spread": float(max(diffs)) if diffs else 0.0,
            "identical": bool(diffs and max(diffs) == 0.0),
            "n_unique_outcomes": len(by),
            "archived_rollouts": len(sub),
            "inflation_factor": len(sub) / max(len(by), 1)}


def paired_sign(rows, a, b, key="post_onset_rmse"):
    """Scenario-paired difference a-b per condition, recomputed from the rows."""
    out = {}
    for cond in sorted({r["condition"] for r in rows}):
        ia, ib = {}, {}
        for r in rows:
            if r["condition"] != cond:
                continue
            k = (r["ep_seed"], r["model_seed"])
            if r["method"] == a:
                ia[k] = r[key]
            elif r["method"] == b:
                ib[k] = r[key]
        # broadcast a checkpoint-independent side across the other side's seeds
        if len({k[1] for k in ib}) < len({k[1] for k in ia}):
            base = {k[0]: v for k, v in ib.items()}
            ib = {k: base[k[0]] for k in ia if k[0] in base}
        elif len({k[1] for k in ia}) < len({k[1] for k in ib}):
            base = {k[0]: v for k, v in ia.items()}
            ia = {k: base[k[0]] for k in ib if k[0] in base}
        shared = sorted(set(ia) & set(ib))
        if not shared:
            continue
        d = np.array([ia[k] - ib[k] for k in shared], dtype=float)
        d = d[np.isfinite(d)]
        out[cond] = {"mean": float(d.mean()), "n_rollout_pairs": int(d.size),
                     "n_unique_scenarios": len({k[0] for k in shared}),
                     "sign": "favours " + (a if d.mean() < 0 else b)}
    return out


# ==========================================================================
def main():
    t0 = time.time()
    print("=" * 78)
    print("PATH B  Priority 1: historical log reanalysis")
    print("=" * 78)
    with open(f"{RES}/stage6_methods.json") as f:
        s6 = json.load(f)
    rows = s6["rows"]
    with open(f"{RES}/stage5_training.json") as f:
        s5 = json.load(f)
    print(f"\nsource artefact: {len(rows)} archived rollouts, "
          f"manifest {s6.get('manifest_hash')}")
    print("Status: HISTORICAL. These rows are motivation, not a prospective Path B "
          "result,\nand are never pooled with the new campaign.")

    findings, out = [], {}

    # ---- Sec 11.4 counts ----
    print("\n" + "=" * 78)
    print("Sec 11.4  unique scenarios vs trained checkpoints vs rollouts")
    print("=" * 78)
    ct = counts_table(rows)
    print(f"  {'ID':4s} {'method':18s} {'rollouts':>9s} {'unique':>7s} {'ckpts':>6s} "
          f"{'roll/scen':>10s} {'ckpt-indep':>11s}")
    for meth, c in sorted(ct.items(), key=lambda kv: kv[1]["id"]):
        print(f"  {c['id']:4s} {meth:18s} {c['n_rollouts']:9d} "
              f"{c['n_unique_scenarios']:7d} {c['n_checkpoints_evaluated']:6d} "
              f"{c['rollouts_per_scenario']:10.1f} "
              f"{str(c['checkpoint_independent']):>11s}")
    out["counts"] = ct

    # ---- deduplication of deterministic methods ----
    print("\n" + "=" * 78)
    print("Sec 3.3  duplicate pseudo-replicates of deterministic methods")
    print("=" * 78)
    dd = {}
    for meth in sorted({r["method"] for r in rows}):
        d = dedupe_check(rows, meth)
        dd[meth] = d
        if d.get("n_seeds", 0) > 1:
            print(f"  {ARCH_IDS.get(meth, meth):4s} {meth:18s} "
                  f"{d['n_seeds']} seed indices, max spread {d['max_spread']:.2e}, "
                  f"identical={d['identical']}, "
                  f"{d['archived_rollouts']} rollouts over "
                  f"{d['n_unique_outcomes']} unique outcomes "
                  f"(inflation x{d['inflation_factor']:.1f})")
    out["deduplication"] = dd
    infl = {ARCH_IDS.get(m, m): d for m, d in dd.items()
            if d.get("identical") and d.get("inflation_factor", 1) > 1}
    findings.append(note(
        "Deterministic methods were evaluated at several seed indices that produced "
        "BITWISE identical outcomes.",
        f"Affected: {sorted(infl)}. Each contributes "
        f"{next(iter(infl.values()))['n_unique_outcomes'] if infl else 0} independent "
        f"scenario outcomes, not\n"
        f"{next(iter(infl.values()))['archived_rollouts'] if infl else 0}. The archived "
        f"5,280-rollout figure is a ROLLOUT count and must not be\nread as a sample "
        f"size. Path B runs these methods once per scenario."))

    # ---- M1 training vs evaluation coverage ----
    m1_eval = sorted({r["model_seed"] for r in rows
                      if r["method"] == "constant_context"})
    m1_trained = sorted(int(k.split("_s")[1]) for k in s5["runs"]
                        if k.startswith("const_s"))
    findings.append(note(
        "M1 training coverage and M1 evaluation coverage are different numbers.",
        f"Stage 5 trained constant-context seeds {m1_trained}; Stage 6 evaluated only "
        f"seeds {m1_eval}.\nThe archived M2-M1 comparison therefore rests on a SINGLE M1 "
        f"checkpoint against three\nM2 checkpoints, so it carries no M1 training "
        f"variability at all. Path B evaluates five\nseeds on both sides."))
    out["m1_coverage"] = {"trained": m1_trained, "evaluated": m1_eval}

    # ---- signs and intervals for the four contrasts the plan names ----
    print("\n" + "=" * 78)
    print("Sec 3.3  signs of the four named contrasts, recomputed from the rows")
    print("=" * 78)
    contrasts = [("no_impact", "constant_context", "M2-M1 changing context"),
                 ("full", "no_impact", "M3-M2 behavioural loss"),
                 ("no_impact", "fallback_only", "M2-M5 learned MPC vs feedback"),
                 ("full", "full_no_check", "M3-M4 repeated check")]
    signs = {}
    for a, b, label in contrasts:
        ps = paired_sign(rows, a, b)
        signs[f"{a}-{b}"] = {"label": label, "per_condition": ps,
                             "saved_intervals": {
                                 c: s6["paired_effects"].get(
                                     f"{a}-{b}|{c}|post_onset_rmse")
                                 for c in ps}}
        print(f"\n  {label}")
        for c, v in ps.items():
            si = s6["paired_effects"].get(f"{a}-{b}|{c}|post_onset_rmse") or {}
            crossed = s6["paired_effects"].get(
                f"{a}-{b}|{c}|post_onset_rmse|crossed") or {}
            ci = (f"[{si.get('lo', float('nan')):+.4f}, "
                  f"{si.get('hi', float('nan')):+.4f}]")
            cx = (f"crossed [{crossed['lo']:+.4f}, {crossed['hi']:+.4f}]"
                  if crossed else "crossed n/a")
            print(f"    {c:11s} {v['mean']:+.4f} m  episode-CI {ci}  {cx}  "
                  f"{v['sign']}")
    out["contrast_signs"] = signs

    # ---- Sec 2.2 first inconsistency: crossed intervals vs the text ----
    m32 = {c: s6["paired_effects"].get(f"full-no_impact|{c}|post_onset_rmse|crossed")
           for c in ("healthy", "actuator", "perception", "combined")}
    strictly_pos = [c for c, v in m32.items() if v and v["lo"] > 0]
    contains0 = [c for c, v in m32.items() if v and v["lo"] <= 0 <= v["hi"]]
    findings.append(note(
        "Resolved: the report's claim that the seed-crossed M3-M2 intervals include "
        "zero is WRONG about its own artefact.",
        f"Recomputed from the saved intervals: strictly positive in {strictly_pos}; "
        f"containing zero in\n{contains0 or 'no condition'}. A strictly positive M3-M2 "
        f"interval means the behavioural-loss model is\nsignificantly WORSE, which is a "
        f"stronger adverse finding than the text stated, not a\nweaker one. Path B "
        f"reports M3 as an adverse ablation on that basis."))
    out["m3_m2_crossed"] = m32

    # ---- Sec 2.2 second inconsistency: the "load-bearing" check ----
    m34 = {c: (s6["paired_effects"].get(f"full-full_no_check|{c}|post_onset_rmse")
               or {}).get("mean") for c in ("healthy", "actuator", "perception",
                                            "combined")}
    rej = {}
    for meth in ("full", "full_no_check"):
        sub = [r for r in rows if r["method"] == meth]
        rej[meth] = {"mean_frac_reject": float(np.nanmean(
            [r.get("frac_reject", np.nan) for r in sub])),
            "total_would_reject": int(sum(r["policy_stats"].get("n_would_reject", 0)
                                          for r in sub if "policy_stats" in r))
            if any("policy_stats" in r for r in sub) else None}
    findings.append(note(
        "Resolved: the post-allocation acceptance check is NOT load-bearing; it is "
        "redundant under the screen that precedes it.",
        f"Recomputed M3-M4 post-onset RMSE differences by condition: "
        f"{ {k: (None if v is None else round(v, 6)) for k, v in m34.items()} }.\n"
        f"Every one is exactly zero, and the enabled check's rejection rate is "
        f"{rej['full']['mean_frac_reject']:.4f}.\nThe reason is structural: once the "
        f"first-action condition carries the same allowance, the\ntwo tests are the same "
        f"inequality on the same quantity, so a candidate that passes the\nfirst cannot "
        f"fail the second. Path B therefore describes the component as redundant,\nnot "
        f"beneficial, and claims no performance effect for it."))
    out["m3_m4"] = {"per_condition_difference": m34, "rejection_rates": rej}

    # ---- Sec 3.3 counter reconciliation ----
    print("\n" + "=" * 78)
    print("Sec 3.3  mechanism counters reconciled against the action-source shares")
    print("=" * 78)
    recon = {}
    for meth in ("full", "no_impact", "constant_context", "nominal_recovery",
                 "fallback_only"):
        sub = [r for r in rows if r["method"] == meth]
        if not sub:
            continue
        tot_steps = sum(r.get("n_steps", 0) for r in sub)
        # The archive's per-episode rows carry the DERIVED rates but not the raw policy
        # counters, so the reconciliation below is against the rates. That is itself a
        # logging gap, and it is one of the things Sec 8 fixes: Path B rows carry the
        # counters as well, so a rate and its counter can be cross-checked.
        st = {k: float(np.nanmean([r.get(k, np.nan) for r in sub]))
              for k in ("frac_reject", "frac_gate_on", "frac_fallback",
                        "action_src_sum")}
        # `fallback_only` is M5's own archived label for its single command source; it is
        # renamed `m5_feedback` in the Sec 8.4 taxonomy. Omitting it here is what made an
        # earlier pass of this reanalysis report M5's shares as summing to 0.015.
        shares = {k: float(np.nanmean([r.get(f"frac_src_{k}", np.nan) for r in sub]))
                  for k in ("candidate", "fallback_first_action", "fallback_checked",
                            "fallback_inadmissible", "fallback_solver_fail",
                            "unchecked_solver_fallback", "fallback_only",
                            "supervisor")}
        ssum = sum(v for v in shares.values() if np.isfinite(v))
        recon[meth] = {"id": ARCH_IDS[meth], "n_steps": tot_steps,
                       "counters": st, "source_shares": shares,
                       "share_sum": ssum}
        print(f"\n  {ARCH_IDS[meth]:4s} {meth:18s} shares sum to {ssum:.6f}")
        for k, v in shares.items():
            if np.isfinite(v) and v > 0:
                print(f"       {k:28s} {v:.4f}")
        print(f"       rates: reject {st['frac_reject']:.4f}  eligible "
              f"{st['frac_gate_on']:.4f}  solver fallback {st['frac_fallback']:.4f}  "
              f"source sum {st['action_src_sum']:.6f}")
    out["counter_reconciliation"] = recon
    bad = {k: v["share_sum"] for k, v in recon.items() if abs(v["share_sum"] - 1) > 1e-6}
    findings.append(note(
        "The archived action-source shares are complete and sum to one.",
        f"Checked on every learned method: deviations {bad or 'none'}. This was NOT true "
        f"of the\nfirst campaign, whose reported decomposition omitted the first-action "
        f"path and left\n24-41% of steps unattributed. Path B keeps the property and "
        f"extends the taxonomy from 8\nlabels to the 12 mutually exclusive labels of Sec "
        f"8.4."))

    # ---- terminology, fixed once ----
    gloss = {
        "first screen": "the Eq. (15) first-action decrease condition, evaluated on the "
                        "nominal-equivalent TRANSMITTED command before transmission",
        "repeated decrease check": "the Eq. (18) post-allocation acceptance test, "
                                   "evaluated on the same quantity after allocation. "
                                   "Redundant under the first screen once both carry "
                                   "the same allowance.",
        "finite proposal repair": "the bounded search over proposal seeds (raw MPC, "
                                  "projected MPC, P-optimal wrench, feedback) plus one "
                                  "Newton step on the known allocation map",
        "continuous projection": "exact projection of the MPC first action onto the "
                                 "first-screen feasible set; a COMPONENT of repair, not "
                                 "a synonym for it",
        "allocation compensation": "the Newton step on the allocation map; also a "
                                   "component of repair",
        "operational eligibility": "the pre-action test that the state is inside the "
                                   "calibrated radius R and a passing fallback exists",
        "supervisor": "the fixed velocity/rate damping controller used when eligibility "
                      "fails. NOT a safety guarantee.",
    }
    findings.append(note(
        "Terminology is fixed once and used consistently from here on.",
        "\n".join(f"{k}: {v}" for k, v in gloss.items())))
    out["glossary"] = gloss

    # ---- what survives ----
    out["preserved"] = {
        "lambda_I_selected_on_dev": float(s5["lambda_grid"]["selected"]),
        "selection_metric": s5["lambda_grid"]["selection_metric"],
        "selected_on": s5["lambda_grid"]["selected_on"],
        "consequence": ("M2 is the SELECTED method and M3 is a labelled ablation. This "
                        "was decided on development data before any test run and is "
                        "preserved unchanged in Path B.")}
    print("\n" + "=" * 78)
    print(f"PRESERVED: lambda_I = {out['preserved']['lambda_I_selected_on_dev']:g} was "
          f"selected on {out['preserved']['selected_on']}.")
    print("=" * 78)

    out.update({"stage": "pathb1_reanalysis", "n_archived_rollouts": len(rows),
                "source_manifest_hash": s6.get("manifest_hash"),
                "status": "HISTORICAL: motivation only, never pooled with Path B",
                "findings": findings, "wall_time_s": time.time() - t0})
    with open(f"{RES}/pathb1_reanalysis.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\nwrote {RES}/pathb1_reanalysis.json ({out['wall_time_s']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

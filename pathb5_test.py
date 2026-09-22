"""Path B Sec 11.3: the prospective test matrix.

Two task families x four conditions x 60 unique scenarios = 480 unique scenario-condition
units. On top of that:

    seeded methods   M1, M2, M3, M-motion   4 x 5 seeds x 480 = 9,600 rollouts
    seedless         M0, M5                 2 x 480          =   960 rollouts
    R-off-clean      5 reused M2 checkpoints x 480            = 2,400 rollouts
    M4               included ONLY if the Sec 7 stop gate did not fire

The reduced route (M4 omitted under the prespecified semantic stop rule) is 12,960
rollouts, which Sec 11.3 blesses explicitly; it supports no population-level M3-M4 effect
estimate, only the development semantic/replay result.

Sec 9.1: nothing is discarded. Supervisor intervals, solver failures, command-search
failures, gate inactivity, deadline misses and runs that never meet the task all stay in
the denominators, and every post-onset window runs through the declared episode end.

Sec 11.4: the long-form output carries one row per rollout, with the unique scenario
count, the trained-checkpoint count and the seedless flag recorded, so a table can never
report replicated deterministic outcomes as independent samples.
"""
from __future__ import annotations

import csv
import json
import os
import time

import numpy as np

import pathb_common as PB
from scsim import config as C
from scsim.parallel import pmap

RES = "results"
os.makedirs(RES, exist_ok=True)
WORKERS = 16

# one representative trace per family, for the Sec 13.2 figure, taken from a declared
# scenario rather than chosen after looking at outcomes
TRACE_UNITS = {("smooth_dock", "combined"): PB.KEY_BLOCKS["test"],
               ("step", "combined"): PB.KEY_BLOCKS["test"]}


def build_jobs(cert, include_M4):
    jobs, plan = [], {}
    mids = ["M0", "M1", "M2", "M3", "M5", "Mmotion", "Roff"]
    if include_M4:
        mids.insert(4, "M4")
    seeds_list = PB.scenario_keys("test", PB.N_TEST_PER_CELL)
    for mid in mids:
        spec = PB.METHODS[mid]
        seeds = PB.SEEDS if spec["seeded"] else (0,)
        n = 0
        for ms in seeds:
            for fam in PB.FAMILIES:
                for cond in PB.CONDITIONS:
                    for es in seeds_list:
                        want = (TRACE_UNITS.get((fam, cond)) == es
                                and mid in ("M2", "M5") and ms == 0)
                        jobs.append((mid, ms, fam, cond, es, cert,
                                     PB.DIAGNOSTIC_RECOVERY_TOL, C.N_HORIZON_HW,
                                     want))
                        n += 1
        plan[mid] = {"id": mid, "seeded": spec["seeded"],
                     "n_checkpoints": len(seeds), "n_rollouts": n,
                     "n_unique_units": len(PB.FAMILIES) * len(PB.CONDITIONS)
                     * PB.N_TEST_PER_CELL,
                     "label": spec["label"]}
    return jobs, plan


def main():
    t0 = time.time()
    # Two radii are run, and both are reported. `corrected` uses the envelope rule derived
    # in pathb4b_radius.py after the pre-registered rule was found to put the retained step
    # task inside an absorbing ineligible set; it writes to its own artefact so the
    # pre-registered matrix is never overwritten.
    import sys
    corrected = "--corrected" in sys.argv
    sfx = "_Rcorrected" if corrected else ""
    print("=" * 78)
    print("PATH B  Sec 11.3: prospective test matrix"
          + ("  [CORRECTED OPERATING RADIUS]" if corrected else "  [PRE-REGISTERED]"))
    print("=" * 78)

    with open(f"{RES}/pathb4_gates.json") as f:
        gates = json.load(f)
    cal = gates["calibration"]
    include_M4 = not gates["stop_gate"]["omit_M4_from_test"]

    import stage6_methods as s6
    cert = s6.certificate_design()
    cert.update(eta=cal["eta"], R=cal["R"])
    if corrected:
        with open(f"{RES}/pathb4b_radius.json") as f:
            rc = json.load(f)["corrected"]
        cert["R"] = float(rc["R"])
        print(f"\noperating radius REPLACED: {cal['R']:.4f} -> {cert['R']:.4f}")
        print(f"  rule: {rc['rule']}")
        print(f"  eta and every other constant are unchanged, so this isolates R.")
    print(f"\nfrozen operational constants (from the calibration block, never the "
          f"test block):")
    print(f"  lambda = {cert['lam']:.4f}   eta = {cert['eta']:g}   "
          f"R = {cert['R']:.4f}   diagnostic tolerance = {cal['diagnostic_tol']} m")
    print(f"  M4 included in the matrix: {include_M4}  "
          f"({gates['stop_gate']['consequence']})")

    manifest = PB.scenario_manifest("test", n=PB.N_TEST_PER_CELL)
    print(f"\ntest manifest sha256 {manifest['sha256']}")
    print(f"population sha256    {manifest['population_sha256']}")
    print(f"{manifest['n_units']} unique scenario-condition units "
          f"({len(PB.FAMILIES)} families x {len(PB.CONDITIONS)} conditions x "
          f"{PB.N_TEST_PER_CELL} keys)")

    jobs, plan = build_jobs(cert, include_M4)
    print(f"\n{'method':9s} {'seeded':>7s} {'ckpts':>6s} {'units':>6s} {'rollouts':>9s}"
          f"  definition")
    for mid, p in plan.items():
        print(f"{mid:9s} {str(p['seeded']):>7s} {p['n_checkpoints']:6d} "
              f"{p['n_unique_units']:6d} {p['n_rollouts']:9d}  {p['label']}")
    print(f"{'TOTAL':9s} {'':>7s} {'':>6s} {manifest['n_units']:6d} "
          f"{len(jobs):9d}")

    rows = pmap(PB.run_unit, jobs, desc="  rollouts", workers=WORKERS, chunksize=4)

    # pull the representative traces out before they bloat the main artefact
    traces = {}
    for r in rows:
        tr = r.pop("_trace", None)
        if tr is not None:
            traces[f"{r['method']}|{r['family']}|{r['condition']}|{r['ep_seed']}"] = tr
    if traces:
        with open(f"{RES}/pathb_traces{sfx}.json", "w") as f:
            json.dump(traces, f)
        print(f"\nwrote {len(traces)} representative traces to "
              f"{RES}/pathb_traces{sfx}.json")

    # ---- Sec 11.4 deterministic count reporting, checked not asserted ----
    counts = {}
    for mid in plan:
        sub = [r for r in rows if r["method"] == mid]
        units = {(r["family"], r["condition"], r["ep_seed"]) for r in sub}
        cks = {r["checkpoint_sha256"] for r in sub}
        counts[mid] = {"n_rollouts": len(sub), "n_unique_units": len(units),
                       "n_distinct_checkpoints": len(cks),
                       "seeded": PB.METHODS[mid]["seeded"],
                       "rollouts_per_unit": len(sub) / max(len(units), 1)}
    print(f"\n{'method':9s} {'rollouts':>9s} {'unique':>7s} {'ckpts':>6s} "
          f"{'roll/unit':>10s}  seedless methods must be 1.0")
    for mid, c in counts.items():
        print(f"{mid:9s} {c['n_rollouts']:9d} {c['n_unique_units']:7d} "
              f"{c['n_distinct_checkpoints']:6d} {c['rollouts_per_unit']:10.1f}")

    # ---- Sec 9.5 failure and censoring ledger ----
    print("\nterminal progress categories (exactly one per rollout, Sec 9.5)")
    hdr = f"{'method':9s} " + "".join(f"{c[:14]:>16s}" for c in PB.PROGRESS_CATEGORIES)
    print(hdr)
    ledger = {}
    for mid in plan:
        sub = [r for r in rows if r["method"] == mid]
        cc = {c: sum(1 for r in sub if r["progress_category"] == c)
              for c in PB.PROGRESS_CATEGORIES}
        assert sum(cc.values()) == len(sub), f"{mid}: categories are not exhaustive"
        ledger[mid] = {"progress": cc, "n": len(sub),
                       "flags": {fl: sum(1 for r in sub if r.get(fl))
                                 for fl in PB.EVENT_FLAGS}}
        print(f"{mid:9s} " + "".join(f"{cc[c]:16d}" for c in PB.PROGRESS_CATEGORIES))
    print("\northogonal event flags (several may be true for one rollout)")
    print(f"{'method':9s} " + "".join(f"{f[:13]:>15s}" for f in PB.EVENT_FLAGS))
    for mid in plan:
        print(f"{mid:9s} " + "".join(f"{ledger[mid]['flags'][f]:15d}"
                                     for f in PB.EVENT_FLAGS))

    # ---- long-form output, one row per rollout ----
    keep = [k for k in rows[0] if k != "policy_stats"]
    csv_path = f"{RES}/pathb_rollouts{sfx}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keep, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keep})
    print(f"\nwrote {csv_path} ({len(rows)} rows, {len(keep)} columns)")

    out = {"stage": "pathb5_test" + sfx,
           "operating_radius_mode": ("corrected envelope rule" if corrected
                                     else "pre-registered p95 rule"),
           "families": list(PB.FAMILIES), "conditions": list(PB.CONDITIONS),
           "n_per_cell": PB.N_TEST_PER_CELL,
           "seeds": list(PB.SEEDS),
           "include_M4": include_M4,
           "manifest": {k: v for k, v in manifest.items() if k != "units"},
           "plan": plan, "counts": counts, "ledger": ledger,
           "operational_constants": {"lam": cert["lam"], "eta": cert["eta"],
                                     "R": cert["R"],
                                     "diagnostic_tol": cal["diagnostic_tol"],
                                     "frozen_on": "calibration key block, before any "
                                                  "test episode"},
           "task_spec": PB.TASK_SPEC,
           "analysis_population": ("all rollouts retained: supervisor intervals, solver "
                                   "failures, search failures, gate inactivity, "
                                   "deadline misses and non-completions are all in the "
                                   "denominators; no exclusions were applied"),
           "n_rollouts": len(rows),
           "manifest_hash": C.manifest_hash(),
           "rows": rows,
           "wall_time_s": time.time() - t0}
    with open(f"{RES}/pathb5_test{sfx}.json", "w") as f:
        json.dump(out, f, default=str)
    print(f"wrote {RES}/pathb5_test{sfx}.json "
          f"({out['wall_time_s'] / 60:.1f} min, {len(rows)} rollouts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

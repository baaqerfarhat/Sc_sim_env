"""Per-condition intervals for the manuscript's effects table.

`pathb6_analysis.py` bootstraps the condition-BALANCED family estimand, which is what the
claim gates need. The manuscript's Table I is laid out per condition, so this script runs the
same crossed scenario-paired bootstrap cell by cell: same analysis seed, same resample count,
same joint-seed rules, same within-method seed averaging before differencing.

These are DESCRIPTIVE per-condition intervals. They are not adjusted for the four conditions
and they are not additional confirmatory tests; only D21 and D25 carry the Bonferroni
allowance, and only at the family level.
"""
from __future__ import annotations

import json

import numpy as np

import pathb_common as PB
import pathb6_analysis as A

RES = "results"
CONTRASTS = (("M2", "M1"), ("M2", "M0"), ("M2", "M5"), ("M3", "M2"),
             ("M2", "Mmotion"), ("M2", "Roff"))


def cell(by, a, b, family, cond, rng, n_boot=A.N_BOOT):
    """One (contrast, family, condition) cell: paired scenario differences of within-method
    seed means, resampled jointly over scenarios and training seeds."""
    items, sa, sb = [], set(), set()
    for (m, f, c, es), va in by.items():
        if m != a or f != family or c != cond:
            continue
        kb = (b, f, c, es)
        if kb in by:
            items.append((va, by[kb]))
            sa |= set(va)
            sb |= set(by[kb])
    if not items:
        return None
    sa, sb = sorted(sa, key=str), sorted(sb, key=str)
    joint = ((a, b) in A.JOINT_SEED_PAIRS or (b, a) in A.JOINT_SEED_PAIRS)
    pt = float(np.mean([np.mean(list(x.values())) - np.mean(list(y.values()))
                        for x, y in items]))
    st = np.empty(n_boot)
    for i in range(n_boot):
        pa = [sa[j] for j in rng.integers(0, len(sa), len(sa))]
        pb = ([sb[sa.index(s)] for s in pa] if joint and len(sa) == len(sb)
              else [sb[j] for j in rng.integers(0, len(sb), len(sb))])
        pick = rng.integers(0, len(items), len(items))
        st[i] = np.mean([np.mean([items[j][0][s] for s in pa if s in items[j][0]])
                         - np.mean([items[j][1][s] for s in pb if s in items[j][1]])
                         for j in pick])
    lo, hi = np.nanpercentile(st, A.PCTL_95)
    return {"mean": pt, "ci95": [float(lo), float(hi)], "n_scenarios": len(items),
            "excludes_zero": bool(not (lo <= 0 <= hi))}


def main():
    import sys
    sfx = "_Rcorrected" if "--corrected" in sys.argv else ""
    art, rows = A.load_rows(sfx)
    by = A.seed_means(rows, "post_onset_rmse")
    rng = np.random.default_rng(A.ANALYSIS_SEED)

    out = {"stage": "pathb8_paper_tables" + sfx,
           "operating_radius_mode": art.get("operating_radius_mode"),
           "analysis_seed": A.ANALYSIS_SEED, "n_boot": A.N_BOOT,
           "scope": ("descriptive per-condition intervals, unadjusted for the four "
                     "conditions; only the family-level D21 and D25 carry the "
                     "Bonferroni allowance"),
           "cells": {}}

    for family in PB.FAMILIES:
        print(f"\n{'='*78}\n{family}\n{'='*78}")
        hdr = f"{'condition':11s}" + "".join(f"{a+'-'+b:>26s}" for a, b in CONTRASTS)
        print(hdr)
        for cond in PB.CONDITIONS:
            line = f"{cond:11s}"
            for a, b in CONTRASTS:
                r = cell(by, a, b, family, cond, rng)
                if r is None:
                    line += f"{'--':>26s}"
                    continue
                out["cells"][f"{a}-{b}|{family}|{cond}"] = r
                star = "*" if r["excludes_zero"] else " "
                line += (f"{r['mean']:+8.4f} [{r['ci95'][0]:+7.4f},"
                         f"{r['ci95'][1]:+7.4f}]{star}")
            print(line)

    with open(f"{RES}/pathb8_paper_tables{sfx}.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\nwrote {RES}/pathb8_paper_tables{sfx}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

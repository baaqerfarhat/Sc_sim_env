"""Path B Priority 4: complete the five-seed target and train the modality ablation.

Sec 11.1 training budget, assuming archived checkpoint provenance passes (it does; see
`pathb0_freeze.py` gate 3.1c):

    M1 (const)      add seeds 3, 4                 2 jobs
    M2 (no_impact)  add seeds 3, 4                 2 jobs
    M3 (full)       add seeds 3, 4                 2 jobs
    M-motion        train seeds 0-4                5 jobs
                                                  --------
                                                  11 jobs

M4 reuses each M3 checkpoint and R-off-clean reuses each M2 checkpoint, so neither is
trained. M0 and M5 require no training.

Sec 4.1 RNG POLICY.  Each method gets its own training stream and the seed is the ONLY
thing that varies within a method. `train_one` derives three independent substreams from
the seed via SeedSequence.spawn, so the behavioural-pair sampler cannot perturb minibatch
order in the arm that does not use it - which is what previously made `full` and
`no_impact` not the matched pair they were reported to be. M3 and M2 at the same seed
therefore share initialisation and data order by construction, which is what lets the
Sec 9.3 analysis resample that contrast as a matched pair.

Everything else - dataset, splits, normalisation, optimiser budget, batch size, epochs,
learning rate and the dev-prediction checkpoint rule - is identical across every job and
identical to the archived seeds 0-2.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

import stage5_data_train as s5
from scsim import config as C

DATA, RES = "data", "results"

# (checkpoint tag, seeds, lambda_i source, constant_context, feat_mask)
JOBS = [
    ("const", (3, 4), "zero", True, "full"),
    ("no_impact", (3, 4), "zero", False, "full"),
    ("full", (3, 4), "ablation", False, "full"),
    ("motion", (0, 1, 2, 3, 4), "zero", False, "motion_command_only"),
]


def main():
    t0 = time.time()
    print("=" * 78)
    print("PATH B  Priority 4: five-seed completion and the modality ablation")
    print("=" * 78)

    # the behavioural weight actually used by `full`, taken from the archived Stage 5
    # selection so the new seeds are trained at the SAME weight as seeds 0-2
    with open(f"{RES}/stage5_training.json") as f:
        s5art = json.load(f)
    lam_full = float(s5art["lambda_full_used"])
    lam_selected = float(s5art["lambda_grid"]["selected"])
    print(f"\ndevelopment-selected lambda_I = {lam_selected:g}  "
          f"(so M2 is the SELECTED method)")
    print(f"ablation weight used by M3     = {lam_full:g}  "
          f"(unchanged from archived seeds 0-2)")

    # ---- dataset: reuse the cached corpus, unchanged ----
    meta_path = os.path.join(DATA, "episodes_meta.json")
    if not os.path.exists(meta_path):
        print("\nERROR: no cached dataset. Run stage5_data_train.py first.")
        return 1
    blob = np.load(os.path.join(DATA, "episodes.npz"), allow_pickle=True)
    episodes = list(blob["episodes"])
    with open(meta_path) as f:
        dmeta = json.load(f)
    print(f"\nreusing the frozen corpus: {len(episodes)} parent episodes, "
          f"manifest {dmeta.get('manifest_hash')}")

    ds = {}
    for split in s5.SPLIT_SIZES:
        eps = [e for e in episodes if e["split"] == split]
        ds[split] = s5.build_windows(eps)
    print(f"  train {len(ds['train']['feats'])} windows, "
          f"dev {len(ds['dev']['feats'])} windows  "
          f"(identical to the archived seeds)")

    q_all = np.array([p["q"] for e in episodes if e["split"] == "train"
                      for p in e["probes"] if p["ok"]])
    q_mu, q_sd = q_all.mean(0), q_all.std(0) + 1e-8

    # ---- run the jobs ----
    runs, n = {}, 0
    total = sum(len(s) for _, s, _, _, _ in JOBS)
    for tag, seeds, lam_kind, const_ctx, fmask in JOBS:
        lam = lam_full if lam_kind == "ablation" else 0.0
        for seed in seeds:
            n += 1
            name = f"{tag}_s{seed}"
            path = os.path.join(DATA, f"model_{name}.pt")
            if os.path.exists(path):
                print(f"\n[{n}/{total}] {name}: checkpoint already present, skipping")
                continue
            print(f"\n[{n}/{total}] --- training {name}  (lambda_I={lam:g}, "
                  f"constant_context={const_ctx}, feat_mask={fmask}) ---")
            out = s5.train_one(ds, q_mu, q_sd, seed=seed, lambda_i=lam, tag=name,
                               constant_context=const_ctx, feat_mask=fmask)
            runs[name] = out

    # ---- inventory every checkpoint the prospective test will use ----
    import hashlib
    inventory = {}
    for tag in ("const", "no_impact", "full", "motion"):
        for seed in range(5):
            p = os.path.join(DATA, f"model_{tag}_s{seed}.pt")
            if not os.path.exists(p):
                inventory[f"{tag}_s{seed}"] = None
                continue
            with open(p, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
            import torch
            ck = torch.load(p, map_location="cpu", weights_only=False)
            inventory[f"{tag}_s{seed}"] = {
                "sha256": sha, "lambda_i": float(ck.get("lambda_i", 0.0)),
                "constant_context": bool(ck.get("constant_context", False)),
                "feat_mask": ck.get("feat_mask", "full"),
                "best_epoch": ck.get("best_epoch"), "dev_l1": ck.get("dev_l1"),
                "archived": f"{tag}_s{seed}" not in runs}

    print("\n" + "=" * 78)
    print("CHECKPOINT INVENTORY (Sec 15: frozen before the test manifest is opened)")
    print("=" * 78)
    print(f"  {'checkpoint':16s} {'lam_I':>7s} {'mask':>20s} {'dev_L1':>10s} "
          f"{'ep':>3s} {'origin':>9s}  sha256")
    missing = []
    for k, v in inventory.items():
        if v is None:
            missing.append(k)
            print(f"  {k:16s} {'':>7s} {'MISSING':>20s}")
            continue
        print(f"  {k:16s} {v['lambda_i']:7.2f} {v['feat_mask']:>20s} "
              f"{v['dev_l1']:10.6f} {str(v['best_epoch']):>3s} "
              f"{'archived' if v['archived'] else 'new':>9s}  {v['sha256'][:16]}")

    # ---- seed-level dev prediction, so training variability is visible ----
    print("\ndev one-step weighted MSE by method and seed "
          "(Sec 9.3: five seeds do not guarantee a narrow interval)")
    print(f"  {'method':12s} " + "".join(f"{'s' + str(s):>11s}" for s in range(5))
          + f"{'mean':>11s}{'sd':>10s}")
    seed_tab = {}
    for tag, mid in (("const", "M1"), ("no_impact", "M2"), ("full", "M3"),
                     ("motion", "Mmotion")):
        v = [inventory.get(f"{tag}_s{s}") for s in range(5)]
        d = [np.nan if x is None else x["dev_l1"] for x in v]
        seed_tab[mid] = d
        arr = np.asarray(d, dtype=float)
        print(f"  {mid:12s} " + "".join(f"{x:11.6f}" for x in d)
              + f"{np.nanmean(arr):11.6f}{np.nanstd(arr, ddof=1):10.6f}")

    out = {"stage": "pathb3_train", "jobs_run": sorted(runs),
           "n_new_jobs": len(runs), "n_planned_jobs": total,
           "lambda_full_used": lam_full, "lambda_selected_on_dev": lam_selected,
           "inventory": inventory, "missing": missing,
           "dev_l1_by_seed": seed_tab,
           "dataset": {"n_parent_episodes": len(episodes),
                       "manifest_hash": dmeta.get("manifest_hash"),
                       "train_windows": int(len(ds["train"]["feats"])),
                       "dev_windows": int(len(ds["dev"]["feats"]))},
           "rng_policy": ("one training stream per job, three independent substreams "
                          "from SeedSequence(seed).spawn(3) for minibatch order, "
                          "multistep sampling and behavioural pairs; M3 and M2 at the "
                          "same seed share initialisation and data order by "
                          "construction"),
           "identical_across_jobs": ["dataset", "splits", "signature normalisation",
                                     "optimiser", "batch size", "epochs",
                                     "learning rate", "checkpoint selection rule"],
           "runs": runs, "wall_time_s": time.time() - t0}
    with open(f"{RES}/pathb3_train.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\nwrote {RES}/pathb3_train.json "
          f"({out['wall_time_s'] / 60:.1f} min, {len(runs)} new jobs)")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

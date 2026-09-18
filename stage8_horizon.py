"""Stage 8: the horizon axis, and the model-level metrics of protocol Sec 9.1.

The certificate of Stage 7 is a one-step contraction under the gain K, so the MPC
horizon N does not appear in it algebraically. Sec 12 nonetheless lists N as a sweep
axis, because N "determines achievable per-solve correction" - that is an OPERATIONAL
statement, and the operational question it maps onto is:

    at horizon N, how often can the transmitted command satisfy the one-step decrease
    condition of Eq. (18), and what does the resulting closed loop cost?

So N is swept in closed loop and reported through the acceptance rate, the observed
one-step slack distribution and the tracking error. This is measured, not asserted.

Also computed here, because both are model-level rather than episode-level:

  prediction error   one-step body-frame prediction on COMMON held-out estimated
                     state sequences, with the fixed training-derived scaling.
  retrieval error    cross-reference behavioural distance for latent neighbours: for
                     each probe anchor, find its nearest neighbour in latent space
                     among anchors from OTHER episodes and report the behavioural
                     signature distance actually incurred. A representation that has
                     learned behaviour-relevant structure retrieves neighbours whose
                     behaviour matches; one that has not retrieves at chance.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from scsim import config as C
from scsim import reference as R
from scsim import scenarios as S
from scsim.parallel import pmap

import stage6_methods as s6

RES = "results"
os.makedirs(RES, exist_ok=True)

# 10 is the manuscript's stated horizon and 12 is the build spec's; the discrepancy
# is unresolved, so both are swept and reported rather than one being assumed. The
# longer values probe whether more preview would help at all.
HORIZONS = tuple(sorted(set(C.N_HORIZON_CANDIDATES) | {20, 30, 40, 50}))
N_EP_PER_CELL = 24


# --------------------------------------------------------------------------
def _horizon_job(args):
    method, N, cond, ep_seed, cert, tol = args
    rng = S.scenario_rng(cond, ep_seed)
    sc = S.make_condition(cond, rng)
    from scsim.runner import run_policy_episode
    pol = s6.make_policy(method, 0, cert, N=N)
    t0 = time.time()
    log = run_policy_episode(pol, seed=ep_seed, steps=C.EPISODE_STEPS, scenario=sc)
    m = s6.episode_metrics(log, sc, tol)
    a = log.arrays()
    sl = np.asarray(a["slack_cmd"], dtype=float)
    sl = sl[np.isfinite(sl)]
    acc = np.asarray(a["accepted"], dtype=bool)
    m.update({"method": method, "N": N, "condition": cond, "ep_seed": ep_seed,
              "frac_accepted": float(acc.mean()) if acc.size else np.nan,
              "slack_p05": float(np.percentile(sl, 5)) if sl.size else np.nan,
              "slack_median": float(np.median(sl)) if sl.size else np.nan,
              "frac_slack_neg": float((sl < 0).mean()) if sl.size else np.nan,
              "wall_s_per_step": (time.time() - t0) / C.EPISODE_STEPS})
    return m


def horizon_sweep(cert, tol, workers=8):
    print("\n" + "=" * 78)
    print("HORIZON AXIS  (closed loop; N does not enter the certificate algebraically)")
    print("=" * 78)
    jobs = []
    for N in HORIZONS:
        for cond in ("healthy", "combined"):
            for i in range(N_EP_PER_CELL):
                jobs.append(("full", N, cond, 30_000 + i, cert, tol))
    rows = pmap(_horizon_job, jobs, desc="  horizon", workers=workers)

    hdr = (f"{'cond':10s} {'N':>3s} {'RMSE (m)':>15s} {'peak (m)':>9s} "
           f"{'accept':>8s} {'reject':>8s} {'slack<0':>8s} {'ms/step':>8s}")
    print(hdr)
    print("-" * len(hdr))
    table = {}
    for cond in ("healthy", "combined"):
        for N in HORIZONS:
            sub = [r for r in rows if r["N"] == N and r["condition"] == cond]
            rm = s6.agg([r["rmse_pos"] for r in sub])
            pk = s6.agg([r["peak_pos"] for r in sub])
            ac = s6.agg([r["frac_accepted"] for r in sub])
            rj = s6.agg([r["frac_reject"] for r in sub])
            sn = s6.agg([r["frac_slack_neg"] for r in sub])
            ms = s6.agg([r["wall_s_per_step"] * 1e3 for r in sub])
            table[f"{cond}|{N}"] = {"rmse_pos": rm, "peak_pos": pk,
                                    "frac_accepted": ac, "frac_reject": rj,
                                    "frac_slack_neg": sn, "ms_per_step": ms}
            print(f"{cond:10s} {N:3d} {rm['mean']:7.3f}+-{rm['sd']:<6.3f} "
                  f"{pk['median']:9.3f} {ac['mean']:8.4f} {rj['mean']:8.4f} "
                  f"{sn['mean']:8.4f} {ms['mean']:8.2f}")
        print()

    # The deployed horizon is DISPUTED: the build spec says 12, the manuscript says
    # 10, and neither has been checked against the flight configuration for the
    # reported logs. Rather than assume one, compare them directly on matched scenario
    # draws so the discrepancy becomes a reported robustness axis. If the paired
    # difference is small relative to the effects being claimed, no conclusion in the
    # paper depends on resolving it.
    n_a, n_b = C.N_HORIZON_MANUSCRIPT, C.N_HORIZON_HW
    horizon_pair = {}
    print(f"--- horizon robustness: N={n_a} (manuscript) vs N={n_b} (build spec), "
          f"matched draws")
    for cond in ("healthy", "combined"):
        pa = {r["ep_seed"]: r for r in rows if r["N"] == n_a
              and r["condition"] == cond}
        pb = {r["ep_seed"]: r for r in rows if r["N"] == n_b
              and r["condition"] == cond}
        common = sorted(set(pa) & set(pb))
        if not common:
            continue
        d = np.array([pa[s]["rmse_pos"] - pb[s]["rmse_pos"] for s in common])
        rng_b = np.random.default_rng(1234)
        bs = np.array([np.mean(rng_b.choice(d, d.size, replace=True))
                       for _ in range(4000)])
        lo, hi = np.percentile(bs, [2.5, 97.5])
        horizon_pair[cond] = {"mean": float(d.mean()), "lo": float(lo),
                              "hi": float(hi), "n_pairs": len(common),
                              "N_a": n_a, "N_b": n_b,
                              "significant": bool(hi < 0 or lo > 0)}
        print(f"  {cond:10s} dRMSE(N={n_a} - N={n_b}) = {d.mean():+.4f} m "
              f"[{lo:+.4f}, {hi:+.4f}]  n={len(common)}  "
              f"{'SIGNIFICANT' if (hi < 0 or lo > 0) else 'not significant'}")
    print()

    return {"table": table, "rows": rows,
            "horizon_pair": horizon_pair,
            "disputed_horizon": {
                "manuscript": n_a, "build_spec": n_b,
                "status": "unresolved; not checked against the flight configuration "
                          "attached to the reported hardware logs, so both are "
                          "reported"},
            "note": "N is swept in closed loop because the certificate is a one-step "
                    "contraction under K and does not contain N. Acceptance rate is "
                    "the operational reading of 'achievable per-solve correction'."}


# --------------------------------------------------------------------------
def _ood_job(args):
    """One out-of-distribution stress episode."""
    method, model_seed, cond, ep_seed, cert, tol, stress_kind = args
    rng = S.scenario_rng(cond, ep_seed, stress_kind)
    if stress_kind == "mismatch":
        # +/-15% plant mismatch against the +/-10% of the training population: a
        # factor of 1.5, NOT double, which an earlier writeup claimed
        sc = S.make_condition(cond, rng, stress=True)
    elif stress_kind == "transfer_ref":
        # A genuinely held-out reference family. `smooth` can no longer serve here:
        # it is now part of the training mixture, and a family used in training
        # cannot also be presented as unseen.
        sc = S.make_condition(cond, rng, reference=R.TRANSFER_FAMILY)
    else:
        raise ValueError(stress_kind)
    from scsim.runner import run_policy_episode
    pol = s6.make_policy(method, model_seed, cert, N=C.N_HORIZON_HW)
    log = run_policy_episode(pol, seed=ep_seed, steps=C.EPISODE_STEPS, scenario=sc)
    m = s6.episode_metrics(log, sc, tol)
    m.update({"method": method, "model_seed": model_seed, "condition": cond,
              "ep_seed": ep_seed, "stress": stress_kind})
    return m


def ood_sweep(cert, tol, workers=12, n_ep=40):
    """Does behavioural supervision buy GENERALISATION?

    The in-distribution comparison in Stage 6 is not the axis the behavioural loss is
    designed for: shaping the latent so behaviourally similar situations are close is a
    claim about transfer, not about fitting the training population. Two stress
    families are used, both outside what training saw:

      mismatch    +/-15% mass and inertia, vs the +/-10% of the training draws
      transfer_ref  the held-out `transfer` reference family, excluded from training

    Cells are labelled stress, as the protocol requires; they are not pooled with the
    calibrated population.
    """
    print("\n" + "=" * 78)
    print("OUT-OF-DISTRIBUTION STRESS  (labelled separately, never pooled)")
    print("=" * 78)
    methods = ("zero_context", "constant_context", "no_impact", "full")
    jobs = []
    for kind in ("mismatch", "transfer_ref"):
        for cond in ("actuator", "combined"):
            for i in range(n_ep):
                for meth in methods:
                    for ms in (s6.MODEL_SEEDS if meth in ("full", "no_impact")
                               else (0,)):
                        jobs.append((meth, ms, cond, 50_000 + i, cert, tol, kind))
    rows = pmap(_ood_job, jobs, desc="  ood", workers=workers)

    table, eff = {}, {}
    hdr = (f"{'stress':11s} {'cond':10s} {'method':17s} {'RMSE (m)':>15s} "
           f"{'peak (m)':>9s} {'succ':>9s}")
    print(hdr)
    print("-" * len(hdr))
    for kind in ("mismatch", "transfer_ref"):
        for cond in ("actuator", "combined"):
            for meth in methods:
                sub = [r for r in rows if r["stress"] == kind
                       and r["condition"] == cond and r["method"] == meth]
                if not sub:
                    continue
                rm = s6.agg([r["rmse_pos"] for r in sub])
                pk = s6.agg([r["peak_pos"] for r in sub])
                att = [r for r in sub if r["attempted"]]
                ns = sum(1 for r in att if r["success"])
                table[f"{kind}|{cond}|{meth}"] = {
                    "rmse_pos": rm, "peak_pos": pk, "n_success": ns,
                    "n_attempted": len(att)}
                print(f"{kind:11s} {cond:10s} {meth:17s} "
                      f"{rm['mean']:7.3f}+-{rm['sd']:<6.3f} {pk['median']:9.3f} "
                      f"{ns:4d}/{len(att):<4d}")
            # paired full - no_impact on this stress cell
            ra = [r for r in rows if r["stress"] == kind and r["condition"] == cond
                  and r["method"] == "full"]
            rb = [r for r in rows if r["stress"] == kind and r["condition"] == cond
                  and r["method"] == "no_impact"]
            st = s6.block_bootstrap_paired(ra, rb, "rmse_pos")
            if st:
                eff[f"{kind}|{cond}"] = st
                sig = "" if (st["lo"] <= 0 <= st["hi"]) else "  *"
                print(f"{'':11s} {'':10s} {'full - no_impact':17s} "
                      f"{st['mean']:+7.4f} [{st['lo']:+.4f}, {st['hi']:+.4f}]{sig}")
            print()
    return {"table": table, "paired_full_minus_no_impact": eff, "rows": rows,
            "n_ep": n_ep,
            "note": "stress cells: +/-15% mismatch and an unseen reference family. "
                    "Labelled separately from the calibrated population."}


def model_level_metrics():
    """Prediction error and retrieval error for every trained representation."""
    import torch
    from scsim.context import ContextModel, probe_signature, signature_distance
    import stage5_data_train as s5

    print("\n" + "=" * 78)
    print("MODEL-LEVEL METRICS  (common held-out sequences, fixed scaling)")
    print("=" * 78)

    eps = np.load("data/episodes.npz", allow_pickle=True)["episodes"]
    sn = np.load("data/sig_norm.npz")
    q_mu, q_sd = sn["mu"], sn["sd"]

    # the COMMON held-out set: windows built from the TEST-split episodes only,
    # identical for every model. build_windows is flat, so the split filter has
    # to happen on the episode list before the call.
    te = s5.build_windows([e for e in eps if e["split"] == "test"])
    F = torch.tensor(te["feats"])
    M = torch.tensor(te["masks"])
    Xb, Ub, D0 = [torch.tensor(t) for t in s5.precompute_body(te)]
    TGT = torch.tensor(s5.body_target_all(te))
    Wx = torch.tensor([1.0, 1.0, 0.5, 0.5, 1.0, 0.3], dtype=torch.float32)
    print(f"  common held-out windows: {len(F)}")

    out = {}
    anchors = None      # resolved once; identical for every model
    hdr = (f"{'model':18s} {'pred err (scaled)':>19s} {'retrieval err':>15s} "
           f"{'chance':>9s} {'ratio':>7s}")
    print(hdr)
    print("-" * len(hdr))
    for tag in ("full", "no_impact", "const"):
        for seed in (0, 1, 2):
            path = f"data/model_{tag}_s{seed}.pt"
            if not os.path.exists(path):
                continue
            ck = torch.load(path, map_location="cpu", weights_only=False)
            mdl = ContextModel(constant_context=ck.get("constant_context", False))
            mdl.load_state_dict(ck["model"])
            mdl.eval()
            with torch.no_grad():
                # a constant-context checkpoint returns a view of an nn.Parameter,
                # which stays attached even under no_grad, so detach explicitly
                z = mdl.encode(F, M).detach()
                pred = D0 + mdl.residual(Xb, Ub, z)
                perr = float((((pred - TGT) * Wx) ** 2).mean())

            # ---- retrieval: nearest latent neighbour from a DIFFERENT episode ----
            # a probe anchor and a history window are DIFFERENT index spaces, so
            # each anchor is resolved to its co-located window before the latents
            # and the signatures can be compared row by row.
            zz = z.numpy()
            ret, chance = np.nan, np.nan
            if anchors is None:
                anchors = [(w, key[0], key[2], key[3], key[4])
                           for key in te["sig_keys"]
                           for w in [s5._sig_window(te, key)]
                           if w is not None]
            # Sec 5.4: a constant-context checkpoint has IDENTICAL latents for every
            # window, so "nearest neighbour" is decided by floating-point tie-breaking
            # and carries no behavioural information. Reporting the resulting number
            # invites the reader to compare it with the others as though it meant
            # something. It is n/a, and the reason is recorded.
            is_const = bool(ck.get("constant_context", False))
            z_spread = float(np.std(zz, axis=0).max())
            if is_const or z_spread < 1e-9:
                out[f"{tag}_s{seed}"] = {
                    "pred_err": perr, "retrieval_err": None, "chance": None,
                    "ratio": None, "cross_ref_ratio": None,
                    "note": "retrieval n/a: latents are constant across windows "
                            f"(max per-dim spread {z_spread:.2e}), so any ranking is "
                            "arbitrary tie-breaking, not behavioural information"}
                print(f"{tag + '_s' + str(seed):18s} {perr:19.6f} "
                      f"{'n/a':>15s} {'n/a':>9s} {'n/a':>7s}")
                continue
            cross_ratio = np.nan
            if len(anchors) > 10:
                sel = np.arange(min(len(anchors), 1500))
                Z = zz[[anchors[i][0] for i in sel]]
                E = np.array([anchors[i][1] for i in sel])
                Q = [anchors[i][2] for i in sel]
                G = np.array([anchors[i][3] for i in sel])     # probe group
                FAM = np.array([anchors[i][4] for i in sel])   # reference family
                d2 = ((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1)
                # Sec 5.4: candidates must come from a DIFFERENT parent episode AND
                # the SAME matched probe group. Without the group restriction a
                # neighbour can be "retrieved" simply for starting at the same state.
                elig = (E[:, None] != E[None, :]) & (G[:, None] == G[None, :])
                d2 = np.where(elig, d2, np.inf)
                nn = d2.argmin(1)
                ok = np.isfinite(d2[np.arange(len(sel)), nn])
                ret = float(np.mean([signature_distance(Q[i], Q[nn[i]], q_mu, q_sd)
                                     for i in np.where(ok)[0]]))
                # random-neighbour baseline drawn from the SAME eligible pool
                rng = np.random.default_rng(0)
                ch_vals = []
                for i in np.where(ok)[0]:
                    pool = np.flatnonzero(elig[i])
                    if len(pool):
                        j = int(pool[rng.integers(0, len(pool))])
                        ch_vals.append(signature_distance(Q[i], Q[j], q_mu, q_sd))
                chance = float(np.mean(ch_vals)) if ch_vals else np.nan
                # cross-reference retrieval, reported separately where claimed
                cr, cc = [], []
                for i in np.where(ok)[0]:
                    pool = np.flatnonzero(elig[i] & (FAM != FAM[i]))
                    if not len(pool):
                        continue
                    j = int(pool[np.argmin(d2[i, pool])])
                    cr.append(signature_distance(Q[i], Q[j], q_mu, q_sd))
                    jr = int(pool[rng.integers(0, len(pool))])
                    cc.append(signature_distance(Q[i], Q[jr], q_mu, q_sd))
                if cr and np.mean(cc) > 0:
                    cross_ratio = float(np.mean(cr) / np.mean(cc))
            out[f"{tag}_s{seed}"] = {
                "pred_err": perr, "retrieval_err": ret, "chance": chance,
                "ratio": (ret / chance) if chance else None,
                "cross_ref_ratio": (None if not np.isfinite(cross_ratio)
                                    else cross_ratio),
                "n_neighbors": 1,
                "candidate_pool": "different parent episode, same matched probe group",
                "pred_err_units": "weighted MSE, mixed state units, NOT RMSE"}
            print(f"{tag + '_s' + str(seed):18s} {perr:19.6f} {ret:15.4f} "
                  f"{chance:9.4f} {ret / chance if chance else float('nan'):7.3f}")
    return out


def main():
    t0 = time.time()
    print("=" * 78)
    print("STAGE 8  horizon axis and model-level metrics")
    print("=" * 78)

    with open(f"{RES}/stage6_methods.json") as f:
        s6res = json.load(f)
    tol = s6res["recovery_tolerance_m"]
    cert = s6.certificate_design()
    cert.update(eta=s6res["supervision_design"]["eta"],
                R=s6res["supervision_design"]["R"])
    print(f"\nreusing the FROZEN Stage 6 supervision design: "
          f"eta={cert['eta']:.4f}  R={cert['R']:.3f}  tol={tol:.3f} m")

    hz = horizon_sweep(cert, tol)
    ood = ood_sweep(cert, tol)
    ml = model_level_metrics()

    out = {"horizon": {k: v for k, v in hz.items() if k != "rows"},
           "horizon_rows": hz["rows"],
           "ood": {k: v for k, v in ood.items() if k != "rows"},
           "ood_rows": ood["rows"], "model_level": ml,
           "frozen_from_stage6": {"eta": cert["eta"], "R": cert["R"], "tol": tol},
           "wall_time_s": time.time() - t0,
           "manifest_hash": C.manifest_hash()}
    with open(f"{RES}/stage8_horizon.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote {RES}/stage8_horizon.json ({out['wall_time_s'] / 60:.1f} min)")


if __name__ == "__main__":
    main()

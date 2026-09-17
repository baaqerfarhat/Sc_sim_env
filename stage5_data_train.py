"""Stage 5: data generation, probe branches, and representation training.

Five splits, split by PARENT EPISODE before any windowing or branching, so no window
or probe branch can straddle a split (Simulation_Validation_Protocol Phase D):

  train      normalisers, probe signatures, network fitting
  dev        hyperparameters, budgets, domains, controller decisions
  fitting    context cells and Mahalanobis score means/covariances
  calibration episode-max conformal thresholds + the one-time acceptance test
  test       the declared metrics under the frozen design

Three training seeds. The full model and the no-behavioural-loss ablation share
initial weights, data, optimiser budget and checkpoint rule; the ONLY intentional
difference is lambda_I.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np
import torch

from scsim import config as C
from scsim import scenarios as S
from scsim.context import (ContextModel, probe_signature, set_seed,
                           signature_distance, SIG_COMPONENT_WEIGHTS)
from scsim.mpc import HardwareMPC
from scsim.parallel import pmap
from scsim.runner import run_episode
from scsim.scenarios import (FEATURE_SCALE, N_FEAT_PER_STEP, build_history,
                             to_body_frame)

DATA = "data"
os.makedirs(DATA, exist_ok=True)
os.makedirs("results", exist_ok=True)

# episodes per split, per condition
SPLIT_SIZES = {"train": 40, "dev": 10, "fitting": 12, "calibration": 12, "test": 16}
PROBE_STEPS = 60          # 6 s probe branch
PROBE_EVERY = 40          # candidate probe anchors within an episode
EXPLORE_STD = 0.35        # behaviour-policy exploration on the proposed wrench


# ==========================================================================
# behaviour policy: the deployed MPC plus bounded exploration
# ==========================================================================
def collect_one(job):
    """Run one parent episode and its probe branches."""
    ep_id, split, condition, seed = job
    rng = np.random.default_rng(seed)
    sc = S.make_condition(condition, rng, reference="step")

    log = run_episode(seed=seed, steps=C.EPISODE_STEPS, estimator_on=True,
                      controller=HardwareMPC(mass=C.MASS, jzz=C.JZZ),
                      **sc.run_kwargs())
    a = log.arrays()

    # ---- probe branches ----
    # A separate simulator branch retains the persistent impairment, resets to a
    # matched anchor, and runs a prescribed exciting command sequence. Probe
    # measurements and future outcomes are TRAINING TARGETS ONLY; the encoder never
    # sees them. Branches inherit the parent's split.
    probes = []
    anchors = list(range(int(sc.onset_step) + C.HISTORY_L + 5,
                         C.EPISODE_STEPS - 5, PROBE_EVERY))
    for ai, k_anchor in enumerate(anchors):
        x_anchor = a["x_true"][k_anchor].copy()
        plog = run_probe_branch(sc, x_anchor, seed=seed * 1000 + ai)
        q, ok, exc = probe_signature(plog)
        if q is not None:
            probes.append({"k": int(k_anchor), "q": q.tolist(),
                           "ok": bool(ok), "exc": float(exc)})

    return {
        "ep_id": ep_id, "split": split, "condition": condition, "seed": seed,
        "scenario": sc.to_dict(),
        "x_true": a["x_true"].astype(np.float32),
        "x_hat": a["x_hat"].astype(np.float32),
        "u_applied": a["u_applied"].astype(np.float32),
        "u_cmd": a["u_cmd"].astype(np.float32),
        "innov": a["innov"].astype(np.float32),
        "pose_valid": a["pose_valid"].astype(np.uint8),
        "ref_score": a["ref_score"].astype(np.float32),
        "accel": a["accel"].astype(np.float32),
        "probes": probes,
    }


def run_probe_branch(sc, x_anchor, seed):
    """A prescribed bounded exciting command sequence, identical in structure for
    every parent condition within the anchor stratum."""
    from scsim import plant as P
    from scsim.estimator import EstimatorStack, VOSurrogate

    rng = np.random.default_rng(seed)
    fault = P.DeterministicFault(sc.fault_fraction, active=sc.fault_active)
    chain = P.CommandChain(fault=fault, duty_ceiling=sc.duty_ceiling,
                           fmax=sc.fmax, fit_offset=sc.fit_offset,
                           eta_smooth=None if sc.eta_smooth is None
                           else np.array(sc.eta_smooth))
    vo = VOSurrogate(rng, mode=sc.perception)
    vo.set_degraded(True)
    est = EstimatorStack()
    est.align(x_anchor)

    x = np.asarray(x_anchor, dtype=float).copy()
    xs, us, iv, pv, rs = [], [], [], [], []
    # fixed excitation: orthogonal wrench dither so the command Gramian is full rank
    for k in range(PROBE_STEPS):
        ph = 2 * np.pi * k / 12.0
        u_star = np.array([2.5 * np.sin(ph), 2.5 * np.cos(ph),
                           0.35 * np.sin(ph / 2.0 + 0.7)])
        obs = vo.observe(x, k)
        est.update(obs, C.TS)
        u_applied, cinfo = chain(u_star, x[4])
        xn = P.plant_step(x, cinfo["dt_on"], x[4],
                          eta_smooth=None if sc.eta_smooth is None
                          else np.array(sc.eta_smooth),
                          mass=sc.mass, jzz=sc.jzz, drag=sc.drag,
                          yaw_damp=sc.yaw_damp)
        xs.append(x.copy())
        us.append(u_applied.copy())
        iv.append(est.innov.copy())
        pv.append(bool(obs.get("valid", True)))
        rs.append(np.concatenate([x_anchor[:2], np.zeros(4)]))
        x = xn
    xs.append(x.copy())
    return {"x_true": np.array(xs), "u_applied": np.array(us),
            "innov": np.array(iv), "pose_valid": np.array(pv),
            "ref_score": np.array(rs + [rs[-1]])}


# ==========================================================================
def main():
    t_start = time.time()
    print("=" * 78)
    print("STAGE 5  data generation, probe branches, representation training")
    print("=" * 78)

    cache = os.path.join(DATA, "episodes.npz")
    meta_path = os.path.join(DATA, "episodes_meta.json")
    if os.path.exists(meta_path):
        print("\nreusing cached dataset")
        with open(meta_path) as f:
            meta = json.load(f)
        blob = np.load(cache, allow_pickle=True)
        episodes = list(blob["episodes"])
    else:
        jobs, ep_id, seed = [], 0, 10_000
        for split, n in SPLIT_SIZES.items():
            for cond in S.MAIN_CONDITIONS:
                for _ in range(n):
                    jobs.append((ep_id, split, cond, seed))
                    ep_id += 1
                    seed += 1
        n_tot = len(jobs)
        print(f"\ncollecting {n_tot} parent episodes "
              f"({len(SPLIT_SIZES)} splits x {len(S.MAIN_CONDITIONS)} conditions)")
        print(f"  + probe branches at up to "
              f"{len(range(180, C.EPISODE_STEPS-5, PROBE_EVERY))} anchors each")
        episodes = pmap(collect_one, jobs, desc="episodes", chunksize=2)
        np.savez_compressed(cache, episodes=np.array(episodes, dtype=object))
        meta = {"n_episodes": n_tot, "split_sizes": SPLIT_SIZES,
                "conditions": list(S.MAIN_CONDITIONS),
                "manifest_hash": C.manifest_hash()}
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

    n_probe = sum(len(e["probes"]) for e in episodes)
    n_ok = sum(sum(1 for p in e["probes"] if p["ok"]) for e in episodes)
    n_trans = sum(len(e["x_hat"]) for e in episodes)
    print(f"\ndataset: {len(episodes)} parent episodes, {n_trans} transitions, "
          f"{n_probe} probe branches ({n_ok} sufficiently excited)")
    print(f"  offline cost of behavioural supervision: {n_probe} extra branches "
          f"x {PROBE_STEPS} steps = {n_probe*PROBE_STEPS} extra transitions")

    # ------------------------------------------------------------------
    # build training tensors
    # ------------------------------------------------------------------
    print("\nbuilding windows (split by parent episode, no leakage)")
    ds = {}
    for split in SPLIT_SIZES:
        eps = [e for e in episodes if e["split"] == split]
        ds[split] = build_windows(eps)
        print(f"  {split:12s} {len(eps):3d} episodes -> "
              f"{len(ds[split]['feats']):6d} windows, "
              f"{len(ds[split]['pairs']):5d} signature pairs")

    # normalisation from TRAINING data only
    tr = ds["train"]
    q_all = np.array([p["q"] for e in episodes if e["split"] == "train"
                      for p in e["probes"] if p["ok"]])
    q_mu, q_sd = q_all.mean(0), q_all.std(0) + 1e-8
    np.savez(os.path.join(DATA, "sig_norm.npz"), mu=q_mu, sd=q_sd)

    results = {"dataset": {"n_episodes": len(episodes), "n_transitions": n_trans,
                           "n_probe_branches": n_probe, "n_probe_excited": n_ok,
                           "probe_extra_transitions": n_probe * PROBE_STEPS},
               "runs": {}}

    # ------------------------------------------------------------------
    # train: full (lambda_I > 0) and ablation (lambda_I = 0), 3 seeds
    # ------------------------------------------------------------------
    for seed in range(C.N_SEEDS):
        for variant, lam_i in (("full", C.LAMBDA_I), ("no_impact", 0.0)):
            tag = f"{variant}_s{seed}"
            print(f"\n--- training {tag}  (lambda_I = {lam_i}) ---")
            out = train_one(ds, q_mu, q_sd, seed=seed, lambda_i=lam_i, tag=tag)
            results["runs"][tag] = out

    # constant-context baseline: one CONSTANT context, residual retrained
    for seed in range(C.N_SEEDS):
        tag = f"const_s{seed}"
        print(f"\n--- training {tag}  (constant context) ---")
        out = train_one(ds, q_mu, q_sd, seed=seed, lambda_i=0.0, tag=tag,
                        constant_context=True)
        results["runs"][tag] = out

    results["wall_time_s"] = time.time() - t_start
    with open("results/stage5_training.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nwrote results/stage5_training.json  "
          f"({results['wall_time_s']/60:.1f} min total)")


# ==========================================================================
def build_windows(eps):
    """One window per (episode, k). Windows inherit the parent episode's split."""
    feats, masks, xh, u, target, ep_idx, ks = [], [], [], [], [], [], []
    pairs = []
    sig_by_ep = {}
    for ei, e in enumerate(eps):
        arrs = {"x_hat": e["x_hat"].astype(float), "u_applied": e["u_applied"].astype(float),
                "pose_valid": e["pose_valid"].astype(bool), "innov": e["innov"].astype(float)}
        T = len(arrs["x_hat"])
        for k in range(C.HISTORY_L, T - 1):
            f, m = build_history(arrs, k)
            feats.append(f / FEATURE_SCALE)
            masks.append(m)
            xh.append(arrs["x_hat"][k])
            u.append(arrs["u_applied"][k])
            target.append(arrs["x_hat"][k + 1])
            ep_idx.append(ei)
            ks.append(k)
        sig_by_ep[ei] = [(p["k"], np.array(p["q"])) for p in e["probes"] if p["ok"]]

    # anchor-matched signature pairs across DIFFERENT parent episodes, including
    # different reference families, to encourage transferable behavioural structure
    rng = np.random.default_rng(0)
    keys = [(ei, k, q) for ei, lst in sig_by_ep.items() for k, q in lst]
    for i in range(len(keys)):
        for _ in range(3):
            j = int(rng.integers(0, len(keys)))
            if keys[j][0] == keys[i][0]:
                continue     # different parent episodes only
            pairs.append((i, j))

    out = {"feats": np.array(feats, dtype=np.float32),
           "masks": np.array(masks, dtype=np.float32),
           "x_hat": np.array(xh, dtype=np.float32),
           "u": np.array(u, dtype=np.float32),
           "target": np.array(target, dtype=np.float32),
           "ep_idx": np.array(ep_idx), "k": np.array(ks),
           "sig_keys": keys, "pairs": pairs, "eps": eps}

    # ---- frozen-context multistep horizons ----
    # T_H holds only impairment-STABLE horizons, i.e. entirely after onset (or
    # entirely before it), so the frozen context is valid across the rollout.
    # T_1 keeps the ordinary onset transitions, so they are not discarded.
    H = C.MULTISTEP_H
    ms_idx, ms_u, ms_x = [], [], []
    for w in range(len(out["k"])):
        ei, k = out["ep_idx"][w], out["k"][w]
        e = eps[ei]
        T = len(e["x_hat"])
        if k + H + 1 >= T:
            continue
        onset = int(e["scenario"]["onset_step"])
        stable = (k >= onset) or (k + H + 1 <= onset)
        if not stable:
            continue
        ms_idx.append(w)
        ms_u.append(e["u_applied"][k:k + H].astype(np.float32))
        ms_x.append(e["x_hat"][k:k + H + 1].astype(np.float32))
    out["multistep"] = {
        "idx": np.array(ms_idx, dtype=np.int64),
        "u": (np.array(ms_u, dtype=np.float32) if ms_u
              else np.zeros((0, H, 3), np.float32)),
        "x": (np.array(ms_x, dtype=np.float32) if ms_x
              else np.zeros((0, H + 1, 6), np.float32)),
    }
    return out


def _sig_window(ds, key):
    """The ordinary history window co-located with a probe anchor."""
    ei, k, q = key
    sel = np.flatnonzero((ds["ep_idx"] == ei) & (ds["k"] == k))
    return int(sel[0]) if len(sel) else None


def train_one(ds, q_mu, q_sd, seed, lambda_i, tag, constant_context=False,
              epochs=8, batch=256, lr=1e-3):
    """Train one representation.

    The optimiser budget, batch size, epoch count, learning rate, initial weights
    (same seed) and checkpoint rule are IDENTICAL across variants. lambda_I is the
    only intentional difference between `full` and `no_impact`.
    """
    set_seed(seed)
    torch.set_num_threads(6)
    model = ContextModel(constant_context=constant_context)
    opt = torch.optim.AdamW(model.trainable(), lr=lr, weight_decay=1e-4)

    tr, dv = ds["train"], ds["dev"]
    F, M = torch.tensor(tr["feats"]), torch.tensor(tr["masks"])
    n = len(F)
    Xb, Ub, D0 = [torch.tensor(t) for t in precompute_body(tr)]
    TGT = torch.tensor(body_target_all(tr))

    # frozen-context multistep tensors, on impairment-stable horizons only
    ms = tr["multistep"]
    ms_idx = torch.tensor(ms["idx"])
    ms_u = torch.tensor(ms["u"])          # (m, H, 3)
    ms_x = torch.tensor(ms["x"])          # (m, H+1, 6) absolute estimates

    # dev tensors for checkpoint selection
    dF, dM = torch.tensor(dv["feats"]), torch.tensor(dv["masks"])
    dXb, dUb, dD0 = [torch.tensor(t) for t in precompute_body(dv)]
    dTGT = torch.tensor(body_target_all(dv))

    # signature pair bookkeeping: map each probe anchor to its ordinary window
    pair_idx, pair_d, pair_w = np.zeros((0, 2), int), np.zeros(0, np.float32), None
    if lambda_i > 0 and len(tr["pairs"]):
        pi_, pd_, pw_ = [], [], []
        wcache = {}
        for i, j in tr["pairs"]:
            for t in (i, j):
                if t not in wcache:
                    wcache[t] = _sig_window(tr, tr["sig_keys"][t])
            wi, wj = wcache[i], wcache[j]
            if wi is None or wj is None:
                continue
            qi, qj = tr["sig_keys"][i][2], tr["sig_keys"][j][2]
            pi_.append((wi, wj))
            pd_.append(signature_distance(qi, qj, q_mu, q_sd))
            # pairs from different conditions act as the cross-reference family term
            ci = tr["eps"][tr["sig_keys"][i][0]]["condition"]
            cj = tr["eps"][tr["sig_keys"][j][0]]["condition"]
            pw_.append(1.0 + (C.LAMBDA_CROSS if ci != cj else 0.0))
        if pi_:
            pair_idx = np.array(pi_)
            pair_d = np.array(pd_, dtype=np.float32)
            pair_w = np.array(pw_, dtype=np.float32)

    Wx = torch.tensor([1.0, 1.0, 0.5, 0.5, 1.0, 0.3], dtype=torch.float32)
    alpha_h = torch.tensor(
        np.ones(C.MULTISTEP_H - 1) / (C.MULTISTEP_H - 1), dtype=torch.float32)

    hist, best = [], None
    rng = np.random.default_rng(seed)
    for ep in range(epochs):
        model.train()
        perm = rng.permutation(n)
        tot = {"l1": 0.0, "lh": 0.0, "imp": 0.0, "nb": 0}
        for b0 in range(0, n, batch):
            idx = perm[b0:b0 + batch]
            ii = torch.tensor(idx)
            z = model.encode(F[ii], M[ii])
            pred = D0[ii] + model.residual(Xb[ii], Ub[ii], z)
            l1 = (((pred - TGT[ii]) * Wx) ** 2).mean()
            loss = l1

            # ---- frozen-context multistep, L_H ----
            l_h = torch.tensor(0.0)
            if len(ms_idx):
                sel = torch.tensor(rng.integers(0, len(ms_idx),
                                                size=min(64, len(ms_idx))))
                wsel = ms_idx[sel]
                zh = model.encode(F[wsel], M[wsel])          # context FROZEN at k
                xcur = ms_x[sel, 0]                          # (b, 6)
                acc = []
                for h in range(C.MULTISTEP_H):
                    xb, ub, d0 = batch_body(xcur, ms_u[sel, h])
                    dres = model.residual(xb, ub, zh)
                    xcur = apply_body_delta(xcur, d0 + dres)
                    if h >= 1:
                        e = xcur - ms_x[sel, h + 1]
                        e = torch.cat([e[:, :4],
                                       wrap_t(e[:, 4:5]), e[:, 5:6]], dim=1)
                        acc.append((((e) * Wx) ** 2).mean())
                if acc:
                    l_h = sum(a * w for a, w in zip(acc, alpha_h))
                    loss = loss + C.LAMBDA_H * l_h

            # ---- behavioural supervision, L_impact ----
            l_imp = torch.tensor(0.0)
            if lambda_i > 0 and len(pair_idx):
                sel = rng.integers(0, len(pair_idx), size=min(128, len(pair_idx)))
                zi = model.encode(F[torch.tensor(pair_idx[sel, 0])],
                                  M[torch.tensor(pair_idx[sel, 0])])
                zj = model.encode(F[torch.tensor(pair_idx[sel, 1])],
                                  M[torch.tensor(pair_idx[sel, 1])])
                dz = torch.norm(zi - zj, dim=-1)
                dq = torch.tensor(pair_d[sel])
                w = torch.tensor(pair_w[sel])
                l_imp = (w * (dz - C.C_Q * dq) ** 2).sum() / w.sum()
                loss = loss + lambda_i * l_imp

            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            tot["l1"] += float(l1) * len(idx)
            tot["lh"] += float(l_h) * len(idx)
            tot["imp"] += float(l_imp) * len(idx)
            tot["nb"] += len(idx)

        # ---- checkpoint selection on DEV one-step prediction (fixed rule) ----
        model.eval()
        with torch.no_grad():
            zd = model.encode(dF, dM)
            pd_ = dD0 + model.residual(dXb, dUb, zd)
            dev_l1 = float((((pd_ - dTGT) * Wx) ** 2).mean())
        hist.append({"epoch": ep, "l1": tot["l1"] / tot["nb"],
                     "lh": tot["lh"] / tot["nb"], "impact": tot["imp"] / tot["nb"],
                     "dev_l1": dev_l1})
        if best is None or dev_l1 < best[0]:
            best = (dev_l1, {k: v.detach().clone()
                             for k, v in model.state_dict().items()}, ep)
        print(f"    epoch {ep}  L1 {hist[-1]['l1']:.6f}  L_H {hist[-1]['lh']:.6f}  "
              f"L_impact {hist[-1]['impact']:.5f}  dev_L1 {dev_l1:.6f}")

    model.load_state_dict(best[1])
    path = os.path.join(DATA, f"model_{tag}.pt")
    torch.save({"model": model.state_dict(), "lambda_i": lambda_i, "seed": seed,
                "constant_context": constant_context, "best_epoch": best[2],
                "dev_l1": best[0]}, path)
    print(f"    selected epoch {best[2]} (dev_L1 {best[0]:.6f}) -> {path}")
    return {"tag": tag, "lambda_i": lambda_i, "seed": seed,
            "constant_context": constant_context, "history": hist,
            "best_epoch": best[2], "dev_l1": best[0], "checkpoint": path}


def wrap_t(a):
    return torch.remainder(a + np.pi, 2 * np.pi) - np.pi


def batch_body(x, u):
    """Body-frame model inputs and the nominal body-frame increment, batched."""
    psi = x[:, 4]
    c, s = torch.cos(psi), torch.sin(psi)
    vx, vy = x[:, 2], x[:, 3]
    xb = torch.stack([c * vx + s * vy, -s * vx + c * vy, x[:, 5]], dim=1)
    ub = torch.stack([c * u[:, 0] + s * u[:, 1],
                      -s * u[:, 0] + c * u[:, 1], u[:, 2]], dim=1)
    # nominal increment (world) then rotated to body
    dt = C.TS
    ax, ay, az = u[:, 0] / C.MASS, u[:, 1] / C.MASS, u[:, 2] / C.JZZ
    dwx = dt * vx + 0.5 * dt * dt * ax
    dwy = dt * vy + 0.5 * dt * dt * ay
    d0 = torch.stack([
        c * dwx + s * dwy, -s * dwx + c * dwy,
        c * (dt * ax) + s * (dt * ay), -s * (dt * ax) + c * (dt * ay),
        dt * x[:, 5], dt * az,
    ], dim=1)
    return xb, ub, d0


def apply_body_delta(x, dbody):
    """Rotate a body-frame increment back to world and add it to the state."""
    psi = x[:, 4]
    c, s = torch.cos(psi), torch.sin(psi)
    dpx = c * dbody[:, 0] - s * dbody[:, 1]
    dpy = s * dbody[:, 0] + c * dbody[:, 1]
    dvx = c * dbody[:, 2] - s * dbody[:, 3]
    dvy = s * dbody[:, 2] + c * dbody[:, 3]
    out = torch.stack([
        x[:, 0] + dpx, x[:, 1] + dpy, x[:, 2] + dvx, x[:, 3] + dvy,
        wrap_t((x[:, 4] + dbody[:, 4]).unsqueeze(1)).squeeze(1),
        x[:, 5] + dbody[:, 5],
    ], dim=1)
    return out


def precompute_body(d):
    """Body-frame model inputs and the nominal one-step prediction, in body frame."""
    from scsim.plant import jetson_nominal_step
    X, U = d["x_hat"].astype(float), d["u"].astype(float)
    n = len(X)
    Xb = np.zeros((n, 3), dtype=np.float32)
    Ub = np.zeros((n, 3), dtype=np.float32)
    D0 = np.zeros((n, 6), dtype=np.float32)
    for i in range(n):
        x, u = X[i], U[i]
        psi = x[4]
        c, s = np.cos(psi), np.sin(psi)
        R = np.array([[c, s], [-s, c]])
        Xb[i] = np.concatenate([R @ x[2:4], [x[5]]])
        Ub[i] = np.concatenate([R @ u[:2], [u[2]]])
        nom = jetson_nominal_step(x, u)
        D0[i] = to_body_frame(x, nom - x)
    return Xb, Ub, D0


def body_target_all(d):
    """Target: the body-frame increment of the next ESTIMATE, for every window."""
    from scsim.plant import wrap_pi
    X = d["x_hat"].astype(float)
    Y = d["target"].astype(float)
    out = np.zeros((len(X), 6), dtype=np.float32)
    for i in range(len(X)):
        dd = Y[i] - X[i]
        dd[4] = wrap_pi(Y[i][4] - X[i][4])
        out[i] = to_body_frame(X[i], dd)
    return out


if __name__ == "__main__":
    main()

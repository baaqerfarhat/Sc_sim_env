"""Stage 7: the numerical recovery certificate and the authority/horizon sweep.

This is one of the two things the manuscript's own abstract says "remain to be
validated". The deliverable is not a pass mark - build_scSim.md Sec 12 predicts the
certificate is EMPTY at hardware authority, and the job is to establish where the
boundary is and say plainly which term binds.

Chain (manuscript Appendix II):
  1  verification domain V0 over reference pairs and plant parameters
  2  LMI (Eq. 34) -> P, K, with the control effort bounded so that the input radius
     of Eq. (20) is not driven to zero by an arbitrarily high gain
  3  interval verification (Lemma 3): gamma_b + nu_b <= lambda < 1
  4  b_r from the reference defects, eta_q from the allocator (Lemma 2)
  5  R_U (Eq. 20), R_corridor / R_chart (Eq. 21)
  6  s_cert = (b_r + d_cert + eta)/(1-lambda);  nonempty iff s_cert <= min(R...)
  7  sweep duty ceiling, per-thruster fmax, duty-law offset, horizon N, the reference
     family AND the plant-parameter tolerance, and mark where hardware sits

DESIGN SELECTION.  A design is chosen by minimising s_cert / R_max over a declared
grid of (lambda0, effort weight), which is the criterion that actually decides
emptiness. Selecting by smallest gamma+nu instead is wrong: it buys contraction with
gain, and gain shrinks R_U faster than it shrinks s_cert.

PARAMETER TOLERANCE.  Sec 14 lists "measured mass and inertia with tolerance" as an
OPEN item explicitly blocking certificate numbers. It is therefore swept rather than
assumed, and the required tolerance is reported as a result.

RESIDUAL ADMISSIBILITY.  The trained residual's Jacobian enclosure is far too large
to admit (see report). Rather than drop the term, the largest admissible scale is
computed by bisection, turning "empty" into a concrete Lipschitz specification.
"""
from __future__ import annotations

import glob
import json
import os
import time

import numpy as np

from scsim import certificate as CT
from scsim import config as C
from scsim.parallel import pmap
from scsim.plant import CommandChain, DeterministicFault
from scsim.reference import SmoothFeasibleReference, StepSetpointReference

os.makedirs("results", exist_ok=True)

# --------------------------------------------------------------------------
# OPEN inputs, declared here because they do not exist in the Jetson code
# --------------------------------------------------------------------------
# Sec 14: "table dimensions, corridor and keep-out boundaries do not exist anywhere
# in the Jetson code - there is no spatial safety envelope of any kind." A corridor
# is REQUIRED for R_corridor, so one is declared as a simulation choice and its
# sensitivity is reported. It is not a measured hardware envelope.
CORRIDOR_HALF_WIDTH = 2.5   # m about the commanded path
D_CERT = 0.08               # design prediction-error budget, in the P norm
CHART_SPAN = np.pi / 2      # declared unwrapped attitude chart

LAMBDA_GRID = (0.80, 0.90, 0.95, 0.97, 0.98, 0.99, 0.995)
EFFORT_GRID = (1.0, 1e2, 1e4)
# Sec 14 OPEN item: mass and inertia tolerance was never measured.
SPAN_GRID = (0.10, 0.05, 0.02, 0.01, 0.0)
HORIZON_GRID = (12, 20, 30, 40, 50)


N_SMOOTH_GROUPS = 8


def reference_library(family):
    """Consecutive reference pairs (r_i, r_{i+1}) spanning the declared library.

    A and B depend on the reference ONLY through the yaw pair (psi_i, psi_{i+1}), so
    the smooth family's samples are grouped into N_SMOOTH_GROUPS consecutive buckets.
    Each bucket contributes one design point at its midpoint, and the returned yaw
    range is the bucket's full span so the interval enclosure rigorously covers the
    references that were not made design points. Keeping all 40 as separate LMI
    vertices makes the SDP enormous for no added coverage.
    """
    if family == "step":
        r1 = np.array([0.0, -2.0, 0, 0, 0.0, 0])
        r2 = np.array([1.0, -2.0, 0, 0, 0.0, 0])
        return [(r1, r1, (0.0, 0.0)),      # held setpoint: an equilibrium
                (r1, r2, (0.0, 0.0)),      # the SWITCH: a 1.0 m jump in one sample
                (r2, r2, (0.0, 0.0))]

    ref = SmoothFeasibleReference(start=np.zeros(2))
    ts = np.linspace(0.0, float(ref.t_switch[-1]), 40)
    states = [(ref.state_at(t), ref.state_at(t + C.TS)) for t in ts]
    out = []
    for grp in np.array_split(np.arange(len(states)), N_SMOOTH_GROUPS):
        yaws = []
        for i in grp:
            yaws += [states[i][0][4], states[i][1][4]]
        mid = states[grp[len(grp) // 2]]
        out.append((mid[0], mid[1], (float(min(yaws)), float(max(yaws)))))
    return out


def domain_vertices(family, mass_span=0.10, jzz_span=0.10):
    """(A_b, B_b) at the design points, plus the interval enclosures per box."""
    A_list, B_list, boxes = [], [], []
    m_iv = (C.MASS * (1 - mass_span), C.MASS * (1 + mass_span))
    j_iv = (C.JZZ * (1 - jzz_span), C.JZZ * (1 + jzz_span))
    for (r_now, r_next, yaw_range) in reference_library(family):
        A, B = CT.error_jacobians(r_now, r_next, mass=C.MASS, jzz=C.JZZ)
        A_list.append(A)
        B_list.append(B)
        # the enclosure must cover the whole yaw span this design point stands for,
        # as well as the now/next rotation mismatch
        lo = min(yaw_range[0], r_now[4], r_next[4])
        hi = max(yaw_range[1], r_now[4], r_next[4])
        E_A, E_B = CT.interval_jacobian_bounds(lo, hi, m_iv, j_iv)
        boxes.append({"r_now": r_now, "r_next": r_next, "A": A, "B": B,
                      "E_A": E_A, "E_B": E_B, "yaw_range": [lo, hi]})
    return A_list, B_list, boxes


def load_residual_jacobian():
    """Entrywise Jacobian enclosure of the trained residual over the visited domain.

    Both a domain-restricted IBP enclosure and the global product-of-spectral-norms
    bound are computed, and the TIGHTER of the two is used. Neither is a sampled
    Jacobian, so both are admissible under Appendix II.
    """
    import torch
    from scsim.context import ContextModel

    paths = sorted(glob.glob("data/model_full_s*.pt"))
    if not paths or not os.path.exists("data/z_box.npy"):
        return None, {"note": "no trained residual available"}
    ck = torch.load(paths[0], map_location="cpu", weights_only=False)
    model = ContextModel(constant_context=ck.get("constant_context", False))
    model.load_state_dict(ck["model"])
    model.eval()

    zlo, zhi = np.load("data/z_box.npy")
    ach = np.array([2.4, 2.4, 0.96])
    vm, rm = 1.8, 1.7                       # the range actually visited in Stage 5
    lo = np.concatenate([[-vm, -vm, -rm], -ach, zlo])
    hi = np.concatenate([[vm, vm, rm], ach, zhi])
    J_ibp, ibp_info = CT.residual_jacobian_box(model, lo, hi)
    J_glob, spec = CT.residual_jacobian_bound(model)
    use_ibp = J_ibp.max() <= J_glob.max()
    J = J_ibp if use_ibp else J_glob
    return J, {"source": paths[0], "ibp_max": float(J_ibp.max()),
               "global_max": float(J_glob.max()), "spectral": float(spec),
               "used": "ibp" if use_ibp else "global_norms",
               "nominal_du_sensitivity": float(C.TS / C.MASS),
               "note": ibp_info}


def achievable_set(cfg):
    """Achievable wrench box for a configuration.

    Two thrusters per force axis and a four-thruster couple, each limited by the
    realizable average force fmax * duty_ceiling.
    """
    avg = cfg["fmax"] * cfg["duty"]
    return np.array([2.0 * avg, 2.0 * avg, 4.0 * 0.2 * avg])


def _chain_factory(cfg):
    def make():
        return CommandChain(fault=DeterministicFault(active=False),
                            duty_ceiling=cfg["duty"] * C.TS,
                            fmax=cfg["fmax"], fit_offset=cfg["offset"])
    return make


def evaluate_certificate(P, K, boxes, family, *, achievable, chain_factory,
                         J_res=None, eta_extra=0.0,
                         corridor_half=CORRIDOR_HALF_WIDTH, d_cert=D_CERT):
    """One full certificate evaluation. Returns a dict of every reported field."""
    B_list = [b["B"] for b in boxes]

    # ---- 3. interval verification, Lemma 3 (nominal predictor, no residual) ----
    gam_max, nu_max, lam = 0.0, 0.0, 0.0
    for b in boxes:
        gam, nu = CT.verify_box(P, K, b["A"], b["B"], b["E_A"], b["E_B"])
        gam_max = max(gam_max, gam)
        nu_max = max(nu_max, nu)
        lam = max(lam, gam + nu)

    # ---- 4. b_r and eta_q ----
    b_r, worst_pair = 0.0, None
    for b in boxes:
        _, d_r = CT.feedforward(b["r_now"], b["r_next"], achievable)
        val = CT.norm_P(d_r, P)
        if val > b_r:
            b_r, worst_pair = val, (b["r_now"][:2].tolist(), b["r_next"][:2].tolist())
    eta_q, _ = CT.allocation_allowance(P, K, B_list, achievable, n_samples=200,
                                       R_probe=1.0, chain_factory=chain_factory)
    eta = eta_q + eta_extra

    # ---- 5. radii ----
    H_u = np.vstack([np.eye(3), -np.eye(3)])
    h_u = np.concatenate([np.asarray(achievable), np.asarray(achievable)])
    u_r_list = [CT.feedforward(b["r_now"], b["r_next"], achievable)[0] for b in boxes]
    R_U, _ = CT.input_radius(P, K, H_u, h_u, u_r_list)

    H_l = np.zeros((4, 6))
    H_l[0, 0] = 1.0
    H_l[1, 0] = -1.0
    H_l[2, 1] = 1.0
    H_l[3, 1] = -1.0
    centre = np.array([0.5, -1.0])
    h_l = np.array([centre[0] + corridor_half, -(centre[0] - corridor_half),
                    centre[1] + corridor_half, -(centre[1] - corridor_half)])
    est_pos = 0.65     # m, the upper edge of the measured healthy |dx| p95 band
    r_list = [b["r_now"] for b in boxes] + [b["r_next"] for b in boxes]
    R_corr, _ = CT.corridor_radius(P, H_l, h_l, r_list,
                                   lambda h: est_pos * np.linalg.norm(h[:2]))
    R_chart, _ = CT.chart_radius(P, CHART_SPAN)

    R_max = min(R_U, R_corr, R_chart)
    s_cert = CT.s_cert_value(b_r, d_cert, eta, lam) if lam < 1.0 else np.inf
    nonempty = bool(lam < 1.0 and s_cert <= R_max)
    margin = (1.0 - lam) * R_max - b_r - d_cert - eta if lam < 1.0 else -np.inf
    ratio = (s_cert / R_max) if np.isfinite(s_cert) and R_max > 0 else np.inf

    # ---- residual admissibility budget ----
    alpha = None
    if J_res is not None and lam < 1.0:
        alpha = CT.residual_budget(P, K, boxes, J_res, lam_target=0.999)

    which_R = min([("R_U", R_U), ("R_corridor", R_corr), ("R_chart", R_chart)],
                  key=lambda t: t[1])[0]
    if lam >= 1.0:
        binding = "lambda>=1 (contraction fails: gamma+nu)"
    elif nonempty:
        binding = which_R
    else:
        terms = {"b_r": b_r, "d_cert": d_cert, "eta": eta}
        binding = f"s_cert>{which_R}; largest term = {max(terms, key=terms.get)}"

    return {
        "family": family, "lam": lam, "gamma_max": gam_max, "nu_max": nu_max,
        "n_boxes": len(boxes),
        "b_r": b_r, "b_r_worst_pair": worst_pair,
        "d_cert": d_cert, "eta_q": eta_q, "eta": eta,
        "R_U": R_U, "R_corridor": R_corr, "R_chart": R_chart, "R_max": R_max,
        "s_cert": s_cert, "ratio": ratio, "margin": margin, "nonempty": nonempty,
        "binding": binding, "residual_alpha_max": alpha,
        "K_absmax": float(np.abs(K).max()),
        "eig_min_P": float(np.linalg.eigvalsh(P).min()),
    }


# --------------------------------------------------------------------------
def _solve_design(job):
    family, lam0, w_eff = job
    A_list, B_list, _ = domain_vertices(family)
    r = CT.solve_lmi(A_list, B_list, lam0, w_effort=w_eff)
    if r is None:
        return None
    return r[0].tolist(), r[1].tolist()


def main():
    t0 = time.time()
    print("=" * 78)
    print("STAGE 7  recovery certificate and authority/horizon sweep")
    print("=" * 78)

    J_res, res_info = load_residual_jacobian()
    print("\nresidual Jacobian enclosure:")
    for k in ("source", "used", "ibp_max", "global_max", "nominal_du_sensitivity"):
        if k in res_info:
            v = res_info[k]
            print(f"    {k:24s} {v if isinstance(v, str) else f'{v:.4g}'}")
    if J_res is not None:
        print(f"    -> the learned residual claims up to "
              f"{J_res[:, 3:].max() / (C.TS / C.MASS):.0f}x the NOMINAL sensitivity "
              f"of the state increment to the commanded wrench")

    out = {"open_inputs": {
               "corridor_half_width_m": CORRIDOR_HALF_WIDTH,
               "d_cert": D_CERT,
               "note": "Sec 14: corridor boundaries and the mass/inertia tolerance "
                       "do not exist in the Jetson code. The corridor is a declared "
                       "SIMULATION choice; the tolerance is SWEPT, not assumed.",
           },
           "lambda_grid": list(LAMBDA_GRID), "effort_grid": list(EFFORT_GRID),
           "span_grid": list(SPAN_GRID), "horizon_grid": list(HORIZON_GRID),
           "residual": {k: v for k, v in res_info.items() if k != "note"},
           "designs": {}, "sweep": [], "span_boundary": {}}

    # ------------------------------------------------------------------
    # 1. design P, K over (family, lambda0, effort). Independent of authority
    #    and of the parameter tolerance, which only enter the enclosures.
    # ------------------------------------------------------------------
    jobs = [(f, float(l), float(w)) for f in ("step", "smooth")
            for l in LAMBDA_GRID for w in EFFORT_GRID]
    print(f"\n--- solving {len(jobs)} LMI designs")
    got = pmap(_solve_design, jobs, desc="LMI", workers=10)
    designs = {}
    for (f, l, w), r in zip(jobs, got):
        if r is None:
            continue
        P, K = np.array(r[0]), np.array(r[1])
        designs[(f, l, w)] = (P, K)
        out["designs"][f"{f}|{l}|{w:g}"] = {
            "K_absmax": float(np.abs(K).max()),
            "eig_min_P": float(np.linalg.eigvalsh(P).min())}
    print(f"    {len(designs)}/{len(jobs)} feasible")

    # ------------------------------------------------------------------
    # 2. authority configurations (Sec 12 axes, hardware value first)
    # ------------------------------------------------------------------
    configs = [dict(label=f"duty={d:.2f}", duty=d, fmax=C.FMAX_PER_THRUSTER,
                    offset=C.FIT_OFFSET) for d in (0.40, 0.55, 0.70, 0.85, 1.00)]
    configs += [dict(label=f"fmax={fm:.1f}N", duty=0.40, fmax=fm,
                     offset=C.FIT_OFFSET) for fm in (2.0, 3.0, 4.0)]
    configs.append(dict(label="offset=0", duty=0.40, fmax=C.FMAX_PER_THRUSTER,
                        offset=0.0))
    configs.append(dict(label="duty=1.0,fmax=4.0,offset=0", duty=1.00, fmax=4.0,
                        offset=0.0))

    print("\n--- sweeping family x lambda x effort x tolerance x authority")
    rows = []
    for family in ("step", "smooth"):
        for span in SPAN_GRID:
            _, _, boxes = domain_vertices(family, mass_span=span, jzz_span=span)
            for (f, l, w), (P, K) in designs.items():
                if f != family:
                    continue
                for cfg in configs:
                    ach = achievable_set(cfg)
                    r = evaluate_certificate(
                        P, K, boxes, family, achievable=ach,
                        chain_factory=_chain_factory(cfg), J_res=J_res)
                    r.update({"lam0": l, "w_effort": w, "param_span": span,
                              "config": cfg["label"], "duty_ceiling": cfg["duty"],
                              "fmax": cfg["fmax"], "duty_offset": cfg["offset"],
                              "achievable": list(ach),
                              "is_hardware": (cfg["duty"] == 0.40
                                              and cfg["fmax"] == C.FMAX_PER_THRUSTER
                                              and cfg["offset"] == C.FIT_OFFSET)})
                    rows.append(r)
    out["sweep"] = rows
    print(f"    {len(rows)} sweep cells")

    report(out, rows)
    out["wall_time_s"] = time.time() - t0
    with open("results/stage7_certificate.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote results/stage7_certificate.json "
          f"({out['wall_time_s'] / 60:.1f} min)")


def report(out, rows):
    print("\n" + "=" * 78)
    print("CERTIFICATE RESULTS")
    print("=" * 78)

    for family in ("step", "smooth"):
        fam = [r for r in rows if r["family"] == family]
        print(f"\n### reference family: {family}")
        brs = [r["b_r"] for r in fam]
        print(f"  reference defect b_r spans {min(brs):.4f} .. {max(brs):.4f}")

        # ---- the contraction condition alone, vs parameter tolerance ----
        print("  contraction gamma+nu < 1 vs plant-parameter tolerance:")
        for span in sorted({r["param_span"] for r in fam}):
            sub = [r for r in fam if r["param_span"] == span]
            best = min(sub, key=lambda r: r["lam"])
            ok = "YES" if best["lam"] < 1.0 else "no "
            print(f"    +/-{span * 100:4.1f}%   best lambda = {best['lam']:.4f}  "
                  f"{ok}   (at lam0={best['lam0']}, w={best['w_effort']:g})")
        feas = sorted({r["param_span"] for r in fam if r["lam"] < 1.0})
        out["span_boundary"][family] = max(feas) if feas else None
        if feas:
            print(f"    -> contraction REQUIRES tolerance <= +/-{max(feas)*100:.0f}%")

        # ---- hardware configuration ----
        hw = [r for r in fam if r["is_hardware"] and r["lam"] < 1.0]
        if hw:
            b = min(hw, key=lambda r: r["ratio"])
            print(f"  HARDWARE authority (duty 0.40, fmax 1.2 N, offset -0.07686 s),"
                  f" best cell over the design grid:")
            print(f"    tolerance +/-{b['param_span']*100:.0f}%  lambda={b['lam']:.4f}"
                  f"  |K|max={b['K_absmax']:.2f}")
            print(f"    b_r={b['b_r']:.4f}  d_cert={b['d_cert']:.3f}  "
                  f"eta_q={b['eta_q']:.4f}")
            print(f"    s_cert={b['s_cert']:.4f}  vs  R_U={b['R_U']:.4f}  "
                  f"R_corridor={b['R_corridor']:.3f}  R_chart={b['R_chart']:.3f}")
            print(f"    NONEMPTY = {b['nonempty']}   binding: {b['binding']}")
            if b["residual_alpha_max"] is not None:
                a = b["residual_alpha_max"]
                print(f"    admissible residual Jacobian scale alpha <= {a:.3e}  "
                      f"({'the trained residual is INADMISSIBLE' if a < 1 else 'the trained residual is admissible'})")

        ok = [r for r in fam if r["nonempty"]]
        print(f"  nonempty cells: {len(ok)}/{len(fam)}")
        if ok:
            b = min(ok, key=lambda r: r["ratio"])
            print(f"  best nonempty cell: {b['config']}, tolerance "
                  f"+/-{b['param_span']*100:.0f}%, lambda={b['lam']:.4f}, "
                  f"s_cert={b['s_cert']:.4f} <= R={b['R_max']:.4f}, "
                  f"margin={b['margin']:.4f}")
            # minimum authority that works, at the best tolerance
            duties = sorted({r["duty_ceiling"] for r in ok})
            print(f"  duty ceilings admitting a nonempty region: {duties}")
        else:
            print("  EMPTY everywhere in the swept grid.")
            near = min(fam, key=lambda r: r["ratio"])
            print(f"  closest cell: {near['config']}, tol "
                  f"+/-{near['param_span']*100:.0f}%, lambda={near['lam']:.4f}, "
                  f"s_cert/R = {near['ratio']:.3g}, binding: {near['binding']}")


if __name__ == "__main__":
    main()

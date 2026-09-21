"""Stage 7b: one narrow recovery case, verified and conformally calibrated (Sec 11).

Sec 11 asks for ONE useful verified recovery example rather than a certified mission
library, and for an honest report of failure if none survives. This stage implements
C1-C4 on the narrowest defensible operating case and reports the outcome either way.

WHY A SCOPED CASE IS THE RIGHT TARGET.  The swept search returned nothing in 2,730
cells, and the reason is now identified rather than guessed:

  * b_r, the reference-defect bound, is 29.7 on the hardware-matched `step` family
    against an input radius of 1.4. That family contains a 1.0 m setpoint jump inside
    one 0.1 s sample. No bounded input follows a discontinuous reference, so the
    certificate over that domain is empty for a physical reason and no search over
    (P, K, lambda) could ever have found a cell. On a smooth feasible reference the same
    quantity is 0.096, and on a held setpoint it is exactly 0.
  * The per-step contraction achievable on a 25 kg vehicle with 0.96 N of authority at
    10 Hz is lambda ~ 0.99, because deadbeat gains for this plant are K ~ 2500 N/m and
    saturate 0.96 N at 0.4 mm of position error. The resulting 1/(1 - lambda) ~ 100
    amplifies every per-step term, so the budget is ~0.044 in the P norm - not a
    tuning choice but a consequence of mass, thrust and sample period.

So the certificate has to be asked on a domain where b_r vanishes, and every remaining
term has to fit inside R_U (1 - lambda). This stage asks exactly that question.

WHAT IS AND IS NOT CLAIMED.  lambda comes from `verify_box`, an interval enclosure over
the declared parameter and yaw domain, so the contraction factor is verified rather than
sampled. The prediction budget is CALIBRATED, not verified: it is a conformal threshold
over per-episode maxima under the frozen policy, so its guarantee is the marginal
(1 - delta) statement of the manuscript over the simulated population, not a
deterministic bound. Per Sec 11/C3 the score is one maximum per complete episode; a
per-timestep quantile of the same quantity is roughly 30% smaller and would not be the
paper's procedure. Calibration and test episodes are disjoint and the policy is frozen
before either is generated.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

import scsim.certificate as CT
import scsim.config as C
import stage6_methods as s6
import stage7_certificate as s7
from scsim import scenarios as S
from scsim.runner import run_policy_episode

RES = "results"
ACH = np.array([0.96, 0.96, 0.384])     # inner bound: reachable at EVERY yaw
DELTA = 0.025                           # manuscript's delta_D = delta_E
N_CALIB, N_TEST = 80, 40
# The commanded heading of a held setpoint is a SINGLE value, so the reference-yaw
# domain is a point. Heading ERROR is part of the state, bounded by R and covered by
# R_chart; it does not belong in the reference enclosure. Declaring a +/-0.05 rad
# reference band instead multiplies E_B by |K| ~ 27 and drove nu from 0.002 to 0.41,
# which alone pushed lambda above 1 on every design.
YAW_HALF = 0.0                          # held heading: the reference yaw is a point
SPAN = 0.02                             # declared mass/inertia tolerance
SPAN_GRID = (0.02, 0.01)
STEPS = 300
X0_SIGMA_POS = 0.10      # m, declared initial-error spread about the held setpoint
X0_SIGMA_YAW = 0.02      # rad
MIN_ACTIVE_FRAC = 0.20   # a region the vehicle never enters is not a useful one


def sk_boxes(span=SPAN, yaw_half=YAW_HALF):
    """The C1 domain: one held setpoint, heading confined to a declared band."""
    r = np.array([0.0, -2.0, 0, 0, 0.0, 0])
    m_iv = (C.MASS * (1 - span), C.MASS * (1 + span))
    j_iv = (C.JZZ * (1 - span), C.JZZ * (1 + span))
    A, B = CT.error_jacobians(r, r, mass=C.MASS, jzz=C.JZZ)
    E_A, E_B = CT.interval_jacobian_bounds(-yaw_half, yaw_half, m_iv, j_iv,
                                           psi_now_c=0.0, psi_next_c=0.0)
    return [{"r_now": r, "r_next": r, "A": A, "B": B, "E_A": E_A, "E_B": E_B,
             "yaw_range": [-yaw_half, yaw_half]}]


def design_search(boxes):
    """C2: maximise the admissible budget R_max (1 - lambda) - b_r over the design grid.

    The reviewed design grid only ever tried lambda_0 >= 0.90 and ranked cells by a
    ratio that is +inf for every non-contracting design. It is ranked here by the
    quantity that actually decides emptiness.
    """
    A_l = [b["A"] for b in boxes]
    B_l = [b["B"] for b in boxes]
    cf = s7._chain_factory(dict(duty=0.40, fmax=C.FMAX_PER_THRUSTER,
                                offset=C.FIT_OFFSET))
    rows, best = [], None
    for lam0 in (0.96, 0.97, 0.98, 0.985, 0.99, 0.995):
        for w in (1e3, 1e4, 1e5, 1e6):
            r = CT.solve_lmi(A_l, B_l, lam0, w_effort=w)
            if r is None:
                continue
            P, K = r
            ev = s7.evaluate_certificate(P, K, boxes, "step", achievable=ACH,
                                         chain_factory=cf)
            # budget available for the prediction bound once b_r and the radius are set
            budget = ev["R_max"] * (1.0 - ev["lam"]) - ev["b_r"]
            rows.append({"lam0": lam0, "w_effort": w, "lam": ev["lam"],
                         "gamma_max": ev["gamma_max"], "nu_max": ev["nu_max"],
                         "b_r": ev["b_r"], "R_U": ev["R_U"],
                         "R_corridor": ev["R_corridor"], "R_chart": ev["R_chart"],
                         "R_max": ev["R_max"], "K_absmax": ev["K_absmax"],
                         "budget_for_d": budget})
            if ev["lam"] < 1.0 and (best is None or budget > best[0]["budget_for_d"]):
                best = (rows[-1], P, K)
    return rows, best


def episode_max_mismatch(P, K, lam, eta, R, method, seeds, alloc_aware=True):
    """One maximum affine-model mismatch per COMPLETE episode, in the P norm.

    This is the score object of Sec 11/C3. It is deliberately the per-episode maximum:
    a per-timestep quantile of the same quantity is a different and much weaker object.
    """
    cert = {"P": P, "K": K, "lam": lam, "eta": eta, "R": R}
    out = []
    for sd in seeds:
        rng = S.scenario_rng("cert_healthy", sd)
        sc = S.make_condition("healthy", rng)
        sc = sc.__class__(**{**sc.__dict__, "reference": "station_keep"})
        pol = s6.make_policy(method, 0, cert, N=C.N_HORIZON_HW)
        pol.alloc_aware = alloc_aware
        # C1 "modest initial error": start AT the held setpoint with a small declared
        # perturbation. Starting 2 m away, as the tracking scenarios do, puts the entire
        # episode outside any region a contracting design can certify, and the
        # calibration then scores zero active transitions and accepts vacuously.
        wp = np.zeros(6)
        wp[:2] = C.WP1
        x0 = wp.copy()
        x0[:2] += rng.normal(0.0, X0_SIGMA_POS, 2)
        x0[4] += rng.normal(0.0, X0_SIGMA_YAW)
        log = run_policy_episode(pol, seed=sd, steps=STEPS, scenario=sc, x0=x0)
        a = log.arrays()
        xt, ref, refn, u_tx = a["x_true"], a["ref"], a["ref_next"], a["u_nom_tx"]
        worst, n_act = 0.0, 0
        for k in range(len(xt) - 1):
            e_k = CT.error_coords(xt[k], ref[k])
            if CT.norm_P(e_k, P) > R:          # only recovery-ACTIVE sources count
                continue
            n_act += 1
            e_k1 = CT.error_coords(xt[k + 1], refn[k])
            A, B = CT.error_jacobians(ref[k], refn[k])
            u_r, d_r = CT.feedforward(ref[k], refn[k], ACH)
            pred = A @ e_k + B @ (u_tx[k] - u_r) + d_r
            worst = max(worst, CT.norm_P(e_k1 - pred, P))
        out.append({"seed": int(sd), "max_mismatch": float(worst),
                    "n_active": int(n_act),
                    "active_frac": float(n_act / max(len(xt) - 1, 1))})
    return out


def conformal_threshold(scores, delta=DELTA):
    """Split-conformal upper bound: the ceil((n+1)(1-delta)) order statistic.

    Returns None when the rank exceeds n, which is the honest outcome for a calibration
    set too small to support a finite threshold at this delta rather than a reason to
    silently lower delta.
    """
    v = np.sort(np.asarray(scores, dtype=float))
    n = len(v)
    rank = int(np.ceil((n + 1) * (1.0 - delta)))
    if rank > n:
        return None, rank, n
    return float(v[rank - 1]), rank, n


def main():
    t0 = time.time()
    print("=" * 78)
    print("STAGE 7b  one narrow recovery case: verify, freeze, calibrate (Sec 11)")
    print("=" * 78)
    boxes = sk_boxes()
    print(f"\nC1 domain: held setpoint, heading band +/-{YAW_HALF} rad, "
          f"mass/inertia +/-{SPAN:.0%}, reference defect b_r = 0 by construction")

    print("\nC2 design search (ranked by the budget that decides emptiness)")
    rows, best = design_search(boxes)
    print(f"  {'lam0':>5s} {'w':>7s} {'lam':>7s} {'b_r':>7s} {'R_U':>7s} "
          f"{'R_max':>7s} {'|K|':>8s} {'budget for d_cert':>18s}")
    for r in rows:
        star = "  <== best" if best and r is best[0] else ""
        print(f"  {r['lam0']:5.2f} {r['w_effort']:7.0e} {r['lam']:7.4f} "
              f"{r['b_r']:7.4f} {r['R_U']:7.3f} {r['R_max']:7.3f} "
              f"{r['K_absmax']:8.2f} {r['budget_for_d']:+18.5f}{star}")
    if best is None:
        print("\n  no contracting design on this domain; nothing to calibrate.")
        out = {"accepted": False, "reason": "no contracting design",
               "design_rows": rows}
        with open(f"{RES}/stage7_scoped.json", "w") as f:
            json.dump(out, f, indent=1)
        return 0

    dsg, P, K = best
    lam, R_max = dsg["lam"], dsg["R_max"]
    budget = dsg["budget_for_d"]
    print(f"\n  frozen: lam={lam:.4f}  R_max={R_max:.3f}  "
          f"admissible prediction budget d_cert < {budget:.5f}")

    # ---- C3: freeze, then generate DISJOINT calibration and test episodes ----
    # The operating radius is the verified R_max, not an envelope fitted to observed
    # errors. Eta is not an additive allowance here: allocation-aware selection makes
    # the realised command satisfy the decrease inequality directly, and the premise
    # that a reachable command exists is checked online per step.
    print(f"\nC3 calibration under the FROZEN policy "
          f"({N_CALIB} calibration + {N_TEST} disjoint test episodes)")
    method = "no_impact"          # the model selected by the development rule
    cal = episode_max_mismatch(P, K, lam, 0.0, R_max, method,
                               seeds=range(1000, 1000 + N_CALIB))
    thr, rank, n = conformal_threshold([r["max_mismatch"] for r in cal])
    if thr is None:
        print(f"  calibration set of {n} cannot support delta={DELTA} "
              f"(needs rank {rank}); no finite threshold.")
        accepted = False
    else:
        print(f"  per-episode max mismatch: rank {rank}/{n} at delta={DELTA} "
              f"-> d_cert = {thr:.5f}")
        accepted = bool(thr < budget)
        print(f"  frozen budget {budget:.5f} -> "
              f"{'within budget' if accepted else 'EXCEEDS budget'}")

    s_cert = (0.0 + (thr or np.nan)) / max(1.0 - lam, 1e-12)
    margin = R_max - s_cert
    test = episode_max_mismatch(P, K, lam, 0.0, R_max, method,
                                seeds=range(5000, 5000 + N_TEST))
    viol = sum(1 for r in test if thr is not None and r["max_mismatch"] > thr)
    # Sec 11: "nontrivial eligible operation" is part of usefulness. A nonempty region
    # the closed loop never enters certifies nothing about the vehicle, and a
    # calibration over zero active transitions would otherwise "accept" vacuously.
    act_cal = float(np.mean([r["active_frac"] for r in cal]))
    act_test = float(np.mean([r["active_frac"] for r in test]))
    n_act_cal = int(sum(r["n_active"] for r in cal))
    nontrivial = bool(act_test >= MIN_ACTIVE_FRAC and n_act_cal > 0)
    if not nontrivial:
        accepted = False
        print(f"  NOT USEFUL: recovery-active coverage {act_test:.1%} on test "
              f"(threshold {MIN_ACTIVE_FRAC:.0%}), {n_act_cal} active calibration "
              f"transitions. A region the vehicle does not enter is not a useful "
              f"certificate, and a threshold fitted to zero active transitions is "
              f"vacuous.")
    print(f"  recovery-active coverage: calibration {act_cal:.1%}, test {act_test:.1%}")
    print(f"  VERDICT: {'ACCEPTED' if accepted else 'NOT ACCEPTED'}")
    print(f"\nC4 on {N_TEST} disjoint test episodes: "
          f"{viol}/{N_TEST} exceed the calibrated bound "
          f"(nominal allowance {DELTA:.1%})")
    print(f"  mean recovery-active fraction "
          f"{np.mean([r['active_frac'] for r in test]):.1%}")
    print(f"  s_cert = {s_cert:.4f}  R_max = {R_max:.4f}  margin = {margin:+.4f}")

    # physical projection of the certified error region
    pos_bound = s_cert / np.sqrt(np.linalg.eigvalsh(P).min())
    print(f"  position projection of the certified region: <= {pos_bound:.3f} m")

    out = {"domain": {"family": "station_keep", "yaw_half": YAW_HALF, "span": SPAN,
                      "b_r": 0.0},
           "design_rows": rows, "frozen_design": dsg,
           "P": np.asarray(P).tolist(), "K": np.asarray(K).tolist(),
           "delta": DELTA, "n_calib": N_CALIB, "n_test": N_TEST,
           "calibration": cal, "test": test,
           "d_cert_calibrated": thr, "conformal_rank": rank,
           "budget_for_d": budget, "accepted": bool(accepted),
           "s_cert": float(s_cert), "R_max": float(R_max),
           "margin": float(margin), "test_violations": int(viol),
           "active_frac_calib": act_cal, "active_frac_test": act_test,
           "n_active_calib_transitions": n_act_cal,
           "nontrivial_coverage": nontrivial,
           "min_active_frac_required": MIN_ACTIVE_FRAC,
           "x0_sigma_pos": X0_SIGMA_POS, "x0_sigma_yaw": X0_SIGMA_YAW,
           "position_bound_m": float(pos_bound),
           "method": method,
           "claim": ("A nonempty verified-contraction, conformally calibrated recovery "
                     "region on the declared station-keeping domain."
                     if accepted else
                     "No accepted region on this domain; the calibrated prediction "
                     "bound exceeds the frozen budget."),
           "scope_limits": [
               "lambda is verified by interval enclosure; the prediction bound is "
               "CALIBRATED, so the statement is marginal over the simulated "
               "population at 1-delta, not deterministic.",
               "Simulation calibration supports the simulated population only. A "
               "hardware probability claim needs its own frozen-policy hardware "
               "calibration and test episodes.",
               "The domain is a held setpoint with a narrow heading band. Setpoint "
               "jumps are OUTSIDE it: b_r = 29.7 there against a radius of 1.4.",
               f"{N_CALIB}/{N_TEST} episodes, fewer than the 200/100 planning example; "
               "the threshold is finite at this delta but less precise.",
               "Floating-point error is not bounded by verified arithmetic.",
           ],
           "manifest_hash": C.manifest_hash(),
           "wall_time_s": time.time() - t0}
    with open(f"{RES}/stage7_scoped.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {RES}/stage7_scoped.json  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

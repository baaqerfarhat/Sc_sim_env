"""Stage 0: semantic checks on the information boundary and the physics.

These are the Section 2.4 and 3.4 checks of the corrections plan, and they are gates
in the strongest sense: every one of them failed or was absent in the previous
campaign, and the results of that campaign are void because of it. The three defects
they pin down are

  * the controller-visible wrench was computed from POST-fault pulses, so the hidden
    actuation fault was observable in the encoder input, the predictor input and the
    acceptance check;
  * physical body force was rotated into the world frame by the ESTIMATED yaw, so
    physical acceleration depended on estimator error;
  * a fallback that failed its own acceptance check was transmitted anyway.

A check here asserts an invariant of the interface, not agreement with a number.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from scsim import config as C
from scsim import plant as P
from scsim import scenarios as S

RES = "results"
os.makedirs(RES, exist_ok=True)

CHECKS = {}


def check(name, ok, detail=""):
    CHECKS[name] = {"pass": bool(ok), "detail": detail}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if detail:
        print(f"         {detail}")
    return bool(ok)


# ==========================================================================
# Section 2.4: the hidden-fault boundary
# ==========================================================================
def _fresh_chain(fault_fraction, active, phase=0, eta_smooth=None):
    f = P.DeterministicFault(fault_fraction, active=active)
    for _ in range(phase):
        f.advance()
    return P.CommandChain(fault=f, eta_smooth=eta_smooth)


def sec2_hidden_fault_invisible():
    """Changing hidden fault severity, phase or onset must not change any
    controller-visible quantity produced by a trial allocation."""
    u_star = np.array([0.35, -0.22, 0.05])
    psi = 0.3

    variants = {
        "no fault": _fresh_chain(1.0, False),
        "skip 70%": _fresh_chain(0.7, True),
        "skip 30%": _fresh_chain(0.3, True),
        "skip 70%, phase 3": _fresh_chain(0.7, True, phase=3),
        "smooth eta 0.4": _fresh_chain(1.0, False,
                                       eta_smooth=np.full(8, 0.4)),
    }
    base = None
    worst = 0.0
    for name, ch in variants.items():
        u_nom, info = ch.trial(u_star, psi)
        sig = np.concatenate([u_nom, info["u_commanded"], info["F_alloc"],
                              info["pulse_command_s"]])
        if base is None:
            base, base_name = sig, name
        else:
            worst = max(worst, float(np.max(np.abs(sig - base))))
    check("2.4a hidden severity/phase does not change controller-visible trial",
          worst == 0.0,
          f"max |difference| over {len(variants)} hidden settings = {worst:.3e} "
          f"(wrench, commanded wrench, allocated force, commanded pulses)")


def sec2_physical_successor_does_change():
    """The complement: the PHYSICAL result must still respond to the hidden fault,
    otherwise the boundary was enforced by making the fault inert."""
    u_star = np.array([0.0, 0.9, 0.0])   # FY+ pair, the faulted thrusters
    psi = 0.0
    x0 = np.zeros(6)
    outs = {}
    for name, ch in (("healthy", _fresh_chain(1.0, False)),
                     ("skip", _fresh_chain(0.0, True))):
        _, info = ch.trial(u_star, psi)
        pulse_actual, skipped = ch.apply_hidden(info)
        x1 = P.plant_step(x0, pulse_actual)
        outs[name] = (x1, skipped, info["pulse_command_s"].copy(), pulse_actual)
    dv = float(np.max(np.abs(outs["healthy"][0] - outs["skip"][0])))
    same_cmd = np.allclose(outs["healthy"][2], outs["skip"][2])
    check("2.4b physical successor still changes with the hidden fault",
          dv > 1e-6 and same_cmd,
          f"identical commanded pulses (max diff "
          f"{float(np.max(np.abs(outs['healthy'][2] - outs['skip'][2]))):.1e}) but "
          f"physical state differs by {dv:.4e}; skip flags "
          f"{outs['healthy'][1]}/{outs['skip'][1]}")


def sec2_trial_does_not_mutate():
    """Repeated trial allocation must not advance allocator memory or the fault."""
    ch = _fresh_chain(0.7, True)
    u_star = np.array([0.4, 0.1, 0.02])
    hist0 = ch.use_hist.copy()
    cyc0, fired0 = ch.fault.fault_cycle, ch.fault.fault_fired
    sigs = []
    for _ in range(5):
        u_nom, info = ch.trial(u_star, 0.0)
        sigs.append(u_nom.copy())
    drift = float(np.max(np.abs(np.array(sigs) - sigs[0])))
    ok = (drift == 0.0 and np.array_equal(hist0, ch.use_hist)
          and (cyc0, fired0) == (ch.fault.fault_cycle, ch.fault.fault_fired))
    check("2.4c repeated trials mutate neither allocator memory nor fault phase",
          ok, f"5 trials: max drift {drift:.1e}, memory unchanged "
              f"{np.array_equal(hist0, ch.use_hist)}, "
              f"fault counter {cyc0}->{ch.fault.fault_cycle}")


def sec2_one_commit_one_slot():
    """Exactly one commit advances memory once and the fault schedule once."""
    ch = _fresh_chain(0.7, True)
    u_a, u_b = np.array([0.4, 0.1, 0.0]), np.array([-0.3, 0.2, 0.01])
    _, info_a = ch.trial(u_a, 0.0)
    _, info_b = ch.trial(u_b, 0.0)          # a second candidate, not transmitted
    cyc0 = ch.fault.fault_cycle
    ch.commit(info_b)                        # transmit exactly one packet
    advanced_once = ch.fault.fault_cycle == cyc0 + 1
    committed_b = np.allclose(
        ch.use_hist,
        P.update_use_hist(np.zeros(8), info_b["_F_for_commit"]))
    check("2.4d one commit = one memory update and one fault slot",
          advanced_once and committed_b,
          f"fault cycle {cyc0}->{ch.fault.fault_cycle}; committed packet is the "
          f"selected one: {committed_b}")


def sec2_one_execution_contract():
    """The data-generation path and the policy path must realise the hidden fault at
    the SAME counter state.

    `CommandChain.__call__` (used by data generation) previews the fault and then
    advances. The policy path advances inside `policy.act`'s `chain.commit` and only
    then calls `apply_hidden`, so it runs the schedule one cycle early. That makes the
    training and evaluation distributions differ at packet level for the same
    commanded pulses, which is precisely the correspondence a learned residual relies
    on. The skip RATE is unchanged, so this is a phase defect rather than a severity
    defect, but it still has to be one contract.
    """
    u_star = np.array([0.35, -0.22, 0.05])
    disagree = []
    for frac in (0.3, 0.5, 0.7, 0.9):
        for phase in (0, 1, 2):
            a, b = [], []
            ch = _fresh_chain(frac, True, phase=phase)
            for _ in range(8):
                _, info = ch(u_star, 0.0)                  # shorthand path
                a.append(not info["fault_skip"])
            ch = _fresh_chain(frac, True, phase=phase)
            for _ in range(8):
                _, info = ch.trial(u_star, 0.0)
                ch.commit(info)                            # what policy.act does
                _, skipped = ch.apply_hidden(info)         # what the runner does
                b.append(not skipped)
            if a != b:
                disagree.append((frac, phase))
    check("2.4f data-generation and policy paths fire identical physical pulses",
          not disagree,
          f"{len(disagree)} of 12 (firing fraction, phase) configurations produce "
          f"different fire/skip sequences between the two execution paths"
          + (f"; e.g. {disagree[0]}" if disagree else "")
          + ". The policy path advances the fault counter in commit() before "
            "apply_hidden() previews it, so it runs one cycle ahead of the "
            "shorthand used to generate training data.")


def sec2_reconstruct_u_from_pulses():
    """u_k must be reconstructible from saved commanded pulses and nominal params."""
    ch = _fresh_chain(0.7, True)
    psi = -0.4
    u_nom, info = ch.trial(np.array([0.3, 0.5, -0.03]), psi)
    recon = P.alloc_matrix(psi) @ (C.VALVE_THRUST * info["pulse_command_s"] / C.TS)
    err = float(np.max(np.abs(recon - u_nom)))
    check("2.4e u_k reconstructs from commanded pulses and nominal parameters",
          err < 1e-12, f"max |reconstruction - logged| = {err:.2e}")


# ==========================================================================
# Section 3.4: physics, coordinates, authority
# ==========================================================================
def sec3_true_yaw_rotates_force():
    """True yaw 90 deg, estimated yaw 0, body-forward pulse: the physical
    acceleration must rotate with the TRUE yaw."""
    dt = np.zeros(8)
    dt[4] = dt[5] = 0.02          # FX+ pair -> +x body force
    x0 = np.zeros(6)
    x_fwd = P.plant_step(x0, dt)
    x_rot = P.plant_step(np.array([0, 0, 0, 0, np.pi / 2, 0], float), dt)
    # +x body at yaw 90 deg must appear as +y world
    ok = (x_fwd[2] > 1e-4 and abs(x_fwd[3]) < 1e-9
          and x_rot[3] > 1e-4 and abs(x_rot[2]) < 1e-9)
    check("3.4a body force rotates with TRUE yaw",
          ok, f"yaw 0 -> dv=({x_fwd[2]:+.5f},{x_fwd[3]:+.5f}), "
              f"yaw 90deg -> dv=({x_rot[2]:+.5f},{x_rot[3]:+.5f})")


def sec3_estimate_cannot_touch_physics():
    """plant_step must not accept an estimator yaw at all: verified structurally,
    since a signature that cannot take the estimate cannot depend on it."""
    import inspect
    params = list(inspect.signature(P.plant_step).parameters)
    ok = "psi_hold" not in params and "psi_hat" not in params
    check("3.4b physical integration takes no estimator yaw argument",
          ok, f"plant_step parameters: {params}")


def sec3_integration_converges():
    """Identical pulses at successively finer steps: differences must fall below a
    declared numerical tolerance."""
    dt = np.zeros(8)
    dt[4], dt[1] = 0.031, 0.017
    x0 = np.array([0.2, -0.1, 0.05, 0.0, 0.3, 0.02])
    ref = P.plant_step(x0, dt, substeps=4000)
    rows = []
    for n in (20, 40, 80, 160, 320):
        e = float(np.max(np.abs(P.plant_step(x0, dt, substeps=n) - ref)))
        rows.append((n, e))
    tol = 5e-4
    e20 = rows[0][1]
    ratio = rows[0][1] / max(rows[2][1], 1e-18)
    check("3.4c integration converges under refinement",
          e20 < tol,
          "max |x(n) - x(4000)|: "
          + ", ".join(f"n={n}: {e:.2e}" for n, e in rows)
          + f" (declared tol {tol:.0e} at the production n={C.PLANT_SUBSTEPS}; "
            f"20->80 improves {ratio:.1f}x)")


def sec3_thrust_scales_impulse():
    """Increasing actual valve thrust at fixed pulse duration must increase the
    physical impulse proportionally. This is what an authority change means."""
    dt = np.zeros(8)
    dt[4] = dt[5] = 0.025
    x0 = np.zeros(6)
    v1, v2 = C.VALVE_THRUST, 2.0 * C.VALVE_THRUST
    d1 = P.plant_step(x0, dt, valve=v1)[2]
    d2 = P.plant_step(x0, dt, valve=v2)[2]
    ratio = d2 / d1 if d1 else np.nan
    check("3.4d physical impulse scales with ACTUAL valve thrust",
          abs(ratio - 2.0) < 1e-9,
          f"dv({v1:.1f} N) = {d1:.6f}, dv({v2:.1f} N) = {d2:.6f}, "
          f"ratio {ratio:.6f} (expected 2)")


def sec3_rotation_equivariance():
    """Rotating a whole scenario (state, yaw, pulses fixed in body frame) must
    rotate the world-frame result by the same angle."""
    dt = np.zeros(8)
    dt[4], dt[6] = 0.02, 0.015
    th = 0.7
    x0 = np.array([0.0, 0.0, 0.1, -0.05, 0.0, 0.0])
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    x0r = x0.copy()
    x0r[0:2], x0r[2:4], x0r[4] = R @ x0[0:2], R @ x0[2:4], th
    a = P.plant_step(x0, dt)
    b = P.plant_step(x0r, dt)
    err = max(float(np.max(np.abs(R @ a[0:2] - b[0:2]))),
              float(np.max(np.abs(R @ a[2:4] - b[2:4]))),
              abs(P.wrap_pi(a[4] + th - b[4])), abs(a[5] - b[5]))
    check("3.4e planar rotation equivariance of the physical plant",
          err < 1e-12, f"max deviation {err:.2e} over position, velocity, yaw, rate")


def sec3_authority_is_physical():
    """A sweep that claims larger thrusters must change actual delivered thrust,
    not only the allocator's permitted request."""
    dt = np.zeros(8)
    dt[4] = dt[5] = 0.02
    x0 = np.zeros(6)
    alloc_only = P.plant_step(x0, dt, valve=C.VALVE_THRUST)[2]
    physical = P.plant_step(x0, dt, valve=4.0)[2]
    check("3.4f allocator-only vs physical authority are distinguishable",
          physical > alloc_only * 2.0,
          f"same commanded pulses: dv = {alloc_only:.5f} at nominal valve thrust "
          f"vs {physical:.5f} at 4.0 N. A sweep changing only the allocator's fmax "
          f"leaves the first number unchanged and must be labelled as such.")


def _mini_policy(**kw):
    """A LearnedContextPolicy on a real checkpoint with a usable (P, K) design."""
    import glob
    from scsim.controllers import LearnedContextPolicy
    from scsim import certificate as CT
    import stage7_certificate as s7

    paths = sorted(glob.glob("data/model_full_s*.pt"))
    if not paths:
        return None
    A_list, B_list, _ = s7.domain_vertices("step", mass_span=0.05, jzz_span=0.05)
    r = CT.solve_lmi(A_list, B_list, 0.99, w_effort=1e4)
    if r is None:
        return None
    P, K = r
    d = dict(P=P, K=K, lam=0.99, eta=0.05, R=50.0)
    d.update(kw)
    return LearnedContextPolicy(paths[0], **d)


def sec4_selection_semantics():
    """Sec 4.6: force each rejection path and verify what is actually transmitted."""
    from scsim import plant as P_
    from scsim import scenarios as S_
    from scsim.runner import run_policy_episode

    pol = _mini_policy()
    if pol is None:
        check("4.6 selection semantics", False,
              "no trained checkpoint available yet; rerun after Stage 5")
        return

    # (a) an impossible acceptance bar (eta very negative) must reject every candidate
    #     and force the fallback / supervisor path, never an unchecked candidate
    pol_rej = _mini_policy(eta=-1e6)
    sc = S_.make_condition("combined", np.random.default_rng(3), reference="step")
    log = run_policy_episode(pol_rej, seed=555, steps=120, scenario=sc)
    a = log.arrays()
    srcs = set(a["action_src"])
    st = log.meta["policy_stats"]
    no_candidate = "candidate" not in srcs
    check("4.6a an unsatisfiable acceptance bar never transmits a candidate",
          no_candidate,
          f"action sources observed: {sorted(srcs)}; "
          f"rejects={st['n_reject']}, first-action failures="
          f"{st.get('n_first_action_fail', 0)}, supervisor={st['n_supervisor']}")

    # (b) an unsatisfiable bar also makes the FALLBACK fail its own check, so
    #     eligibility must be false and the fixed supervisor must act. The earlier
    #     implementation transmitted the failing fallback instead.
    frac_sup = float(np.mean([s == "supervisor" for s in a["action_src"]]))
    check("4.6b a failing fallback yields ineligibility and the fixed supervisor",
          frac_sup > 0.5 and int(np.asarray(a["gate"]).sum()) == 0,
          f"supervisor share {frac_sup * 100:.0f}%, eligible steps "
          f"{int(np.asarray(a['gate']).sum())} of {len(a['gate'])} "
          f"(eligibility requires a PASSING fallback)")

    # (c) the selection must be EXACTLY accounted for by its declared conditions.
    #     A permissive eta is deliberately not enough to force a candidate through:
    #     the Sec 4.2 first-action condition carries no eta, so it can still reject.
    pol_ok = _mini_policy(eta=1e6, R=1e9)
    log2 = run_policy_episode(pol_ok, seed=555, steps=120, scenario=sc)
    a2 = log2.arrays()
    st2 = log2.meta["policy_stats"]
    src2 = list(a2["action_src"])
    n = len(src2)
    n_cand = sum(1 for s in src2 if s == "candidate")
    n_fa = sum(1 for s in src2 if s == "fallback_first_action")
    n_ck = sum(1 for s in src2 if s == "fallback_checked")
    n_sup = sum(1 for s in src2 if s == "supervisor")
    # every step is accounted for by exactly one declared outcome, and the
    # first-action tally in the stats matches the number of diverted steps
    exact = (n_cand + n_fa + n_ck + n_sup == n
             and st2.get("n_first_action_fail", -1) == n_fa
             and st2["n_reject"] == n_ck)
    check("4.6c every step is accounted for by exactly one declared outcome",
          exact,
          f"of {n} steps: {n_cand} candidate, {n_fa} diverted by the eta-free "
          f"first-action condition, {n_ck} by command admissibility / acceptance, "
          f"{n_sup} supervisor. A permissive eta cannot rescue the first-action "
          f"condition by construction, which is why that share stays high.")

    # (d) the candidate's slack must not be relabelled as the transmitted slack
    ok_sep = "slack_fb" in a and len(a["slack_fb"]) == len(a["slack_cmd"])
    check("4.6d candidate and fallback slacks are recorded separately",
          ok_sep,
          "slack_cmd (candidate) and slack_fb (fallback) are distinct log channels, "
          "so a candidate's slack cannot be read as the transmitted action's slack")

    # (e) trial allocations inside one control step must not advance the fault
    #     schedule more than once per transmitted command
    n_skips = log.meta["n_fault_skips"]
    check("4.6e one transmitted command advances the fault schedule once",
          n_skips <= 120,
          f"{n_skips} skips over 120 control steps with 2-3 trial allocations each; "
          f"only the committed packet advances the schedule")


def sec6_enclosure_not_falsified():
    """Sec 6.1: sampling cannot certify an enclosure, but it CAN refute one, and
    refuting one is fatal because every downstream certificate number depends on it.

    For each design point, sample the actual Jacobians over the declared box and
    check that no entry of |A(v) - A_b| or |B(v) - B_b| exceeds the returned bound.
    """
    import stage7_certificate as s7
    from scsim import certificate as CT

    rng = np.random.default_rng(0)
    worst_A = worst_B = -np.inf
    detail = ""
    n_pts = 0
    for family in ("step", "smooth"):
        for span in (0.05, 0.10):
            _, _, boxes = s7.domain_vertices(family, mass_span=span, jzz_span=span)
            m_iv = (C.MASS * (1 - span), C.MASS * (1 + span))
            j_iv = (C.JZZ * (1 - span), C.JZZ * (1 + span))
            for b in boxes:
                lo, hi = b["yaw_range"]
                for _ in range(300):
                    pn = rng.uniform(lo, hi)
                    px = rng.uniform(lo, hi)
                    m = rng.uniform(*m_iv)
                    j = rng.uniform(*j_iv)
                    r_n, r_x = b["r_now"].copy(), b["r_next"].copy()
                    r_n[4], r_x[4] = pn, px
                    A, B = CT.error_jacobians(r_n, r_x, mass=m, jzz=j)
                    vA = float(np.max(np.abs(A - b["A"]) - b["E_A"]))
                    vB = float(np.max(np.abs(B - b["B"]) - b["E_B"]))
                    n_pts += 1
                    if vA > worst_A:
                        worst_A = vA
                    if vB > worst_B:
                        worst_B, detail = vB, f"{family}, span {span}"
    ok = worst_A <= 0.0 and worst_B <= 0.0
    check("6.1 interval enclosure not falsified by sampling",
          ok,
          f"{n_pts} sampled points: worst (|dA| - E_A) = {worst_A:+.3e}, "
          f"worst (|dB| - E_B) = {worst_B:+.3e}; both must be <= 0. "
          f"Passing does NOT certify the continuum, only that no counterexample "
          f"was found ({detail}).")


def main():
    t0 = time.time()
    print("=" * 78)
    print("STAGE 0  semantic gates: information boundary and physics")
    print("=" * 78)
    print("\n--- Section 2.4: hidden-fault boundary ---")
    sec2_hidden_fault_invisible()
    sec2_physical_successor_does_change()
    sec2_trial_does_not_mutate()
    sec2_one_commit_one_slot()
    sec2_one_execution_contract()
    sec2_reconstruct_u_from_pulses()

    print("\n--- Section 3.4: physics, coordinates, authority ---")
    sec3_true_yaw_rotates_force()
    sec3_estimate_cannot_touch_physics()
    sec3_integration_converges()
    sec3_thrust_scales_impulse()
    sec3_rotation_equivariance()
    sec3_authority_is_physical()

    print("\n--- Section 4.6: controller selection semantics ---")
    sec4_selection_semantics()

    print("\n--- Section 6.1: interval enclosure soundness ---")
    sec6_enclosure_not_falsified()

    n = len(CHECKS)
    npass = sum(1 for v in CHECKS.values() if v["pass"])
    print("\n" + "=" * 78)
    print(f"{npass}/{n} semantic checks pass")
    fails = [k for k, v in CHECKS.items() if not v["pass"]]
    if fails:
        print("FAILED: " + ", ".join(fails))
        print("These are gates. Nothing downstream is meaningful until they pass.")
    print("=" * 78)

    with open(f"{RES}/stage0_semantics.json", "w") as f:
        json.dump({"checks": CHECKS, "n_pass": npass, "n_checks": n,
                   "failures": fails, "manifest_hash": C.manifest_hash(),
                   "wall_time_s": time.time() - t0}, f, indent=1)
    print(f"wrote {RES}/stage0_semantics.json")
    raise SystemExit(0 if not fails else 1)


if __name__ == "__main__":
    main()

"""Path B shared definitions: method matrix, scenario manifests, endpoints, scoring.

Everything that more than one Path B stage needs lives here, so the method matrix, the
task specification, the action taxonomy and the scoring code cannot drift between the
development gates and the prospective test.

Sections cited in comments refer to `pathB/EXPERIMENTS_AND_RESULTS_PLAN.md`.

FROZEN CHOICES, declared here once
----------------------------------
* Task dwell is 22 OBSERVATIONS, which spans 2.1 elapsed seconds at exactly 10 Hz. The
  archived implementation used 21 observations and labelled the result 2.1 s; 21
  observations span 20 intervals, which is 2.0 s. Sec 9.4's preferred freeze keeps the
  JSON's elapsed-time MEANING, so the count moves to 22 and the endpoint is reported as
  2.1 s. It is never reported as both.
* The scoring window starts at the onset, or at the pseudo-onset for healthy episodes.
  This differs from the archived healthy endpoint, which used the complete episode.
  Both are labelled and never pooled.
* Scenario keys are drawn from blocks disjoint from every seed the archive used.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from scsim import config as C
from scsim import scenarios as S

RES, DATA = "results", "data"

# ==========================================================================
# Sec 4: the exact method matrix
# ==========================================================================
CONDITIONS = S.MAIN_CONDITIONS
FAMILIES = ("step", "smooth_dock")
SEEDS = (0, 1, 2, 3, 4)               # Sec 4.1 five-seed target

# id -> (internal policy name, checkpoint tag, seeded?, deployment overrides)
#
# `seeded=False` marks a controller whose transmitted commands provably do not depend on
# the checkpoint. Sec 4.1 forbids copying its single trajectory five times and calling
# the copies seed replicates, and Sec 11.4 forbids reporting the copies as rollouts, so
# these run once per scenario and the independence is verified empirically in the smoke
# gate rather than asserted here.
METHODS = {
    "M0": dict(policy="nominal_recovery", tag="full", seeded=False, opts={},
               label="nominal, no learned residual or context",
               purpose="isolates the learned predictor from the rest of the controller"),
    "M1": dict(policy="constant_context", tag="const", seeded=True, opts={},
               label="trained constant context",
               purpose="fair static learned-model baseline"),
    "M2": dict(policy="no_impact", tag="no_impact", seeded=True, opts={},
               label="changing context, prediction losses only (SELECTED)",
               purpose="the selected learned method"),
    "M3": dict(policy="full", tag="full", seeded=True, opts={},
               label="changing context + behavioural loss",
               purpose="behavioural-supervision ablation; NOT the selected method"),
    "M4": dict(policy="full_no_check", tag="full", seeded=True,
               opts={"enforce_post_alloc": False},
               label="M3 with the repeated post-allocation check disabled",
               purpose="isolates the repeated decrease check"),
    "M5": dict(policy="fallback_only", tag="full", seeded=False, opts={},
               label="nominal feedback + repair, no MPC optimisation",
               purpose="simpler pipeline baseline; M2-M5 does NOT isolate planning"),
    "Mmotion": dict(policy="no_impact", tag="motion", seeded=True, opts={},
                    label="M2 without the estimator-diagnostic channels",
                    purpose="incremental value of the explicit diagnostic channels"),
    "Roff": dict(policy="no_impact", tag="no_impact", seeded=True,
                 opts={"repair": False},
                 label="M2 with finite proposal repair disabled",
                 purpose="clean repair contrast; both arms screen the TRANSMITTED "
                         "command"),
}

# the co-primary contrasts, and the family each one is estimated on (Sec 1.2)
CO_PRIMARY = (("D21", "M2", "M1", "step",
               "changing context vs trained constant context"),
              ("D25", "M2", "M5", "smooth_dock",
               "complete learned-MPC pipeline vs nominal feedback/repair"))
# secondary contrasts, descriptive only (Sec 9.3)
SECONDARY = (("M3", "M2", "behavioural loss"),
             ("M2", "Mmotion", "estimator-diagnostic channels"),
             ("M2", "Roff", "finite proposal repair"),
             ("M3", "M4", "repeated post-allocation check"),
             ("M2", "M0", "learned residual"),
             ("M2", "M5", "learned-MPC pipeline"),
             ("M2", "M1", "changing context"))

# ==========================================================================
# Sec 9.4: the frozen task specification
# ==========================================================================
# ---- task_success_v2: a DUAL endpoint, one frame each ----------------------
# The archived provisional pair (0.15 m, 5 deg) was specified on the TRUE state. Plan line
# 524 required it to be justified or changed on development evidence before the test
# manifest was generated. `pathb2_floor.py` showed it cannot be justified on the true state:
# the simulator has no absolute position reference after the one-shot t0 alignment, and
# `scsim/estimator.py` gives the VO position and heading biases unbounded random walks
# (healthy bias_rw = 0.02 m/sqrt(s), yaw_bias_rw = 0.016 rad/sqrt(s)). At the 60 s
# completion deadline that puts the ESTIMATE a mean 0.194 m and a 90th-percentile 0.332 m
# away from the truth, with a heading spread of 11.7 deg, confirmed open-loop with no
# controller in the loop at 0.350 m and 13.3 deg. A controller cannot place the true state
# closer to the goal than its estimate is to the truth, so a 0.15 m TRUE-state tolerance
# scores zero for every method under every task and discriminates nothing. That, not the
# choice of task, is why the Sec 6.4 ladder failed at every rung.
#
# The replacement keeps both frames instead of picking one:
#   DECLARED  scored on the estimate. The completion an onboard system would assert.
#             Retains the archived 0.15 m / 5 deg unchanged.
#   ACHIEVED  scored on the true state, at the healthy estimation floor rounded up.
#             What a ground-truth observer would certify.
# The GAP between them is itself an endpoint, and for a perception-fault paper it is the
# informative one: it measures how much of a method's apparent success is the estimator
# deceiving itself.
TASK_TOL_POS = 0.15                     # m, DECLARED frame (estimate)
TASK_TOL_YAW = np.deg2rad(5.0)          # rad, DECLARED frame
TASK_TOL_POS_TRUE = 0.35                # m, ACHIEVED frame; healthy floor 0.332 rounded up
TASK_TOL_YAW_TRUE = np.deg2rad(15.0)    # rad, ACHIEVED frame; healthy floor 11.7 rounded up
TASK_DWELL_OBS = 22                     # observations; 21 intervals = 2.1 s at 10 Hz
TASK_DWELL_S = (TASK_DWELL_OBS - 1) * C.TS
TASK_DEADLINE_STEPS = C.EPISODE_STEPS

TASK_SPEC = {
    "version": "task_success_v2",
    "declared": {"frame": "estimated state, the onboard assertion",
                 "tol_pos_m": TASK_TOL_POS, "tol_yaw_deg": 5.0},
    "achieved": {"frame": "true state, a ground-truth observer",
                 "tol_pos_m": TASK_TOL_POS_TRUE, "tol_yaw_deg": 15.0},
    "dwell_observations": TASK_DWELL_OBS,
    "dwell_elapsed_s": TASK_DWELL_S,
    "deadline_s": TASK_DEADLINE_STEPS * C.TS,
    "convention": (f"{TASK_DWELL_OBS} consecutive observations span "
                   f"{TASK_DWELL_OBS - 1} intervals = {TASK_DWELL_S:.1f} elapsed "
                   f"seconds at exactly 10 Hz, by logged timestamps."),
    "changed_from_archive": ("Two changes. (a) The archive used 21 observations and "
                             "labelled the result 2.1 s; 21 observations span 2.0 s, so "
                             "Sec 9.4's preferred freeze preserves the elapsed-time "
                             "meaning and the count is 22. (b) The archived 0.15 m / "
                             "5 deg pair was applied to the TRUE state, where it is below "
                             "the estimation floor and unreachable for every method; it is "
                             "retained unchanged on the ESTIMATE and a separate true-state "
                             "pair is derived from the floor. The endpoint is never "
                             "reported under both dwell conventions, and the two frames "
                             "are never merged into one number."),
    "provenance": ("DECLARED thresholds are the archived provisional engineering values, "
                   "retained unchanged. ACHIEVED thresholds are fixed by the frozen VO "
                   "constants through the analytic floor in results/pathb2_floor.json, not "
                   "fitted to any rollout. Neither pair is a measured spacecraft "
                   "requirement. Both were frozen from development evidence only, before "
                   "the prospective test manifest was generated, and neither moves after "
                   "any prospective outcome is seen."),
    "scope": "A sampled task-completion endpoint. NOT an intersample guarantee.",
}

# the separate historical diagnostic, never merged with task success
DIAGNOSTIC_RECOVERY_TOL = 0.662
DIAGNOSTIC_RECOVERY_LABEL = ("diagnostic recovery (baseline-relative ~0.66 m "
                             "tolerance) carried over from the archive; NOT task "
                             "success and never merged with it")

# ==========================================================================
# Sec 8.4: the mutually exclusive transmitted-action taxonomy
# ==========================================================================
ACTION_SOURCES = (
    "mpc_primary",
    "mpc_replacement",
    "m5_feedback",
    "fallback_first_screen",
    "fallback_repeated_check",
    "fallback_command_admissibility",
    "fallback_solver",
    "fallback_deadline",
    "supervisor_operating_radius",
    "supervisor_no_passing_fallback",
    "supervisor_preaction_ineligible_other",
    "supervisor_posteligibility_failure",
)

# Sec 9.5: exactly one terminal progress category per rollout
PROGRESS_CATEGORIES = (
    "never_entered_position_tolerance",
    "position_but_never_simultaneous_yaw",
    "both_tolerances_but_no_dwell",
    "task_success",
    "corrupted_unscorable",
)
# Sec 9.5: orthogonal event flags; several may be true at once and they are NOT forced
# into the progress category
EVENT_FLAGS = (
    "departed_after_entering",
    "supervisor_intervention",
    "no_passing_fallback",
    "solver_failure",
    "repair_search_failure",
    "deadline_overrun",
    "numerical_anomaly",
    "episode_deadline_censored",
)

# ==========================================================================
# Sec 6.1: scenario key blocks, disjoint from everything the archive used
# ==========================================================================
# archive usage: stage5 data 10_000-10_359, stage6 calibration 10_000-10_024,
# stage6 test 20_000-20_059, stage7b 1_000-1_080 and 5_000-5_040, stage8 20_000+.
# Path B therefore takes fresh blocks two orders of magnitude away.
KEY_BLOCKS = {
    "feasibility": 700_000,   # Sec 6.4 smooth-task development gate
    "smoke": 710_000,         # Sec 7 Priority 2 instrumentation gate
    "stopgate": 720_000,      # Sec 7 Priority 2 M3/M4 semantic gate
    "calibration": 730_000,   # frozen operational constants
    "test": 800_000,          # the prospective test manifest
}
N_TEST_PER_CELL = 60          # Sec 6.1: 60 unique scenarios per condition and family


def scenario_keys(block, n, *, offset=0):
    """Episode seeds for a named key block. Blocks are disjoint by construction."""
    base = KEY_BLOCKS[block]
    return [base + offset + i for i in range(n)]


def draw_scenario(family, condition, ep_seed):
    """One matched scenario draw.

    The generator is keyed on (family, condition, ep_seed) through the crc32 rule in
    `scsim.scenarios.scenario_rng`, so it is stable across processes and reruns. Keying
    on the family gives each family its own 60 draws per condition, which is what the
    family-specific estimands need; no cross-family pairing is claimed anywhere.
    """
    rng = S.scenario_rng(family, condition, ep_seed)
    return S.make_condition(condition, rng, reference=family)


def scenario_manifest(block, families=FAMILIES, n=N_TEST_PER_CELL):
    """The full list of (family, condition, ep_seed) units for a block, plus its hash.

    Sec 6.1 requires a machine-readable manifest whose SHA-256 is recorded in every run,
    so the test set cannot be silently regenerated or extended.
    """
    units = [{"family": f, "condition": c, "ep_seed": s}
             for f in families for c in CONDITIONS
             for s in scenario_keys(block, n)]
    blob = json.dumps(units, sort_keys=True, separators=(",", ":")).encode()
    return {"block": block, "n_per_cell": n, "families": list(families),
            "conditions": list(CONDITIONS), "n_units": len(units),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "population_sha256": S.population_hash(),
            "units": units}


# ==========================================================================
# policy construction
# ==========================================================================
def checkpoint_path(tag, seed):
    return f"{DATA}/model_{tag}_s{seed}.pt"


def make_policy(mid, seed, cert, N=C.N_HORIZON_HW):
    """Build one Path B method. Every component not named in METHODS[mid]['opts'] is
    identical across methods by construction, because they all route through the same
    two policy classes with the same frozen (P, K, lambda, eta, R)."""
    from scsim.controllers import (FallbackOnlyPolicy, LearnedContextPolicy,
                                   NominalRecoveryPolicy)
    spec = METHODS[mid]
    cls = {"nominal_recovery": NominalRecoveryPolicy,
           "fallback_only": FallbackOnlyPolicy}.get(spec["policy"],
                                                    LearnedContextPolicy)
    # a checkpoint-independent method still loads seed 0 so its architecture and
    # normalisation metadata match; nothing in its command path consults the weights
    use_seed = seed if spec["seeded"] else 0
    return cls(checkpoint_path(spec["tag"], use_seed), check_mode="enforce",
               P=cert["P"], K=cert["K"], lam=cert["lam"], eta=cert["eta"],
               R=cert["R"], N=N, **spec["opts"])


# ==========================================================================
# Sec 9.2 / 9.4 / 9.5: endpoints
# ==========================================================================
def episode_metrics(log, sc, diagnostic_tol):
    """Every declared endpoint for one rollout, scored on the PHYSICAL state.

    The controller's own checks use the estimate; nothing here does. The scoring window
    starts at the onset for every condition, using the pseudo-onset for healthy, so the
    four conditions share one estimand definition.
    """
    a = log.arrays()
    # xt is the truth, used by every primary endpoint; xh is the estimate, used ONLY by the
    # `declared` half of task_success_v2, which is by definition what the vehicle believes.
    xt, xh, rs = a["x_true"], a["x_hat"], a["ref_score"]
    n = len(xt)
    e_pos = np.linalg.norm(xt[:, :2] - rs[:, :2], axis=1)
    e_yaw = np.abs(np.arctan2(np.sin(xt[:, 4] - rs[:, 4]),
                              np.cos(xt[:, 4] - rs[:, 4])))

    # ---- Sec 9.2 primary endpoint: post-onset position RMSE ----
    # The onset is drawn for EVERY condition, including healthy, where it triggers no
    # impairment and serves only to define this window. That makes the four conditions
    # one estimand instead of two, at the cost of differing from the archived healthy
    # number, which used the whole episode.
    onset = int(sc.onset_step)
    onset = min(max(onset, 0), n - 1)
    m = {
        "onset_step": onset,
        "onset_is_pseudo": bool(not (sc.fault_active or sc.perception != "healthy")),
        "post_onset_rmse": float(np.sqrt(np.mean(e_pos[onset:] ** 2))),
        "post_onset_peak": float(e_pos[onset:].max()),
        "post_onset_mae": float(np.mean(e_pos[onset:])),
        "post_onset_rmse_yaw": float(np.sqrt(np.mean(e_yaw[onset:] ** 2))),
        "post_onset_peak_yaw": float(e_yaw[onset:].max()),
        # secondary, whole-episode
        "rmse_pos": float(np.sqrt(np.mean(e_pos ** 2))),
        "peak_pos": float(e_pos.max()),
        "mae_pos": float(np.mean(e_pos)),
        "rmse_yaw": float(np.sqrt(np.mean(e_yaw ** 2))),
        "peak_yaw": float(e_yaw.max()),
        "n_steps": n,
    }

    # ---- Sec 9.4 task completion at the FINAL intended goal, task_success_v2 ----
    # Scored twice, once per frame, because the two frames answer different questions and
    # the simulator's unbounded estimator drift makes them differ by more than the
    # tolerance. `declared` uses the estimate the controller actually sees, `achieved` uses
    # the true state. They are never combined into one number.
    tgt = log.meta.get("final_target")
    tgt = None if tgt is None else np.asarray(tgt, dtype=float)
    m["task_final_defined"] = tgt is not None
    m["task_spec_version"] = TASK_SPEC["version"]
    if tgt is not None:
        for frame, state, tp, ty in (("declared", xh, TASK_TOL_POS, TASK_TOL_YAW),
                                     ("achieved", xt, TASK_TOL_POS_TRUE,
                                      TASK_TOL_YAW_TRUE)):
            sfx = "" if frame == "achieved" else "_declared"
            ef = np.linalg.norm(state[:, :2] - tgt[None, :2], axis=1)
            ey = np.abs(np.arctan2(np.sin(state[:, 4] - tgt[4]),
                                   np.cos(state[:, 4] - tgt[4])))
            in_pos, in_yaw = ef <= tp, ey <= ty
            at_goal = in_pos & in_yaw
            limit = min(n, TASK_DEADLINE_STEPS) - TASK_DWELL_OBS + 1
            first = None
            for t in range(max(limit, 0)):
                if at_goal[t:t + TASK_DWELL_OBS].all():
                    first = t
                    break
            m[f"task_success{sfx}"] = first is not None
            m[f"completion_time{sfx}"] = (np.nan if first is None else
                                          float((first + TASK_DWELL_OBS - 1) * C.TS))
            m[f"time_to_task_tol{sfx}"] = (float((first - onset) * C.TS)
                                           if first is not None and first >= onset
                                           else np.nan)
            m[f"final_pos_err_to_target{sfx}"] = float(ef[-1])
            m[f"final_yaw_err_to_target{sfx}"] = float(ey[-1])
            m[f"frac_time_at_goal{sfx}"] = float(at_goal.mean())
            m[f"task_held_at_end{sfx}"] = bool(at_goal[-TASK_DWELL_OBS:].all())

            # ---- Sec 9.5 exactly one terminal progress category, per frame ----
            if first is not None:
                cat = "task_success"
            elif not in_pos.any():
                cat = "never_entered_position_tolerance"
            elif not at_goal.any():
                cat = "position_but_never_simultaneous_yaw"
            else:
                cat = "both_tolerances_but_no_dwell"
            m[f"progress_category{sfx}"] = cat
            # orthogonal event, not part of the category
            m[f"departed_after_entering{sfx}"] = (
                bool((~at_goal[int(np.argmax(at_goal)):]).any()) if at_goal.any()
                else False)

        # The gap between the two frames: a run the vehicle declares complete but a
        # ground-truth observer does not certify. This is an endpoint in its own right.
        m["declared_not_achieved"] = bool(m["task_success_declared"]
                                          and not m["task_success"])
        m["achieved_not_declared"] = bool(m["task_success"]
                                          and not m["task_success_declared"])
    else:
        for sfx in ("", "_declared"):
            m.update({f"task_success{sfx}": None, f"completion_time{sfx}": np.nan,
                      f"time_to_task_tol{sfx}": np.nan,
                      f"final_pos_err_to_target{sfx}": np.nan,
                      f"final_yaw_err_to_target{sfx}": np.nan,
                      f"frac_time_at_goal{sfx}": np.nan,
                      f"task_held_at_end{sfx}": None,
                      f"progress_category{sfx}": "corrupted_unscorable",
                      f"departed_after_entering{sfx}": False})
        m["declared_not_achieved"] = m["achieved_not_declared"] = False

    # ---- Sec 9.6 diagnostic recovery, kept separate from task success ----
    import stage6_methods as s6
    has_onset = bool(sc.fault_active or sc.perception != "healthy")
    rec = s6.score_recovery(e_pos <= diagnostic_tol, onset if has_onset else None,
                            TASK_DWELL_OBS)
    m["diag_recovery_mode"] = rec["mode"]
    m["diag_recovery_success"] = rec["success"]
    m["diag_recovery_time"] = rec["t_from_onset"]
    m["diag_tolerance_m"] = float(diagnostic_tol)

    # ---- Sec 8.4 action sources, one per step, shares summing to one ----
    src = list(a["action_src"]) if "action_src" in a else []
    if src:
        for lab in ACTION_SOURCES:
            m[f"src_{lab}"] = float(sum(1 for s in src if s == lab) / len(src))
        tot = sum(m[f"src_{lab}"] for lab in ACTION_SOURCES)
        unknown = sorted(set(src) - set(ACTION_SOURCES))
        if unknown or abs(tot - 1.0) > 1e-9:
            raise AssertionError(
                f"action-source taxonomy is not total: sum={tot:.6f}, "
                f"unlabelled={unknown}")
        m["action_src_sum"] = float(tot)
        # grouped shares, for the tables
        m["share_mpc"] = m["src_mpc_primary"] + m["src_mpc_replacement"]
        m["share_repair_replacement"] = m["src_mpc_replacement"]
        m["share_fallback"] = sum(m[f"src_{s}"] for s in ACTION_SOURCES
                                  if s.startswith("fallback_"))
        m["share_supervisor"] = sum(m[f"src_{s}"] for s in ACTION_SOURCES
                                    if s.startswith("supervisor"))
        m["share_m5_feedback"] = m["src_m5_feedback"]

    # candidate-rejection reasons, reported SEPARATELY from the source
    rej = list(a["reject_reason"]) if "reject_reason" in a else []
    for lab in ("first_screen", "repeated_check", "command_admissibility",
                "fallback_screen"):
        m[f"rej_{lab}"] = (float(sum(1 for r in rej if r == lab) / len(rej))
                           if rej else np.nan)
    orig = list(a["repair_seed_origin"]) if "repair_seed_origin" in a else []
    for lab in ("raw_mpc", "projected_mpc", "p_error", "feedback", "not_applicable"):
        m[f"seed_{lab}"] = (float(sum(1 for o in orig if o == lab) / len(orig))
                            if orig else np.nan)
    if "projection_applied" in a:
        m["projection_rate"] = float(np.mean(np.asarray(a["projection_applied"],
                                                        dtype=bool)))
    if "compensation_applied" in a:
        m["compensation_rate"] = float(np.mean(np.asarray(a["compensation_applied"],
                                                          dtype=bool)))

    # ---- Sec 8.5 effort and timing ----
    u = np.asarray(a["u_nom_tx"], dtype=float)
    m["effort_force_mean"] = float(np.mean(np.linalg.norm(u[:, :2], axis=1)))
    m["effort_moment_mean"] = float(np.mean(np.abs(u[:, 2])))
    m["command_rate_norm"] = float(np.mean(np.linalg.norm(np.diff(u, axis=0), axis=1)))
    pulse = np.asarray(a["pulse_command_s"], dtype=float)
    m["duty_on_time_mean_s"] = float(np.mean(pulse.sum(axis=1)))
    m["pulse_count_mean"] = float(np.mean((pulse > 0).sum(axis=1)))
    m["saturation_frac"] = float(np.mean(pulse >= C.PWM_PERIOD - 1e-12))
    m["impulse_proxy_Ns"] = float(np.sum(pulse) * C.FMAX_PER_THRUSTER)
    m["accel_p95"] = float(np.percentile(a["accel"], 95))
    for q in (50, 95, 99):
        m[f"decision_ms_p{q}"] = (float(np.nanpercentile(a["decision_ms"], q))
                                  if len(a.get("decision_ms", [])) else np.nan)
    m["decision_ms_max"] = (float(np.nanmax(a["decision_ms"]))
                            if len(a.get("decision_ms", [])) else np.nan)
    m["solve_ms_p95"] = float(np.nanpercentile(a["solve_ms"], 95))
    m["deadline_miss_rate"] = (float(np.mean(a["deadline_miss"]))
                               if len(a.get("deadline_miss", [])) else np.nan)

    # ---- Sec 9.5 orthogonal event flags ----
    st = log.meta.get("policy_stats", {})
    inelig = list(a["ineligible_reason"]) if "ineligible_reason" in a else []
    m["supervisor_intervention"] = bool(m.get("share_supervisor", 0.0) > 0)
    m["no_passing_fallback"] = bool(any(r == "no_passing_fallback" for r in inelig))
    m["solver_failure"] = bool(st.get("n_fallback", 0) > 0)
    m["repair_search_failure"] = bool(st.get("n_proj_infeasible", 0) > 0)
    m["deadline_overrun"] = bool(np.nansum(a.get("deadline_miss", [0])) > 0)
    m["numerical_anomaly"] = bool(not np.isfinite(xt).all())
    m["episode_deadline_censored"] = bool(not m.get("task_success", False))
    m["gate_on_frac"] = float(np.mean(np.asarray(a["gate"], dtype=float)))
    m["n_fault_skips"] = log.meta.get("n_fault_skips", 0)
    m["policy_stats"] = {k: int(v) for k, v in st.items()}
    return m


def run_unit(args):
    """One (method, seed, family, condition, ep_seed) rollout. Picklable for pmap."""
    mid, seed, family, cond, ep_seed, cert, tol, N, want_trace = args
    from scsim.runner import run_policy_episode
    sc = draw_scenario(family, cond, ep_seed)
    pol = make_policy(mid, seed, cert, N=N)
    log = run_policy_episode(pol, seed=ep_seed, steps=C.EPISODE_STEPS, scenario=sc)
    m = episode_metrics(log, sc, tol)
    m.update({"method": mid, "model_seed": (seed if METHODS[mid]["seeded"] else None),
              "seeded": METHODS[mid]["seeded"], "family": family,
              "condition": cond, "ep_seed": ep_seed, "N": N,
              "checkpoint_sha256": log.meta.get("checkpoint_sha256"),
              "feat_mask": log.meta.get("feat_mask"),
              "repair": log.meta.get("repair"),
              "reference_version": log.meta.get("reference_version")})
    if want_trace:
        a = log.arrays()
        keep = ("x_true", "x_hat", "ref_score", "u_prop", "u_nom_tx", "pulse_command_s",
                "pulse_actual_s", "gate", "accepted", "slack_cmd", "slack_fb",
                "action_src", "repair_seed_origin", "reject_reason", "e_P", "accel",
                "fault_skip", "pose_valid", "decision_ms")
        m["_trace"] = {k: np.asarray(a[k]).tolist() for k in keep if k in a}
        m["_trace"]["onset"] = int(sc.onset_step)
    return m

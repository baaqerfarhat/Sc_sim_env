"""Closed-loop episode runner.

Information flow is strictly causal and hidden variables never reach the controller
(Simulation_Validation_Protocol Phase C):

  true plant state  ->  VO surrogate observation  ->  controller filter stack
                    ->  estimate  ->  MPC  ->  command chain  ->  plant

The fault schedule, the true state, and the effectiveness are recorded in the
evaluator log only. `hidden` fields are never read by any controller code path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config as C
from . import plant as P
from .estimator import EstimatorStack, VOSurrogate
from .mpc import HardwareMPC
from .reference import make_reference


@dataclass
class EpisodeLog:
    """Per-step records, with the information boundary visible in the field names.

    CONTROLLER-VISIBLE: x_hat, ref, u_prop, u_cmd, u_nom_tx, pulse_command_s,
    F_alloc, use_hist, innov, pose_valid, z_ctx, gate, accepted, slack_*.
    EVALUATOR-ONLY (never an input to a policy, a check or a feature builder):
    x_true, pulse_actual_s, fault_skip, accel, ref_score.
    """
    x_true: list = field(default_factory=list)
    x_hat: list = field(default_factory=list)
    ref: list = field(default_factory=list)
    ref_next: list = field(default_factory=list)
    ref_score: list = field(default_factory=list)
    u_prop: list = field(default_factory=list)
    u_cmd: list = field(default_factory=list)
    u_nom_tx: list = field(default_factory=list)
    pulse_command_s: list = field(default_factory=list)
    pulse_actual_s: list = field(default_factory=list)
    F_alloc: list = field(default_factory=list)
    use_hist: list = field(default_factory=list)
    accel: list = field(default_factory=list)
    solve_ms: list = field(default_factory=list)
    fallback: list = field(default_factory=list)
    fault_skip: list = field(default_factory=list)
    pose_valid: list = field(default_factory=list)
    innov: list = field(default_factory=list)
    z_ctx: list = field(default_factory=list)
    # proposed-method extras
    gate: list = field(default_factory=list)
    accepted: list = field(default_factory=list)
    slack_cmd: list = field(default_factory=list)
    slack_fb: list = field(default_factory=list)
    action_src: list = field(default_factory=list)
    e_P: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def arrays(self):
        out = {}
        for k, v in self.__dict__.items():
            if k == "meta":
                continue
            if len(v) and isinstance(v[0], (list, np.ndarray)):
                out[k] = np.array(v, dtype=float)
            elif len(v):
                out[k] = np.array(v)
        out["meta"] = self.meta
        return out


def run_episode(
    *,
    seed=0,
    steps=C.EPISODE_STEPS,
    reference="step",
    fault_active=False,
    fault_fraction=0.7,
    fault_onset_step=0,
    eta_smooth=None,
    perception="healthy",
    controller=None,
    estimator_on=True,
    duty_ceiling=C.PWM_PERIOD,
    fmax=C.FMAX_PER_THRUSTER,
    fit_offset=C.FIT_OFFSET,
    mass=C.MASS,
    jzz=C.JZZ,
    drag=0.0,
    yaw_damp=0.0,
    x0=None,
    residual_fn=None,
    context_fn=None,
    vo_override=None,
    record=True,
):
    """Run one episode. Returns an EpisodeLog.

    `fault_onset_step` implements the protocol's 15-20 s onset draw. The hardware
    fault itself is a step at t=0 with no schedule; a mid-episode onset is a
    simulation-study choice and is labelled as such in the manifest.
    """
    rng = np.random.default_rng(seed)
    ctrl = controller if controller is not None else HardwareMPC(mass=mass, jzz=jzz)
    N = ctrl.N

    x = np.zeros(6) if x0 is None else np.asarray(x0, dtype=float).copy()
    ref_gen = make_reference(reference, start=x[:2].copy())

    fault = P.DeterministicFault(fault_fraction=fault_fraction, active=False)
    chain = P.CommandChain(fault=fault, duty_ceiling=duty_ceiling, fmax=fmax,
                           fit_offset=fit_offset, eta_smooth=eta_smooth)

    vo = VOSurrogate(rng, mode=perception, override=vo_override)
    est = EstimatorStack()
    # one-shot alignment at t0 against ground truth, then never again (Sec 8)
    est.align(x)

    u_prev = np.zeros(3)
    log = EpisodeLog()
    log.meta = dict(
        seed=seed, reference=reference, fault_active=fault_active,
        fault_fraction=fault_fraction, fault_onset_step=fault_onset_step,
        eta_smooth=None if eta_smooth is None else np.asarray(eta_smooth).tolist(),
        perception=perception, N=N, duty_ceiling=duty_ceiling, fmax=fmax,
        fit_offset=fit_offset, mass=mass, jzz=jzz, drag=drag, yaw_damp=yaw_damp,
        estimator_on=estimator_on, steps=steps,
        manifest_hash=C.manifest_hash(),
    )

    for k in range(steps):
        # ---- fault onset (evaluator-side; the controller is never told) ----
        if fault_active and k == fault_onset_step:
            chain.fault.active = True
        if perception != "healthy":
            vo.set_degraded(k >= fault_onset_step)

        # ---- observation -> estimate (causal) ----
        if estimator_on:
            obs = vo.observe(x, k)
            x_hat = est.update(obs, C.TS)
        else:
            x_hat = x.copy()
            obs = {"valid": True}

        # ---- reference (position-triggered, uses the ESTIMATE not truth) ----
        ref_gen.update(x_hat, k)
        ref_prev = ref_gen.preview(N)

        # ---- learned context and residual ----
        z = None if context_fn is None else context_fn(k, log)
        dres = None if residual_fn is None else residual_fn(x_hat, u_prev, z)

        # ---- MPC ----
        u_star, info = ctrl.solve(x_hat, ref_prev, u_prev, dres)

        # ---- command chain -> plant ----
        # the allocator legitimately uses the ESTIMATE to turn a world-frame wrench
        # request into body commands; the plant below uses TRUE yaw to turn the
        # resulting body force into world acceleration
        u_nom_tx, cinfo = chain(u_star, x_hat[4])
        x_next = P.plant_step(x, cinfo["pulse_actual_s"], valve=C.VALVE_THRUST,
                              eta_smooth=eta_smooth, mass=mass, jzz=jzz,
                              drag=drag, yaw_damp=yaw_damp)
        a_mag = np.hypot(x_next[2] - x[2], x_next[3] - x[3]) / C.TS

        if record:
            log.x_true.append(x.copy())
            log.x_hat.append(x_hat.copy())
            log.ref.append(ref_prev[1].copy())
            log.ref_score.append(ref_gen.scoring_reference(k).copy())
            log.u_prop.append(np.asarray(u_star, dtype=float).copy())
            log.u_cmd.append(cinfo["u_commanded"].copy())
            log.u_nom_tx.append(u_nom_tx.copy())
            log.pulse_command_s.append(cinfo["pulse_command_s"].copy())
            log.pulse_actual_s.append(cinfo["pulse_actual_s"].copy())
            log.F_alloc.append(cinfo["F_alloc"].copy())
            log.use_hist.append(chain.use_hist.copy())
            log.accel.append(a_mag)
            log.solve_ms.append(info.get("solve_time_ms", np.nan))
            log.fallback.append(bool(info.get("fallback", False)))
            log.fault_skip.append(bool(cinfo["fault_skip"]))
            log.pose_valid.append(bool(obs.get("valid", True)))
            log.innov.append(est.innov.copy() if estimator_on else np.zeros(2))
            log.z_ctx.append(np.zeros(C.D_LATENT) if z is None else np.asarray(z))

        u_prev = np.asarray(u_star, dtype=float)
        x = x_next

    log.meta["n_solver_fail"] = ctrl.n_solver_fail
    log.meta["n_retry"] = ctrl.n_retry
    log.meta["switch_step"] = getattr(ref_gen, "switch_step", None)
    log.meta["n_fault_skips"] = chain.fault.n_skips
    return log


def run_policy_episode(policy, *, seed=0, steps=C.EPISODE_STEPS, scenario=None,
                       x0=None, vo_override=None, record=True):
    """Run one episode under a policy object (Algorithm 1 compliant).

    The policy owns MPC, allocation, checking and transmission, so the trial/commit
    discipline is enforced: candidate and fallback are trial-allocated from the same
    frozen allocator memory and only the transmitted one commits its update.
    """
    from .scenarios import Scenario

    sc = scenario if scenario is not None else Scenario("healthy", "healthy")
    rng = np.random.default_rng(seed)

    x = np.zeros(6) if x0 is None else np.asarray(x0, dtype=float).copy()
    ref_gen = make_reference(sc.reference, start=x[:2].copy())

    fault = P.DeterministicFault(sc.fault_fraction, active=False)
    eta_s = None if sc.eta_smooth is None else np.asarray(sc.eta_smooth)
    chain = P.CommandChain(fault=fault, duty_ceiling=sc.duty_ceiling,
                           fmax=sc.fmax, fit_offset=sc.fit_offset,
                           eta_smooth=eta_s)

    vo = VOSurrogate(rng, mode=sc.perception, override=vo_override)
    est = EstimatorStack()
    est.align(x)
    policy.reset(x)

    log = EpisodeLog()
    log.meta = dict(seed=seed, steps=steps, policy=policy.name,
                    scenario=sc.to_dict(), manifest_hash=C.manifest_hash())

    # rolling buffers so the encoder history is built from CONTROLLER-VISIBLE data.
    # u_nom_tx is the nominal-equivalent transmitted wrench: it carries no hidden
    # fault information, which is the whole point of the separation in plant.py.
    hist = {"x_hat": np.zeros((steps, 6)), "u_nom_tx": np.zeros((steps, 3)),
            "pose_valid": np.zeros(steps, dtype=bool),
            "innov": np.zeros((steps, 2))}

    for k in range(steps):
        if sc.fault_active and k == sc.onset_step:
            chain.fault.active = True
        if sc.perception != "healthy":
            vo.set_degraded(k >= sc.onset_step)

        obs = vo.observe(x, k)
        x_hat = est.update(obs, C.TS)
        hist["x_hat"][k] = x_hat
        hist["pose_valid"][k] = bool(obs.get("valid", True))
        hist["innov"][k] = est.innov

        # Sec 4.5: the successor reference is COMMITTED here, before the command,
        # and it is the one used to form e_{k+1} and the transition mismatch. A
        # later position-triggered decision may schedule a new reference but must
        # not retroactively replace this committed sample.
        ref_gen.update(x_hat, k)
        ref_prev = ref_gen.preview(policy.mpc.N)
        r_committed_next = ref_prev[1].copy()

        out = policy.act(k, x_hat, ref_prev, chain, hist)
        hist["u_nom_tx"][k] = out["u_nominal_transmitted"]

        pulse_actual, skipped = chain.apply_hidden(out)
        out["pulse_actual_s"], out["fault_skip"] = pulse_actual, skipped
        x_next = P.plant_step(x, pulse_actual, eta_smooth=eta_s,
                              mass=sc.mass, jzz=sc.jzz, drag=sc.drag,
                              yaw_damp=sc.yaw_damp)
        a_mag = np.hypot(x_next[2] - x[2], x_next[3] - x[3]) / C.TS

        if record:
            log.x_true.append(x.copy())
            log.x_hat.append(x_hat.copy())
            log.ref.append(ref_prev[1].copy())
            log.ref_score.append(ref_gen.scoring_reference(k).copy())
            log.ref_next.append(r_committed_next)
            log.u_prop.append(np.asarray(out["u_prop"], dtype=float).copy())
            log.u_cmd.append(out["u_commanded"].copy())
            log.u_nom_tx.append(out["u_nominal_transmitted"].copy())
            log.pulse_command_s.append(out["pulse_command_s"].copy())
            log.pulse_actual_s.append(pulse_actual.copy())
            log.F_alloc.append(out["F_alloc"].copy())
            log.use_hist.append(chain.use_hist.copy())
            log.accel.append(a_mag)
            log.solve_ms.append(out.get("solve_ms", np.nan))
            log.fallback.append(bool(out.get("fallback", False)))
            log.fault_skip.append(bool(out["fault_skip"]))
            log.pose_valid.append(bool(obs.get("valid", True)))
            log.innov.append(est.innov.copy())
            z = out.get("z")
            log.z_ctx.append(np.zeros(C.D_LATENT) if z is None else np.asarray(z))
            log.gate.append(int(out.get("gate", 1)))
            log.accepted.append(bool(out.get("accepted", True)))
            log.slack_cmd.append(float(out.get("slack_cmd", np.nan)))
            log.slack_fb.append(float(out.get("slack_fb", np.nan)))
            # which controller actually produced the transmitted action
            log.action_src.append(str(out.get("action_src", "candidate")))
            log.e_P.append(float(out.get("e_P", np.nan)))

        x = x_next

    log.meta.update({"switch_step": getattr(ref_gen, "switch_step", None),
                     "n_fault_skips": chain.fault.n_skips,
                     "policy_stats": dict(policy.stats),
                     "has_recovery": bool(getattr(policy, "has_recovery", False)),
                     "check_mode": getattr(policy, "check_mode", "off")})
    return log

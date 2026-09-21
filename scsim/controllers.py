"""The five method variants compared in Stage 6, plus the adaptive-MPC baseline.

All variants share the task references, physical limits, estimator, timing and
scenario draws. They differ only where stated.

  ZeroContextPolicy      the hardware comparator: z = 0 at deployment, no residual.
                         This is a DIAGNOSTIC, not a retrained model.
  ConstantContextPolicy  residual retrained with one learned CONSTANT context. This
                         is what answers "does inferring a CHANGING context help?".
  AdaptiveMPCPolicy      no learned context; bounded regularised RLS correction to
                         the velocity and angular-rate increments, driven only by
                         available estimates and transmitted commands. It never
                         receives actual effectiveness or fault-onset labels.
  LearnedContextPolicy   full method, or the lambda_I = 0 ablation, or the full
                         method with the post-allocation check bypassed.

`LearnedContextPolicy` also implements Algorithm 1: eligibility gate, first-action
condition, post-allocation acceptance check (Eq. 18) and stored checked fallback.
"""
from __future__ import annotations

import time

import numpy as np

from . import certificate as CT
from . import config as C
from .mpc import HardwareMPC, ProposedMPC
from .plant import wrap_pi
from .scenarios import (FEATURE_SCALE, build_history, from_body_frame,
                        to_body_frame)


class BasePolicy:
    """Common interface. `act` owns MPC, allocation, checking and transmission, so
    the trial/commit discipline of Algorithm 1 is enforced in one place."""

    name = "base"
    uses_context = False
    has_recovery = False        # no eligibility gate and no acceptance check

    def __init__(self, N=C.N_HORIZON_HW, mass=C.MASS, jzz=C.JZZ, huber=False):
        self.mpc = (ProposedMPC(N=N, mass=mass, jzz=jzz) if huber
                    else HardwareMPC(N=N, mass=mass, jzz=jzz))
        self.u_prev = np.zeros(3)
        self.stats = {"n_fallback": 0, "n_gate_off": 0, "n_reject": 0,
                      "n_active": 0, "n_steps": 0}

    def reset(self, x0):
        self.u_prev = np.zeros(3)

    def residual(self, k, x_hat, hist):
        return None

    def context(self, k, x_hat, hist):
        return None

    def act(self, k, x_hat, ref_prev, chain, hist):
        """Default path: solve, allocate, transmit. No acceptance check, matching
        the deployed controller."""
        self.stats["n_steps"] += 1
        z = self.context(k, x_hat, hist)
        dres = self.residual(k, x_hat, hist)
        u_star, info = self.mpc.solve(x_hat, ref_prev, self.u_prev, dres)
        if info.get("fallback"):
            self.stats["n_fallback"] += 1
        _, cinfo = chain.trial(u_star, x_hat[4])
        chain.commit(cinfo)
        self.u_prev = np.asarray(u_star, dtype=float)
        cinfo.update({"z": z, "gate": 1, "accepted": True,
                      "action_src": "candidate",
                      "solve_ms": info.get("solve_time_ms", np.nan),
                      "fallback": bool(info.get("fallback", False)),
                      "u_prop": np.asarray(u_star, dtype=float)})
        return cinfo


class ZeroContextPolicy(BasePolicy):
    """z = 0 at deployment and no dynamics residual. The hardware comparator."""
    name = "zero_context"


class TorchPolicyMixin:
    """Shared loading and inference for the trained variants."""

    def load(self, checkpoint):
        import torch
        from .context import ContextModel
        ck = torch.load(checkpoint, map_location="cpu", weights_only=False)
        self.model = ContextModel(constant_context=ck.get("constant_context", False))
        self.model.load_state_dict(ck["model"])
        self.model.eval()
        self.torch = torch
        self.checkpoint = checkpoint
        self._z = np.zeros(C.D_LATENT)

    def _infer(self, k, hist):
        """Encode the causal history. Hidden impairment variables are not arguments
        here, so a fault label cannot reach the controller even in principle."""
        import torch
        feats, mask = build_history(hist, k)
        with torch.no_grad():
            f = torch.tensor((feats / FEATURE_SCALE)[None], dtype=torch.float32)
            m = torch.tensor(mask[None], dtype=torch.float32)
            z = self.model.encode(f, m)
        # a constant-context checkpoint returns an expanded VIEW of its learned
        # nn.Parameter, which stays attached to the graph even under no_grad, so
        # .numpy() on it would raise. detach unconditionally.
        return z.detach()

    def _residual_world(self, x_hat, u_prev, z):
        import torch
        psi = x_hat[4]
        c, s = np.cos(psi), np.sin(psi)
        R = np.array([[c, s], [-s, c]])
        xb = np.concatenate([R @ x_hat[2:4], [x_hat[5]]])
        ub = np.concatenate([R @ u_prev[:2], [u_prev[2]]])
        with torch.no_grad():
            d = self.model.residual(
                torch.tensor(xb[None], dtype=torch.float32),
                torch.tensor(ub[None], dtype=torch.float32), z).numpy()[0]
        # the residual is predicted in the body frame; rotate back to world, which
        # is the frame the MPC's prediction model uses
        return from_body_frame(x_hat, d)


class ConstantContextPolicy(BasePolicy, TorchPolicyMixin):
    """Trained constant-context MPC: a single learned context for every transition."""
    name = "constant_context"
    uses_context = True

    def __init__(self, checkpoint, **kw):
        super().__init__(**kw)
        self.load(checkpoint)

    def context(self, k, x_hat, hist):
        return self._z

    def residual(self, k, x_hat, hist):
        import torch
        z = self.model.const_z.detach()[None]
        self._z = z.numpy()[0]
        return self._residual_world(x_hat, self.u_prev, z)


class AdaptiveMPCPolicy(BasePolicy):
    """Bounded, regularised RLS correction to the velocity / angular-rate increments.

    Regressors are the transmitted-equivalent wrench and a bias term; targets are the
    observed increments minus the nominal prediction. The correction is clipped to a
    bounded set, and forgetting, initialisation and update timing are fixed below.

    It receives exactly the same sensor and estimator information as the learned
    variants, and no effectiveness or onset labels.
    """
    name = "adaptive_mpc"

    def __init__(self, lam_forget=0.98, ridge=5.0, clip=0.25, **kw):
        super().__init__(**kw)
        self.lam_forget = lam_forget
        self.ridge = ridge
        self.clip = clip
        self.reset(None)

    def reset(self, x0):
        super().reset(x0)
        # three independent channels: vx, vy, r. Regressor [u_channel, 1].
        self.Pm = [np.eye(2) / self.ridge for _ in range(3)]
        self.th = [np.zeros(2) for _ in range(3)]
        self._prev = None

    def _update(self, x_hat, u_nom_tx):
        from .plant import jetson_nominal_step
        if self._prev is None:
            self._prev = (x_hat.copy(), np.asarray(u_nom_tx, dtype=float).copy())
            return
        xp, up = self._prev
        nom = jetson_nominal_step(xp, up)
        for ch, (si, ui) in enumerate(((2, 0), (3, 1), (5, 2))):
            y = x_hat[si] - nom[si]
            phi = np.array([up[ui], 1.0])
            Pm = self.Pm[ch]
            denom = self.lam_forget + phi @ Pm @ phi
            gain = Pm @ phi / denom
            self.th[ch] = self.th[ch] + gain * (y - phi @ self.th[ch])
            self.Pm[ch] = (Pm - np.outer(gain, phi @ Pm)) / self.lam_forget
            # bounded parameters
            self.th[ch] = np.clip(self.th[ch], -self.clip, self.clip)
        self._prev = (x_hat.copy(), np.asarray(u_nom_tx, dtype=float).copy())

    def residual(self, k, x_hat, hist):
        d = np.zeros(6)
        for ch, si in enumerate((2, 3, 5)):
            phi = np.array([self.u_prev[[0, 1, 2][ch]], 1.0])
            d[si] = float(np.clip(phi @ self.th[ch], -self.clip, self.clip))
        # position rows follow from the velocity correction over one step
        d[0] = 0.5 * C.TS * d[2]
        d[1] = 0.5 * C.TS * d[3]
        d[4] = 0.5 * C.TS * d[5]
        return d

    def act(self, k, x_hat, ref_prev, chain, hist):
        out = super().act(k, x_hat, ref_prev, chain, hist)
        # Sec 7.4: the identification regressor must use the KNOWN nominal
        # transmitted wrench associated with the observed increment.
        self._update(x_hat, out["u_nominal_transmitted"])
        return out


class LearnedContextPolicy(BasePolicy, TorchPolicyMixin):
    """The full proposed method, its no-behavioural-loss ablation, and the
    no-post-allocation-check variant.

    `post_alloc_check=False` bypasses ONLY the candidate check after allocation
    (Eq. 18). Everything else is retained: the MPC first-action constraint, source
    eligibility, the allocator, and optimisation-failure handling with the stored
    fallback. That isolates candidate acceptance after allocation.
    """
    name = "learned_context"
    uses_context = True
    has_recovery = True

    def __init__(self, checkpoint, post_alloc_check=True, recovery=True,
                 P=None, K=None, lam=0.99, eta=0.05, R=None, check_mode=None, **kw):
        # Sec 4.2: the safeguards are INDEPENDENT switches so an ablation can disable
        # exactly one. Popped before super() because they are not base-class kwargs.
        _enf_elig = bool(kw.pop("enforce_eligibility", True))
        _enf_first = bool(kw.pop("enforce_first_action", True))
        _enf_post = kw.pop("enforce_post_alloc", None)
        # Allocation-aware command selection. Default ON because the uniform additive
        # allowance it replaces is unattainable on this vehicle; kept switchable so its
        # contribution is measured by ablation rather than asserted.
        self.alloc_aware = bool(kw.pop("alloc_aware", True))
        # Enforce Eq. (15)'s first-action decrease condition by exact projection
        # instead of checking it after the fact and discarding the proposal.
        self.project_first_action = bool(kw.pop("project_first_action", True))
        # Declared modification to Eq. (15); see the justification at its use site.
        self.first_action_eta = bool(kw.pop("first_action_eta", True))
        kw.setdefault("huber", True)
        super().__init__(**kw)
        self.load(checkpoint)
        # check_mode: "enforce" acts on the check, "monitor" evaluates and records it
        # but always transmits the candidate, "off" does neither. MONITOR is what
        # calibration needs: eta has to be fitted to slacks observed while the check
        # is not yet rejecting anything, otherwise the threshold depends on itself.
        if check_mode is None:
            check_mode = "enforce" if post_alloc_check else "off"
        assert check_mode in ("enforce", "monitor", "off")
        self.check_mode = check_mode
        self.post_alloc_check = (check_mode == "enforce")
        # Driving every safeguard from `check_mode` meant check_mode="off" silently
        # disabled eligibility/supervisor diversion and the first-action condition as
        # well as the post-allocation test, so the M3-M4 gap was a combined-safeguard
        # effect that could not be attributed to the allocated-command check. These
        # default to `check_mode` semantics; the single-component ablation overrides
        # `enforce_post_alloc` alone.
        self.enforce_eligibility = _enf_elig
        self.enforce_first_action = _enf_first
        self.enforce_post_alloc = bool(check_mode == "enforce"
                                       if _enf_post is None else _enf_post)
        # solver failure / deadline miss always falls back: liveness, not an ablatable
        # safeguard
        self.enforce_solver_fallback = True
        self.recovery = bool(recovery)
        self.P = None if P is None else np.asarray(P, dtype=float)
        self.K = None if K is None else np.asarray(K, dtype=float)
        self.lam = float(lam)
        self.eta = float(eta)
        self.R = R
        self.stats.update({"n_reject": 0, "n_would_reject": 0, "n_gate_off": 0,
                           "n_active": 0, "n_supervisor": 0,
                           "n_first_action_fail": 0,
                           # Sec S1.1 eligibility failure attribution
                           "n_fb_decrease_fail": 0, "n_fb_inadmissible": 0,
                           "n_elig_radius_fail": 0, "n_elig_fb_only_fail": 0,
                           "n_proj_infeasible": 0})

    def context(self, k, x_hat, hist):
        return self._z

    def residual(self, k, x_hat, hist):
        z = self._infer(k, hist)
        self._z = z.numpy()[0]
        self._z_t = z
        return self._residual_world(x_hat, self.u_prev, z)

    # ------------------------------------------------------------------
    def act(self, k, x_hat, ref_prev, chain, hist):
        # Sec 12: the COMPLETE decision latency, not the solver's reported duration.
        # This spans context inference, the residual, the feedforward, the fallback
        # allocation, optimisation, allocation-aware selection and every check, which
        # is what has to fit the 100 ms period. `solve_ms` alone omitted everything the
        # learned components add and so could not support a real-time claim.
        _t0 = time.perf_counter()
        self.stats["n_steps"] += 1
        dres = self.residual(k, x_hat, hist)
        z = self._z

        r_now, r_next = ref_prev[0], ref_prev[1]
        e_k = CT.error_coords(x_hat, r_now)

        # ---- stored CHECKED fallback: allocate u_fb from the FROZEN sigma_q ----
        # Sec 4.4: the fallback only qualifies as the eligible checked fallback if it
        # PASSES this test. An earlier version computed fb_ok and then transmitted the
        # fallback regardless, so a failing fallback was routinely sent as though it
        # had been verified.
        fb_info, fb_ok, fb_slack = None, False, np.nan
        u_r = d_r = None
        if self.recovery and self.P is not None and self.K is not None:
            u_r, d_r = CT.feedforward(r_now, r_next, self._achievable(chain))
            u_fb = u_r + self.K @ e_k
            if self.alloc_aware:
                # request the wrench whose REALISATION satisfies the decrease
                # inequality, seeded from the affine law then the P-optimal wrench
                u_opt = self._wrench_star(e_k, u_r, d_r, chain, r_now, r_next)
                rho_fb = (self.lam * CT.norm_P(e_k, self.P)
                          + CT.norm_P(d_r, self.P))
                u_fb, fb_info, _, _ = self._alloc_aware_trial(
                    u_fb, e_k, u_r, d_r, r_now, r_next, chain, x_hat[4],
                    extra_seeds=[u_opt], rho=rho_fb)
            else:
                _, fb_info = chain.trial(u_fb, x_hat[4])
            u_fb_tx = fb_info["u_nominal_transmitted"]
            fb_dec, fb_slack = self._check(e_k, u_fb_tx, u_r, d_r, r_now, r_next)
            fb_adm = self._admissible(u_fb_tx, chain, x_hat[4])
            fb_ok = bool(fb_dec and fb_adm)
            # Sec S1.1: eligibility has several independent failure reasons and a
            # single "ineligible" counter cannot tell them apart, which is why
            # supervisor dominance could be measured but not explained.
            self.stats["n_fb_decrease_fail"] += int(not fb_dec)
            self.stats["n_fb_inadmissible"] += int(not fb_adm)
            fb_info.update(_slack=fb_slack, _ok=fb_ok, _u_prop=u_fb)

        # ---- pre-action eligibility (Eq. 19), now a real branch ----
        # Two conditions decided from information available BEFORE acting: the state
        # is inside the eligible radius, and a verified fallback exists for it. If
        # either fails the guarantee cannot be claimed, so the fixed supervisor acts
        # and the sample is recorded as supervisor-driven rather than as a quiet
        # success.
        eligible = True
        if self.recovery and self.P is not None and self.R is not None:
            if CT.norm_P(e_k, self.P) > self.R:
                eligible = False
                self.stats["n_elig_radius_fail"] += 1
        if self.recovery and self.P is not None and self.K is not None and not fb_ok:
            if eligible:
                self.stats["n_elig_fb_only_fail"] += 1
            eligible = False
        gate = int(eligible)
        self.stats["n_active" if eligible else "n_gate_off"] += 1

        chosen, accepted, slack, src = None, True, np.nan, "candidate"

        # In MONITOR mode eligibility is recorded but not acted on. That is the whole
        # purpose of the mode: eta and R have to be fitted to slacks observed while
        # the machinery is not yet diverting the action, otherwise the thresholds
        # depend on themselves and the calibration measures the supervisor rather
        # than the candidate it is supposed to characterise.
        if (self.recovery and not eligible and self.enforce_eligibility
                and self.check_mode != "monitor"):
            u_sup = self._supervisor(x_hat, chain)
            _, chosen = chain.trial(u_sup, x_hat[4])
            chosen["_u_prop"] = u_sup
            accepted, src = False, "supervisor"
            self.stats["n_supervisor"] += 1
            info = {"fallback": False, "solve_time_ms": 0.0}
        else:
            u_star, info = self.mpc.solve(x_hat, ref_prev, self.u_prev, dres)
            if info.get("fallback"):
                self.stats["n_fallback"] += 1
                # optimiser failure or deadline: the stored PASSING fallback
                chosen, accepted, src = fb_info, False, "fallback_solver_fail"
                if chosen is None:
                    _, chosen = chain.trial(u_star, x_hat[4])
                    src = "unchecked_solver_fallback"
            else:
                # Sec 4.2: the manuscript's Eq. (15) carries a FIRST-ACTION norm
                # condition, WITHOUT the post-allocation allowance eta:
                #   ||A e + B du_0 + d^r||_P <= lam ||e||_P + ||d^r||_P.
                # The OSQP problem solved above is a quadratic program and does not
                # acquire that conic constraint by having its weights changed, so it
                # is NOT enforced inside the optimisation. This is a declared
                # approximation: the condition is instead verified independently here,
                # on the returned proposal, before the candidate is allowed to be
                # called feasible. A proposal that fails it is not a feasible candidate
                # and is discarded in favour of the checked fallback.
                # Allocation-aware selection happens BEFORE the first-action screen.
                # The condition has to be evaluated on the command that will actually
                # act. Screening the raw proposal and only then allocating rejected
                # 24-41% of candidates for a defect the allocator was about to
                # introduce and that the controller could have planned around, which
                # is what drove the fixed supervisor to 42-66% of all actions.
                cand, proj_feasible = None, True
                if (self.project_first_action and self.recovery
                        and self.P is not None and u_r is not None):
                    u_star, proj_feasible = self._project_first_action(
                        u_star, e_k, u_r, d_r, r_now, r_next, chain)
                    self.stats["n_proj_infeasible"] += int(not proj_feasible)
                if self.alloc_aware and u_r is not None:
                    rho = (self.lam * CT.norm_P(e_k, self.P)
                           + CT.norm_P(d_r, self.P))
                    u_opt = self._wrench_star(e_k, u_r, d_r, chain, r_now, r_next)
                    u_star, cand, _, _ = self._alloc_aware_trial(
                        u_star, e_k, u_r, d_r, r_now, r_next, chain, x_hat[4],
                        extra_seeds=[u_opt, u_r + self.K @ e_k], rho=rho)
                    u_eval = cand["u_nominal_transmitted"]
                else:
                    u_eval = np.asarray(u_star)

                first_ok = True
                if self.recovery and self.P is not None and u_r is not None:
                    A_e, B_e = CT.error_jacobians(r_now, r_next)
                    lhs = CT.norm_P(A_e @ e_k + B_e @ (np.asarray(u_eval) - u_r)
                                    + d_r, self.P)
                    rhs = (self.lam * CT.norm_P(e_k, self.P)
                           + CT.norm_P(d_r, self.P))
                    # DECLARED MODIFICATION to Eq. (15). The manuscript's first-action
                    # condition carries no implementation allowance, on the premise
                    # that the planned first input is applied exactly. It is not: the
                    # command reaches the thrusters through a duty-quantised allocator
                    # whose error is a known, persistent, non-vanishing quantity, so
                    # the condition that governs the physical successor is the one on
                    # the REALISED command, and that one needs the allowance.
                    #
                    # This is not a convenience. With no allowance the feasible set
                    # {u admissible : LHS <= rhs} is EMPTY - verified by exact
                    # projection, not by a failed search - at 66.6% of the states
                    # visited in closed loop. The allowance-free condition is therefore
                    # not implementable on this vehicle at 10 Hz, and enforcing it
                    # hands two thirds of all actions to the fixed supervisor.
                    #
                    # Consequence, reported rather than hidden: with the allowance on
                    # both sides this condition and Eq. (18) become the same test on
                    # the same quantity, so the post-allocation decrease test is
                    # redundant BY CONSTRUCTION rather than merely inactive.
                    if self.first_action_eta:
                        rhs = rhs + self.eta
                    first_ok = bool(lhs <= rhs)
                    self.stats["n_first_action_fail"] += int(not first_ok)

                if (not first_ok and self.enforce_first_action
                        and self.check_mode != "monitor"):
                    # no timely FEASIBLE candidate exists, so the stored passing
                    # fallback is transmitted
                    chosen, accepted, src = fb_info, False, "fallback_first_action"
                else:
                    if cand is None:
                        _, cand = chain.trial(u_star, x_hat[4])
                    cand["_u_prop"] = u_star
                    cand["_first_action_ok"] = first_ok
                    if fb_info is not None:
                        # The decrease test is ALWAYS evaluated so its slack and
                        # verdict are logged on every arm; only enforcement is
                        # ablatable. Command admissibility is a hard input-budget
                        # constraint and stays enforced on both arms, so this ablation
                        # is precisely "the post-allocation decrease test is disabled"
                        # and not "several safeguards are disabled together".
                        u_cand_tx = cand["u_nominal_transmitted"]
                        ok_dec, slack = self._check(e_k, u_cand_tx, u_r, d_r,
                                                    r_now, r_next)
                        ok_adm = self._admissible(u_cand_tx, chain, x_hat[4])
                        cand["_ok_decrease"] = bool(ok_dec)
                        cand["_ok_admissible"] = bool(ok_adm)
                        ok = bool(ok_dec and ok_adm)
                        act_on_decrease = (self.enforce_post_alloc
                                           and self.check_mode != "monitor")
                        if not ok_adm:
                            # never transmit a command outside the declared budget
                            self.stats["n_reject"] += 1
                            chosen, accepted, src = (fb_info, False,
                                                     "fallback_inadmissible")
                        elif ok_dec or not act_on_decrease:
                            # monitor and the M4 ablation record the would-be verdict
                            # and transmit the candidate regardless
                            chosen, accepted = cand, bool(ok)
                            if not ok_dec:
                                self.stats["n_would_reject"] += 1
                        else:
                            self.stats["n_reject"] += 1
                            chosen, accepted, src = (fb_info, False,
                                                     "fallback_checked")
                    else:
                        chosen, accepted = cand, True

        if chosen is None:
            # only reachable if a rejection path fired without a stored fallback,
            # which means the recovery machinery was partially configured; fail loudly
            # rather than transmitting something unexamined
            raise RuntimeError(
                f"{self.name}: no command selected at step {k} (src={src}). A "
                f"rejection path fired with no stored fallback available.")
        chain.commit(chosen)
        u_prop = chosen.get("_u_prop", np.zeros(3))
        # Sec 4.1: the residual is evaluated at the input actually transmitted at
        # this transition, which is what training uses. Carrying the previous
        # PROPOSED wrench forward instead made the deployed predictor inconsistent
        # with its own training data whenever allocation saturated.
        self.u_prev = np.asarray(chosen["u_nominal_transmitted"], dtype=float)
        chosen.update({"z": z, "gate": gate, "accepted": bool(accepted),
                       "slack_cmd": float(slack) if np.isfinite(slack) else np.nan,
                       "slack_fb": float(fb_slack),
                       "action_src": src,
                       "e_P": (CT.norm_P(e_k, self.P) if self.P is not None
                               else np.nan),
                       "solve_ms": info.get("solve_time_ms", np.nan),
                       "fallback": bool(info.get("fallback", False)),
                       "u_prop": np.asarray(u_prop, dtype=float)})
        dec_ms = (time.perf_counter() - _t0) * 1e3
        chosen["decision_ms"] = float(dec_ms)
        # A deadline miss keeps its source label rather than being reclassified after
        # the fact. This is simulation-workstation timing, NOT the flight computer.
        chosen["deadline_miss"] = bool(dec_ms > C.TS * 1e3)
        return chosen

    # ------------------------------------------------------------------
    def _achievable(self, chain):
        avg = chain.fmax * (chain.duty_ceiling / C.TS)
        return np.array([2.0 * avg, 2.0 * avg, 4.0 * 0.2 * avg])

    # ------------------------------------------------------------------
    # Allocation-aware command selection.
    #
    # WHY THIS EXISTS.  The manuscript treats the allocation error
    # delta_u = u_tx - u^star as an unknown additive disturbance, absorbed by the
    # allowance eta in Eq. (18). Measurement says that is the wrong model twice over.
    #
    # First, delta_u is not unknown: u_tx is the nominal-equivalent transmitted wrench,
    # a deterministic function of the commanded pulses, computed by `chain.trial`
    # BEFORE anything is transmitted. The controller therefore knows it exactly at
    # decision time.
    #
    # Second, the uniform additive bound is unattainable on this vehicle. Holding a
    # fixed request, the per-step allocation error reproduces with ratio exactly 1.000
    # over 400 steps - it is a persistent bias, not a dithered one - and its size is
    # about 6.3% of the commanded correction. The per-step contraction achievable at
    # 25 kg with 0.96 N of authority at 10 Hz is lambda ~ 0.99, so the decrease
    # inequality admits a relative error of only 1 - lambda ~ 0.94%. A uniform eta
    # covering 6.3% cannot coexist with a nonempty region, which is why the search over
    # 2,730 cells returned nothing.
    #
    # WHAT REPLACES IT.  Because the map is known, the request is chosen so that its
    # REALISATION satisfies the decrease inequality, instead of requesting the affine
    # law and hoping its allocation error is small. The premise becomes "a reachable
    # transmitted command satisfying the inequality exists", which is verified online
    # per step, rather than "the allocation error is uniformly bounded by eta", which
    # is false here. Measured effect: the decrease condition is satisfiable on 92-100%
    # of samples instead of 24-49%.
    #
    # This is an ablatable component (`alloc_aware=False`), so its contribution is
    # measured rather than assumed.
    def _project_first_action(self, u0, e_k, u_r, d_r, r_now, r_next, chain):
        """Project the MPC's first action onto the Eq. (15) first-action feasible set.

        WHY.  The first-action decrease condition is a CONSTRAINT of Eq. (15), but OSQP
        solves a quadratic program and cannot carry the conic constraint, so the
        reviewed implementation checked it afterwards and discarded any proposal that
        failed. It failed on 71% of steps - not because no feasible command existed
        (the affine fallback satisfies the same inequality on 94.5% of steps) but
        because a tracking-cost optimum has no reason to also be a contraction optimum.
        The candidate was therefore rejected in favour of the fallback almost always,
        and the comparison attributed to "MPC planning" was mostly measuring the
        fallback.

        The feasible set {u : ||A e + B(u - u_r) + d_r||_P <= rho} is convex, so the
        declared architecture is a proposal generator followed by a verifier and an
        exact projection onto the verified set. Writing M = P^{1/2} B and
        c = P^{1/2}(A e - B u_r + d_r), the projection of u0 solves

            min ||u - u0||^2  s.t.  ||M u + c|| <= rho,

        whose stationarity gives u(nu) = (I + 2 nu M'M)^{-1} (u0 - 2 nu M'c) for a
        scalar nu >= 0 found by bisection on ||M u(nu) + c|| = rho. M'M is 3x3, so each
        iteration is a 3x3 solve.

        Returns (u_projected, feasible). `feasible=False` means the set is empty at this
        state: the required per-step contraction exceeds the available authority, which
        is a genuine ineligibility rather than a rejected proposal.
        """
        A, B = CT.error_jacobians(r_now, r_next)
        Pc = np.linalg.cholesky(self.P).T          # P = Pc' Pc
        M = Pc @ B
        c = Pc @ (A @ e_k - B @ u_r + d_r)
        rho = self.lam * CT.norm_P(e_k, self.P) + CT.norm_P(d_r, self.P)
        u0 = np.asarray(u0, dtype=float)
        lim = self._achievable(chain)

        if np.linalg.norm(M @ u0 + c) <= rho:
            return u0, True

        # is the set nonempty at all? its centre is the unconstrained minimiser
        MtM = M.T @ M
        u_c = -np.linalg.solve(MtM + 1e-12 * np.eye(3), M.T @ c)
        if np.linalg.norm(M @ u_c + c) > rho:
            return u_c, False                      # infeasible: authority insufficient

        lo, hi = 0.0, 1.0
        for _ in range(60):                        # grow until the constraint is met
            u = np.linalg.solve(np.eye(3) + 2 * hi * MtM, u0 - 2 * hi * (M.T @ c))
            if np.linalg.norm(M @ u + c) <= rho:
                break
            lo, hi = hi, hi * 4.0
        for _ in range(60):                        # bisect to the boundary
            mid = 0.5 * (lo + hi)
            u = np.linalg.solve(np.eye(3) + 2 * mid * MtM, u0 - 2 * mid * (M.T @ c))
            if np.linalg.norm(M @ u + c) <= rho:
                hi = mid
            else:
                lo = mid
        u = np.linalg.solve(np.eye(3) + 2 * hi * MtM, u0 - 2 * hi * (M.T @ c))
        u = np.clip(u, -lim, lim)
        return u, bool(np.linalg.norm(M @ u + c) <= rho + 1e-9)

    def _wrench_star(self, e_k, u_r, d_r, chain, r_now, r_next):
        """The wrench minimising the one-step P-weighted error, over the input box.

        Unconstrained minimiser of ||A e + B(u - u_r) + d_r||_P, then projected onto
        the declared budget. B'PB is 3x3, so this is a direct solve, not a QP.
        """
        A, B = CT.error_jacobians(r_now, r_next)
        g = A @ e_k + d_r - B @ u_r
        M = B.T @ self.P @ B
        u = -np.linalg.solve(M + 1e-12 * np.eye(3), B.T @ self.P @ g)
        lim = self._achievable(chain)
        return np.clip(u, -lim, lim)

    def _alloc_aware_trial(self, u_ideal, e_k, u_r, d_r, r_now, r_next, chain, psi,
                           extra_seeds=None, rho=None):
        """Trial-allocate `u_ideal`, then take one Newton step on the known allocation
        map and keep whichever realisation better satisfies the decrease inequality.

        delta = u_tx(u) - u is locally constant on a quantisation cell, so requesting
        u - delta lands near the intended wrench. Two `chain.trial` calls, no grid
        search: at 0.6 ms per trial a 27-point search would not fit the 100 ms period.
        """
        lim = self._achievable(chain)
        A, B = CT.error_jacobians(r_now, r_next)

        def lhs_of(u_tx):
            return CT.norm_P(A @ e_k + B @ (np.asarray(u_tx) - u_r) + d_r, self.P)

        # `seeds` are tried in priority order. The first whose REALISATION satisfies
        # `rho` wins, so the MPC's own proposal is preferred and the contraction-optimal
        # wrench is only used as a repair. If none is feasible the LHS-minimising
        # realisation is returned together with feasible=False, which is a genuine
        # statement that no reachable command achieves the required decrease here.
        seeds = [np.asarray(u_ideal, dtype=float)]
        if extra_seeds:
            seeds += [np.asarray(s, dtype=float) for s in extra_seeds]
        best = None
        for seed in seeds:
            req = seed
            for _ in range(2):                     # one Newton step on the known map
                _, info = chain.trial(req, psi)
                u_tx = info["u_nominal_transmitted"]
                val = lhs_of(u_tx)
                if best is None or val < best[0]:
                    best = (val, req.copy(), info)
                if rho is not None and val <= rho:
                    return req.copy(), info, val, True
                req = np.clip(req - (np.asarray(u_tx) - req), -lim, lim)
        return best[1], best[2], best[0], (rho is None or best[0] <= rho)

    def _check(self, e_k, u_nom_tx, u_r, d_r, r_now, r_next):
        """Post-allocation acceptance check, Eq. (18).

            ||A e + B(u - u^r) + d^r||_P <= lam ||e||_P + ||d^r||_P + eta

        evaluated at the NOMINAL-EQUIVALENT TRANSMITTED wrench. That quantity is a
        function of the commanded pulses only, so this check contains no hidden
        fault information; an earlier version evaluated it at the post-fault wrench,
        which let the check see the fault before the controller was entitled to.
        """
        A, B = CT.error_jacobians(r_now, r_next)
        lhs = CT.norm_P(A @ e_k + B @ (np.asarray(u_nom_tx) - u_r) + d_r, self.P)
        rhs = (self.lam * CT.norm_P(e_k, self.P) + CT.norm_P(d_r, self.P)
               + self.eta)
        return bool(lhs <= rhs), float(rhs - lhs)

    def _reachable_box(self, chain, psi):
        """EXACT per-axis support of the allocator's reachable wrench set at yaw psi.

        The transmitted wrench is A(psi) F with per-thruster force in [0, F_cap], a
        zonotope whose per-axis support is the sum of the positive entries of each row.
        At psi = 0 only two thrusters bear on each force axis and the support is
        2 F_cap = 0.96 N, but at 45 degrees four contribute and it is 2.83 F_cap
        = 1.36 N.
        """
        from .plant import alloc_matrix
        F_cap = chain.fmax * chain.duty_ceiling / C.TS
        A = alloc_matrix(float(psi))
        return np.maximum(np.maximum(A, 0.0).sum(axis=1),
                          np.maximum(-A, 0.0).sum(axis=1)) * F_cap

    def _admissible(self, u_nom_tx, chain, psi):
        """u_k in U, tested against the set the actuators can actually deliver.

        This previously compared the transmitted wrench against `_achievable`, the
        yaw-INDEPENDENT inner bound (0.96 N per axis) used as the planning budget. The
        transmitted wrench is produced by the allocator from realisable pulse durations,
        so at off-axis yaw it legitimately reaches 1.14 N and was then declared
        inadmissible. That single mismatch, not the decrease test and not the eligible
        radius, rejected the stored fallback on 49.6% of all control steps, made the
        source ineligible, and handed 52% of transmitted actions to the fixed
        supervisor. The planning budget stays the conservative inner bound, because a
        plan must be realisable at every yaw; admissibility of a command that has
        already been allocated is tested against the true reachable set.
        """
        return bool(np.all(np.abs(np.asarray(u_nom_tx))
                           <= self._reachable_box(chain, psi) + 1e-9))

    def _supervisor(self, x_hat, chain):
        """The fixed supervisor used when eligibility fails.

        Sec 4.4 is explicit that this is not automatically safe, so its use is
        counted and its physical outcome scored like any other action rather than
        treated as an inactive sample.
        """
        u = np.array([-C.FALLBACK_KP_POS * x_hat[2],
                      -C.FALLBACK_KP_POS * x_hat[3],
                      -C.FALLBACK_KP_HEAD * x_hat[5]])
        return np.clip(u, [-C.FALLBACK_CLIP_F, -C.FALLBACK_CLIP_F,
                           -C.FALLBACK_CLIP_M],
                       [C.FALLBACK_CLIP_F, C.FALLBACK_CLIP_F, C.FALLBACK_CLIP_M])


class NominalRecoveryPolicy(LearnedContextPolicy):
    """M0: the SAME recovery controller structure with NO learned residual.

    Same pseudo-Huber cost, horizon, feedforward, affine model, acceptance check,
    eligibility rule, supervisor, allocator and solver handling as M3; the learned
    residual is identically zero and the context is a constant zero vector. This
    isolates the benefit of the learned predictor with every other component held
    comparable, which no variant in the earlier campaign did: `zero_context` also
    dropped the entire recovery apparatus and the pseudo-Huber cost, so it confounded
    the residual with the controller.
    """
    name = "nominal_recovery"
    uses_context = False

    def __init__(self, checkpoint, **kw):
        # a checkpoint is still loaded so the architecture and normalisation metadata
        # match, but neither the encoder nor the residual head is ever consulted
        super().__init__(checkpoint, **kw)

    def residual(self, k, x_hat, hist):
        self._z = np.zeros(C.D_LATENT)
        return np.zeros(6)


class FallbackOnlyPolicy(LearnedContextPolicy):
    """M5: the checked fallback feedback ONLY, with no MPC planning.

    Retains the context-conditioned feedforward, the gain K, the allocator, the
    acceptance check, the eligibility rule and the supervisor, so the single thing
    removed relative to M3 is the constrained optimisation. If M3 does not beat this,
    the measured performance is coming from the fallback and the eligibility logic
    rather than from MPC planning.
    """
    name = "fallback_only"

    def act(self, k, x_hat, ref_prev, chain, hist):
        self.stats["n_steps"] += 1
        # the context and residual are still computed: the feedforward is
        # context-conditioned in M3, and removing that too would confound MPC
        # planning with the learned feedforward
        self.residual(k, x_hat, hist)
        z = self._z
        r_now, r_next = ref_prev[0], ref_prev[1]
        e_k = CT.error_coords(x_hat, r_now)

        u_r, d_r = CT.feedforward(r_now, r_next, self._achievable(chain))
        u_fb = u_r + self.K @ e_k
        # M5 must differ from M3 only by the removal of MPC planning, so it gets the
        # same allocation-aware selection. Leaving it out would make the MPC-versus-
        # fallback comparison a comparison of two different things.
        if self.alloc_aware:
            u_opt = self._wrench_star(e_k, u_r, d_r, chain, r_now, r_next)
            rho_fb = self.lam * CT.norm_P(e_k, self.P) + CT.norm_P(d_r, self.P)
            u_fb, fb, _, _ = self._alloc_aware_trial(
                u_fb, e_k, u_r, d_r, r_now, r_next, chain, x_hat[4],
                extra_seeds=[u_opt], rho=rho_fb)
        else:
            _, fb = chain.trial(u_fb, x_hat[4])
        u_fb_tx = fb["u_nominal_transmitted"]
        fb_ok, fb_slack = self._check(e_k, u_fb_tx, u_r, d_r, r_now, r_next)
        fb_ok = bool(fb_ok and self._admissible(u_fb_tx, chain, x_hat[4]))

        eligible = fb_ok
        if self.R is not None and CT.norm_P(e_k, self.P) > self.R:
            eligible = False

        if eligible:
            chosen, src = fb, "fallback_only"
            chosen["_u_prop"] = u_fb
            self.stats["n_active"] += 1
        else:
            u_sup = self._supervisor(x_hat, chain)
            _, chosen = chain.trial(u_sup, x_hat[4])
            chosen["_u_prop"] = u_sup
            src = "supervisor"
            self.stats["n_gate_off"] += 1
            self.stats["n_supervisor"] += 1

        chain.commit(chosen)
        self.u_prev = np.asarray(chosen["u_nominal_transmitted"], dtype=float)
        chosen.update({"z": z, "gate": int(eligible), "accepted": bool(fb_ok),
                       "slack_cmd": float(fb_slack), "slack_fb": float(fb_slack),
                       "action_src": src, "solve_ms": 0.0, "fallback": False,
                       "e_P": CT.norm_P(e_k, self.P),
                       "u_prop": np.asarray(chosen["_u_prop"], dtype=float)})
        return chosen

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

    def _update(self, x_hat, u_applied):
        from .plant import jetson_nominal_step
        if self._prev is None:
            self._prev = (x_hat.copy(), np.asarray(u_applied, dtype=float).copy())
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
        self._prev = (x_hat.copy(), np.asarray(u_applied, dtype=float).copy())

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
        self._update(x_hat, out["u_applied"])
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
        self.recovery = bool(recovery)
        self.P = None if P is None else np.asarray(P, dtype=float)
        self.K = None if K is None else np.asarray(K, dtype=float)
        self.lam = float(lam)
        self.eta = float(eta)
        self.R = R
        self.stats.update({"n_reject": 0, "n_would_reject": 0, "n_gate_off": 0,
                           "n_active": 0})

    def context(self, k, x_hat, hist):
        return self._z

    def residual(self, k, x_hat, hist):
        z = self._infer(k, hist)
        self._z = z.numpy()[0]
        self._z_t = z
        return self._residual_world(x_hat, self.u_prev, z)

    # ------------------------------------------------------------------
    def act(self, k, x_hat, ref_prev, chain, hist):
        self.stats["n_steps"] += 1
        dres = self.residual(k, x_hat, hist)
        z = self._z

        r_now, r_next = ref_prev[0], ref_prev[1]
        e_k = CT.error_coords(x_hat, r_now)

        # ---- eligibility, decided from PRE-ACTION information (Eq. 19) ----
        # Eligibility says whether the GUARANTEE applies at this step; it does not
        # switch the supervision off. The acceptance check enforces a decrease in
        # ||e||_P, which is a sound thing to demand whether or not the state is inside
        # the certified region, and Stage 7 finds that region empty at hardware
        # authority, so disabling the check outside it would disable it always.
        # `gate` is therefore REPORTED as the eligible fraction, not used to branch.
        gate = 1
        if self.recovery and self.P is not None and self.R is not None:
            if CT.norm_P(e_k, self.P) > self.R:
                gate = 0
        if gate == 0:
            self.stats["n_gate_off"] += 1
        else:
            self.stats["n_active"] += 1

        # ---- stored checked fallback: allocate u_fb from the FROZEN sigma_q ----
        fb_info = None
        if self.recovery and self.P is not None and self.K is not None:
            u_r, d_r = CT.feedforward(r_now, r_next, self._achievable(chain))
            u_fb = u_r + self.K @ e_k
            _, fb_info = chain.trial(u_fb, x_hat[4])
            fb_ok, fb_slack = self._check(e_k, fb_info["u_applied"], u_r, d_r,
                                          r_now, r_next)
            fb_info["_slack"] = fb_slack
            fb_info["_ok"] = fb_ok
            fb_info["_u_prop"] = u_fb

        # ---- solve the MPC ----
        u_star, info = self.mpc.solve(x_hat, ref_prev, self.u_prev, dres)
        if info.get("fallback"):
            self.stats["n_fallback"] += 1

        chosen, accepted, slack = None, True, np.nan
        if not info.get("fallback"):
            _, cand = chain.trial(u_star, x_hat[4])
            if self.check_mode != "off" and fb_info is not None:
                u_r, d_r = CT.feedforward(r_now, r_next, self._achievable(chain))
                ok, slack = self._check(e_k, cand["u_applied"], u_r, d_r,
                                        r_now, r_next)
                if ok or self.check_mode == "monitor":
                    # monitor still records the slack and the would-be verdict, but
                    # transmits the candidate regardless
                    chosen, accepted = cand, bool(ok)
                    if not ok:
                        self.stats["n_would_reject"] += 1
                else:
                    # rejected: transmit the STORED checked fallback instead
                    self.stats["n_reject"] += 1
                    chosen, accepted = fb_info, False
            else:
                chosen, accepted = cand, True
        else:
            # solver failure: use the stored checked fallback if one exists
            chosen = (fb_info if fb_info is not None
                      else chain.trial(u_star, x_hat[4])[1])
            accepted = False

        chain.commit(chosen)
        u_prop = chosen.get("_u_prop", u_star)
        self.u_prev = np.asarray(u_prop, dtype=float)
        chosen.update({"z": z, "gate": gate, "accepted": bool(accepted),
                       "slack_cmd": float(slack) if np.isfinite(slack) else np.nan,
                       "e_P": (CT.norm_P(e_k, self.P) if self.P is not None
                               else np.nan),
                       "solve_ms": info.get("solve_time_ms", np.nan),
                       "fallback": bool(info.get("fallback", False)),
                       "u_prop": np.asarray(u_prop, dtype=float)})
        return chosen

    # ------------------------------------------------------------------
    def _achievable(self, chain):
        avg = chain.fmax * (chain.duty_ceiling / C.TS)
        return np.array([2.0 * avg, 2.0 * avg, 4.0 * 0.2 * avg])

    def _check(self, e_k, u_applied, u_r, d_r, r_now, r_next):
        """Post-allocation acceptance check, Eq. (18).

            ||A e + B(u - u^r) + d^r||_P <= lam ||e||_P + ||d^r||_P + eta

        evaluated at the TRANSMITTED-equivalent wrench, not the pre-allocation
        proposal.
        """
        A, B = CT.error_jacobians(r_now, r_next)
        lhs = CT.norm_P(A @ e_k + B @ (np.asarray(u_applied) - u_r) + d_r, self.P)
        rhs = (self.lam * CT.norm_P(e_k, self.P) + CT.norm_P(d_r, self.P)
               + self.eta)
        return bool(lhs <= rhs), float(rhs - lhs)

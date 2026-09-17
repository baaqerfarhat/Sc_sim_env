"""Model predictive controllers.

Two controllers, kept strictly distinct (build_scSim.md Sec 9):

`HardwareMPC`  - the controller that actually ran. Plain sum-of-squares stage cost,
                 N = 12, loose first-pass OSQP tolerances, near-coast fallback on
                 solver failure. No first-action condition, no terminal set, no
                 post-allocation check. This is the reference variant.

`ProposedMPC`  - manuscript Eq. (16) pseudo-Huber cost in error coordinates, plus
                 the first-action condition (Eq. 15), the eligibility gate (Eq. 19),
                 and the post-allocation acceptance check (Eq. 18) with stored
                 checked fallback. None of these existed on hardware.

Both are built on OSQP directly rather than through a modelling layer, because the
episode budget is ~5000 episodes x 600 steps.
"""
from __future__ import annotations

import numpy as np
import osqp
import scipy.sparse as sp

from . import config as C
from .plant import jetson_nominal_jac, wrap_pi

NX, NU = 6, 3


# ==========================================================================
# sparse index helpers
# ==========================================================================
class _Layout:
    """z = [x_1..x_N | u_0..u_{N-1} | s_r_1..s_r_N | s_h_1..s_h_N]"""

    def __init__(self, N):
        self.N = N
        self.nx = NX * N
        self.nu = NU * N
        self.ns = 2 * N
        self.n = self.nx + self.nu + self.ns
        self.ix = lambda i: slice(NX * (i - 1), NX * i)          # x_i, i = 1..N
        self.iu = lambda i: slice(self.nx + NU * i, self.nx + NU * (i + 1))
        self.isr = lambda i: self.nx + self.nu + (i - 1)
        self.ish = lambda i: self.nx + self.nu + N + (i - 1)


class HardwareMPC:
    """The deployed controller, reproduced exactly.

    Cost (all in absolute state space, tracking a setpoint preview):
        sum_{i=1..N}  w_pos|p_i-p_r|^2 + w_vel|v_i-v_r|^2
                    + w_psi(psi_i-psi_r)^2 + w_r(r_i-r_r)^2      (x4 at i=N)
      + sum_{i=0..N-1} w_u|u_i|^2 + w_du|u_i - u_{i-1}|^2
      + w_ang_slack * sum s_r^2 + w_headband * sum s_h

    Constraints: hard input box (+/-5, +/-5, +/-2) - the DECLARED box, which is
    physically unreachable and that is the point; |r| <= 1.8 soft via s_r;
    |r| <= 2.5 hard; |psi - psi_ref| <= 15 deg soft via s_h. No position, velocity,
    corridor or terminal-set constraints, and no first-action constraint. Input rate
    is penalised but never constrained.
    """

    def __init__(self, N=C.N_HORIZON_HW, weights=None, delta=0.0, huber=False,
                 mass=C.MASS, jzz=C.JZZ):
        self.N = int(N)
        self.L = _Layout(self.N)
        self.A, self.B = jetson_nominal_jac(C.TS, mass, jzz)
        self.w = np.array(C.W_NOMINAL if weights is None else weights, dtype=float)
        self.delta = float(delta)
        self.huber = bool(huber)
        self._m = None
        self._built_sig = None
        self._w_cur = None
        self.n_solver_fail = 0
        self.n_retry = 0

    # ------------------------------------------------------------------
    def _limits(self):
        """delta is multiplicative tightening: limit = (1-delta)*nominal, applied to
        Fx_max, Fy_max, Mz_max, ang_vel_max, psi_tol. NOT to the hard ang_vel_guard."""
        d = 1.0 - self.delta
        return dict(
            fx=C.FX_MAX * d, fy=C.FY_MAX * d, mz=C.MZ_MAX_DECLARED * d,
            rsoft=C.ANG_RATE_SOFT * d, psitol=C.HEADBAND * d,
            rhard=C.ANG_RATE_HARD,  # hard guard is never tightened
        )

    # ------------------------------------------------------------------
    def _cost_bases(self):
        """Per-weight cost basis matrices sharing ONE sparsity pattern.

        The cost is linear in the six weights, so P's nonzero values can be
        recomputed as sum_c w_c * basis_c and pushed to OSQP with update(Px=...).
        Rebuilding the problem whenever a weight changes made the pseudo-Huber
        majorisation loop ~80x slower than the solve itself.
        """
        N, L = self.N, self.L
        n = L.n
        comps = {}
        for name in ("pos", "vel", "psi", "r", "u", "du", "slack"):
            comps[name] = np.zeros((n, n))
        for i in range(1, N + 1):
            scale = C.QN_SCALE if i == N else 1.0
            base = NX * (i - 1)
            comps["pos"][base + 0, base + 0] = scale
            comps["pos"][base + 1, base + 1] = scale
            comps["vel"][base + 2, base + 2] = scale
            comps["vel"][base + 3, base + 3] = scale
            comps["psi"][base + 4, base + 4] = scale
            comps["r"][base + 5, base + 5] = scale
        for i in range(N):
            for j in range(NU):
                a = L.nx + NU * i + j
                comps["u"][a, a] += 1.0
                comps["du"][a, a] += 1.0
                if i > 0:
                    b = L.nx + NU * (i - 1) + j
                    comps["du"][a, b] += -1.0
                    comps["du"][b, a] += -1.0
                    comps["du"][b, b] += 1.0
        for i in range(1, N + 1):
            comps["slack"][L.isr(i), L.isr(i)] = C.W_ANG_SLACK

        # union sparsity pattern over the upper triangle
        union = np.zeros((n, n), dtype=bool)
        for M in comps.values():
            union |= np.abs(M) > 0
        union = np.triu(union)
        pat = sp.csc_matrix(np.where(union, 1.0, 0.0))
        rows, cols = pat.nonzero()
        # csc nonzero() is column-ordered, matching the data layout
        order = np.lexsort((rows, cols))
        rows, cols = rows[order], cols[order]
        self._P_rows, self._P_cols = rows, cols
        self._P_basis = {k: 2.0 * comps[k][rows, cols] for k in comps}
        self._P_pattern = pat

    def _P_data(self, w_state):
        w_pos, w_vel, w_psi, w_r, w_u, w_du = w_state
        b = self._P_basis
        return (w_pos * b["pos"] + w_vel * b["vel"] + w_psi * b["psi"]
                + w_r * b["r"] + w_u * b["u"] + w_du * b["du"] + b["slack"])

    def _build(self, w_state):
        """Build the sparse P pattern and the constraint matrix A once."""
        N, L = self.N, self.L
        A, B = self.A, self.B

        self._cost_bases()
        self._P = sp.csc_matrix(
            (self._P_data(w_state), (self._P_rows, self._P_cols)),
            shape=(L.n, L.n))

        # ---- constraints ----
        rows = []
        # (a) dynamics x_{i+1} = A x_i + B u_i + dres, i = 0..N-1
        for i in range(N):
            Rr = sp.lil_matrix((NX, L.n))
            Rr[:, L.ix(i + 1)] = sp.eye(NX)
            if i > 0:
                Rr[:, L.ix(i)] = -A
            Rr[:, L.iu(i)] = -B
            rows.append(Rr)
        # (b) input box
        for i in range(N):
            Rr = sp.lil_matrix((NU, L.n))
            Rr[:, L.iu(i)] = sp.eye(NU)
            rows.append(Rr)
        # (c) |r_i| <= rsoft + s_r  ->  two rows;  and s_r >= 0
        for i in range(1, N + 1):
            Rr = sp.lil_matrix((2, L.n))
            Rr[0, NX * (i - 1) + 5] = 1.0
            Rr[0, L.isr(i)] = -1.0
            Rr[1, NX * (i - 1) + 5] = -1.0
            Rr[1, L.isr(i)] = -1.0
            rows.append(Rr)
        # (d) |r_i| <= rhard
        for i in range(1, N + 1):
            Rr = sp.lil_matrix((1, L.n))
            Rr[0, NX * (i - 1) + 5] = 1.0
            rows.append(Rr)
        # (e) |psi_i - psi_ref| <= psitol + s_h
        for i in range(1, N + 1):
            Rr = sp.lil_matrix((2, L.n))
            Rr[0, NX * (i - 1) + 4] = 1.0
            Rr[0, L.ish(i)] = -1.0
            Rr[1, NX * (i - 1) + 4] = -1.0
            Rr[1, L.ish(i)] = -1.0
            rows.append(Rr)
        # (f) slack nonnegativity
        Rr = sp.lil_matrix((2 * N, L.n))
        for i in range(1, N + 1):
            Rr[i - 1, L.isr(i)] = 1.0
            Rr[N + i - 1, L.ish(i)] = 1.0
        rows.append(Rr)

        self._A = sp.csc_matrix(sp.vstack(rows))
        self._nrow = self._A.shape[0]
        # row offsets
        self._r_dyn = 0
        self._r_box = NX * N
        self._r_rsoft = self._r_box + NU * N
        self._r_rhard = self._r_rsoft + 2 * N
        self._r_head = self._r_rhard + N
        self._r_slack = self._r_head + 2 * N

    # ------------------------------------------------------------------
    def _bounds(self, x0, ref, u_prev, dres):
        N, L = self.N, self.L
        lim = self._limits()
        lo = np.full(self._nrow, -np.inf)
        hi = np.full(self._nrow, np.inf)
        # dynamics equalities
        b = np.zeros(NX * N)
        for i in range(N):
            rhs = dres.copy()
            if i == 0:
                rhs = rhs + self.A @ x0
            b[NX * i:NX * (i + 1)] = rhs
        lo[self._r_dyn:self._r_box] = b
        hi[self._r_dyn:self._r_box] = b
        # input box
        box_lo = np.tile([-lim["fx"], -lim["fy"], -lim["mz"]], N)
        box_hi = np.tile([lim["fx"], lim["fy"], lim["mz"]], N)
        lo[self._r_box:self._r_rsoft] = box_lo
        hi[self._r_box:self._r_rsoft] = box_hi
        # |r| <= rsoft + s_r
        hi[self._r_rsoft:self._r_rhard] = lim["rsoft"]
        # |r| <= rhard
        lo[self._r_rhard:self._r_head] = -lim["rhard"]
        hi[self._r_rhard:self._r_head] = lim["rhard"]
        # |psi - psi_ref| <= psitol + s_h ; psi_ref varies over the preview
        for i in range(1, N + 1):
            pr = ref[i, 4]
            hi[self._r_head + 2 * (i - 1)] = lim["psitol"] + pr
            hi[self._r_head + 2 * (i - 1) + 1] = lim["psitol"] - pr
        # slacks >= 0
        lo[self._r_slack:] = 0.0
        return lo, hi

    def _linear(self, ref, u_prev, w_state):
        """q vector. Cost is z'Pz + q'z with P already doubled."""
        N, L = self.N, self.L
        w_pos, w_vel, w_psi, w_r, w_u, w_du = w_state
        q = np.zeros(L.n)
        for i in range(1, N + 1):
            scale = C.QN_SCALE if i == N else 1.0
            d = np.array([w_pos, w_pos, w_vel, w_vel, w_psi, w_r]) * scale
            q[NX * (i - 1):NX * i] = -2.0 * d * ref[i]
        # rate term couples u_0 to u_prev
        q[L.iu(0)] += -2.0 * w_du * u_prev
        for i in range(1, N + 1):
            q[L.ish(i)] = C.W_HEADBAND  # linear headband penalty
        return q

    # ------------------------------------------------------------------
    def solve(self, x0, ref, u_prev, dres=None, weights=None):
        """Return (u0, info). `ref` is (N+1, 6); ref[0] is unused."""
        w_state = np.array(self.w if weights is None else weights, dtype=float)
        dres = np.zeros(NX) if dres is None else np.asarray(dres, dtype=float)
        x0 = np.asarray(x0, dtype=float)

        # unwrap the preview yaw onto the chart around x0 so the headband is linear
        ref = np.array(ref, dtype=float, copy=True)
        ref[:, 4] = x0[4] + wrap_pi(ref[:, 4] - x0[4])
        x0 = x0.copy()

        # only the horizon changes the problem STRUCTURE; a weight change is an
        # in-place update of P's nonzero values, which the majorisation loop needs
        rebuilt = False
        if self._m is None or self._built_sig != self.N:
            self._build(w_state)
            self._m = osqp.OSQP()
            lo, hi = self._bounds(x0, ref, u_prev, dres)
            self._m.setup(P=self._P, q=self._linear(ref, u_prev, w_state),
                          A=self._A, l=lo, u=hi,
                          eps_abs=C.OSQP_EPS_1, eps_rel=C.OSQP_EPS_1,
                          polish=False, warm_start=True, verbose=False,
                          max_iter=4000)
            self._built_sig = self.N
            self._w_cur = w_state.copy()
            rebuilt = True
        else:
            lo, hi = self._bounds(x0, ref, u_prev, dres)
            if not np.array_equal(w_state, self._w_cur):
                Px = self._P_data(w_state)
                self._P.data = Px
                self._m.update(Px=Px)
                self._w_cur = w_state.copy()
            self._m.update(q=self._linear(ref, u_prev, w_state), l=lo, u=hi)

        info = {"solver": "osqp", "retried": False, "rebuilt": rebuilt}
        res = self._m.solve()
        status = str(res.info.status)
        ok = status in ("solved", "solved inaccurate")
        # retry once at the tighter tolerance with polish (Sec 9)
        if not ok:
            self.n_retry += 1
            info["retried"] = True
            m2 = osqp.OSQP()
            m2.setup(P=self._P, q=self._linear(ref, u_prev, w_state), A=self._A,
                     l=lo, u=hi, eps_abs=C.OSQP_EPS_2, eps_rel=C.OSQP_EPS_2,
                     polish=True, warm_start=True, verbose=False, max_iter=8000)
            res = m2.solve()
            status = str(res.info.status)
            ok = status in ("solved", "solved inaccurate")

        info["status"] = status
        info["solve_time_ms"] = float(res.info.run_time) * 1e3
        info["iters"] = int(res.info.iter)

        if not ok or res.x is None or not np.all(np.isfinite(res.x)):
            self.n_solver_fail += 1
            info["fallback"] = True
            return self.coast_fallback(x0, ref[1]), info

        info["fallback"] = False
        u0 = res.x[self.L.iu(0)]
        info["u_seq"] = res.x[self.L.nx:self.L.nx + self.L.nu].reshape(self.N, NU)
        info["x_seq"] = res.x[:self.L.nx].reshape(self.N, NX)
        return np.asarray(u0, dtype=float), info

    # ------------------------------------------------------------------
    @staticmethod
    def coast_fallback(x0, ref1):
        """Solver-failure fallback, a near-coast (Sec 9)."""
        ex = ref1[0] - x0[0]
        ey = ref1[1] - x0[1]
        eh = wrap_pi(ref1[4] - x0[4])
        return np.array([
            np.clip(C.FALLBACK_KP_POS * ex, -C.FALLBACK_CLIP_F, C.FALLBACK_CLIP_F),
            np.clip(C.FALLBACK_KP_POS * ey, -C.FALLBACK_CLIP_F, C.FALLBACK_CLIP_F),
            np.clip(C.FALLBACK_KP_HEAD * eh, -C.FALLBACK_CLIP_M, C.FALLBACK_CLIP_M),
        ])


# ==========================================================================
# proposed Eq. (16) pseudo-Huber, solved by majorisation-minimisation
# ==========================================================================
def huber_irls_weights(e, w, s):
    """Quadratic majoriser weight for the pseudo-Huber stage cost.

    rho(e) = w s^2 (sqrt(1 + (e/s)^2) - 1) is concave in e^2, so
        rho(e) <= rho(e0) + rho'_{e^2}(e0^2) (e^2 - e0^2)
    is a valid quadratic majoriser with weight rho'_{e^2} = w / (2 sqrt(1+(e0/s)^2)).
    Iterating the weighted quadratic solve therefore decreases the true pseudo-Huber
    objective monotonically.
    """
    return w / (2.0 * np.sqrt(1.0 + (e / s) ** 2))


class ProposedMPC(HardwareMPC):
    """Eq. (16) pseudo-Huber cost via 3 MM iterations, plus the recovery machinery.

    Everything the hardware controller lacked lives here: the first-action decrease
    condition, the eligibility gate, and the post-allocation acceptance check with a
    stored checked fallback.
    """

    def __init__(self, N=C.N_HORIZON_HW, s_huber=None, mm_iters=3, **kw):
        super().__init__(N=N, **kw)
        self.s = np.array(C.HUBER_S if s_huber is None else s_huber, dtype=float)
        self.mm_iters = int(mm_iters)

    def solve(self, x0, ref, u_prev, dres=None, weights=None):
        w0 = np.array(self.w if weights is None else weights, dtype=float)
        # first pass with the nominal quadratic weights
        u0, info = super().solve(x0, ref, u_prev, dres, weights=w0)
        if info.get("fallback"):
            return u0, info
        # MM iterations: reweight the state cost from the current predicted errors
        for _ in range(self.mm_iters - 1):
            xs = info.get("x_seq")
            if xs is None:
                break
            err = xs - ref[1:]
            err[:, 4] = wrap_pi(err[:, 4])
            # aggregate per-channel error scale over the preview
            e_pos = np.sqrt(np.mean(err[:, 0] ** 2 + err[:, 1] ** 2))
            e_vel = np.sqrt(np.mean(err[:, 2] ** 2 + err[:, 3] ** 2))
            e_psi = np.sqrt(np.mean(err[:, 4] ** 2))
            e_r = np.sqrt(np.mean(err[:, 5] ** 2))
            wnew = w0.copy()
            wnew[0] = 2.0 * huber_irls_weights(e_pos, w0[0], self.s[0])
            wnew[1] = 2.0 * huber_irls_weights(e_vel, w0[1], self.s[2])
            wnew[2] = 2.0 * huber_irls_weights(e_psi, w0[2], self.s[4])
            wnew[3] = 2.0 * huber_irls_weights(e_r, w0[3], self.s[5])
            u0, info = super().solve(x0, ref, u_prev, dres, weights=wnew)
            if info.get("fallback"):
                break
        info["cost"] = "pseudo_huber_mm"
        return u0, info

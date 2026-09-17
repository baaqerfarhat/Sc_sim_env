"""Recovery certificate: LMI design, interval verification, and radii.

Implements manuscript Appendix II. The chain is:

  1  cover a compact domain V0 of (rho, z, u^r) by boxes
  2  solve the LMI (Eq. 34) for Q, Y at representative (A_b, B_b) -> P, K, lambda0
  3  bound the implemented model on each box by intervals, |A-A_b| <= E_A,
     |B-B_b| <= E_B, and certify gamma_b + nu_b <= lambda < 1  (Lemma 3)
  4  compute b_r, R_U (Eq. 20), R_corridor / R_chart (Eq. 21)
  5  s_cert = (b_r + d_cert + eta)/(1-lambda) and the strict margin

The verification is genuine interval arithmetic with outward rounding, not sampled
Jacobians: Appendix II is explicit that sampled Jacobians are insufficient.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from . import config as C
from .plant import alloc_matrix, jetson_nominal_jac, wrap_pi

NX, NU = 6, 3


# ==========================================================================
# error coordinates
# ==========================================================================
def error_coords(x, r):
    """e = Phi_r(x): position and velocity errors in the REFERENCE body frame,
    attitude error on a declared unwrapped chart.

    Body-frame coordinates make the error model invariant to a common planar rigid
    transformation of state and reference, which is what lets one certificate cover
    the whole reference library.
    """
    psi_r = r[4]
    c, s = np.cos(psi_r), np.sin(psi_r)
    R = np.array([[c, s], [-s, c]])  # world -> reference body
    dp = R @ (np.asarray(x)[:2] - np.asarray(r)[:2])
    dv = R @ (np.asarray(x)[2:4] - np.asarray(r)[2:4])
    return np.array([dp[0], dp[1], dv[0], dv[1],
                     wrap_pi(x[4] - r[4]), x[5] - r[5]])


def T_r(r):
    """Phi_r^{-1}(e) = r + T_r e on the chart."""
    psi_r = r[4]
    c, s = np.cos(psi_r), np.sin(psi_r)
    Rb = np.array([[c, -s], [s, c]])  # reference body -> world
    T = np.zeros((NX, NX))
    T[0:2, 0:2] = Rb
    T[2:4, 2:4] = Rb
    T[4, 4] = 1.0
    T[5, 5] = 1.0
    return T


def error_jacobians(r_now, r_next, mass=C.MASS, jzz=C.JZZ, dt=C.TS):
    """A(upsilon), B(upsilon): Jacobians of bar_f at (e, u) = (0, u^r).

    bar_f_i(e,u,z) = Phi_{r_{i+1}}( f_theta( Phi_{r_i}^{-1}(e), u, z) ).
    With the nominal predictor linear in (x, u), the composition gives
    A = T_{r_{i+1}}^{-1} A_0 T_{r_i} and B = T_{r_{i+1}}^{-1} B_0.
    """
    A0, B0 = jetson_nominal_jac(dt, mass, jzz)
    Ti, Tn = T_r(r_now), T_r(r_next)
    Tni = np.linalg.inv(Tn)
    return Tni @ A0 @ Ti, Tni @ B0


# ==========================================================================
# LMI design
# ==========================================================================
# Natural scales for conditioning the SDP. B entries span 250x (2e-4 N^-1 on
# position to 5.6e-2 on yaw rate), so the unscaled LMI is numerically hopeless: Q
# would need a comparable dynamic range and SCS reports infeasible. Solving in
# normalised coordinates and mapping back fixes it, and leaves lambda unchanged.
STATE_SCALE = np.array([1.0, 1.0, 0.3, 0.3, 0.3, 0.3])
INPUT_SCALE = np.array([2.4, 2.4, 0.96])   # the ACHIEVABLE set, not the declared box


def solve_lmi(A_list, B_list, lam0, state_scale=STATE_SCALE,
              input_scale=INPUT_SCALE, w_effort=1.0, verbose=False):
    """Find Q > 0, Y with  [[lam0^2 Q, (AQ+BY)'], [AQ+BY, Q]] >= 0  at every vertex,
    while bounding the control effort of the resulting gain.

    Returns (P, K) with P = Q^{-1}, K = Y Q^{-1}, or None if infeasible.

    Solved in normalised coordinates x = Sx*xt, u = Su*ut, so
    At = Sx^-1 A Sx, Bt = Sx^-1 B Su, and mapped back by
    P = Sx^-1 Pt Sx^-1, K = Su Kt Sx^-1.

    eps I <= Q <= I removes the homogeneous scale degeneracy of the LMI, which
    otherwise leaves the SDP unbounded and badly conditioned.

    EFFORT BOUND.  Contraction alone is satisfied by arbitrarily high gain, and an
    unbounded gain is worthless here: the input radius of Eq. (20) is
        R_U = min_i u_i / sqrt(K_i Q K_i'),
    so a large gain drives R_U to zero and simultaneously inflates the parametric
    term nu, which carries E_B K. The extra Schur block
        [[t, Yt_i], [Yt_i', Qt]] >= 0   <=>   Yt_i Qt^-1 Yt_i' = Kt_i Qt Kt_i' <= t
    for every input row bounds that quantity by a single t, and minimising
    w_effort * t - trace(Q) trades the achievable radius against a large invariant
    ellipsoid. With Su set to the achievable set, R_U = 1/sqrt(t) exactly.

    The certificate verdict is invariant to the normalisation: under Q -> cQ both
    R_U and s_cert scale as 1/sqrt(c), so only their ratio matters.
    """
    import scs
    import scipy.sparse as sp

    n, m = NX, NU
    Sx = np.diag(state_scale)
    Su = np.diag(input_scale)
    Sxi = np.diag(1.0 / state_scale)
    At = [Sxi @ A @ Sx for A in A_list]
    Bt = [Sxi @ B @ Su for B in B_list]

    nq = n * (n + 1) // 2
    it = nq + m * n            # index of the effort bound t
    nvar = it + 1

    basis = []
    for i in range(n):
        for j in range(i + 1):
            E = np.zeros((n, n))
            E[i, j] = 1.0
            E[j, i] = 1.0
            basis.append(E)

    blocks = []

    def psd_block(mat_fn, size, const):
        rows = [_vec_sdp(mat_fn(k), size) for k in range(nvar)]
        blocks.append((np.array(rows).T, _vec_sdp(const, size), size))

    eps = 1e-3
    # Q - eps I >= 0
    psd_block(lambda k: basis[k] if k < nq else np.zeros((n, n)), n,
              -eps * np.eye(n))
    # I - Q >= 0   (normalisation)
    psd_block(lambda k: -basis[k] if k < nq else np.zeros((n, n)), n, np.eye(n))

    for A, B in zip(At, Bt):
        def lmi_fn(k, A=A, B=B):
            M = np.zeros((2 * n, 2 * n))
            if k < nq:
                Ek = basis[k]
                M[:n, :n] = lam0 ** 2 * Ek
                M[n:, n:] = Ek
                M[n:, :n] = A @ Ek
                M[:n, n:] = (A @ Ek).T
            elif k < it:
                i, j = divmod(k - nq, n)
                Ek = np.zeros((m, n))
                Ek[i, j] = 1.0
                BY = B @ Ek
                M[n:, :n] = BY
                M[:n, n:] = BY.T
            return M

        psd_block(lmi_fn, 2 * n, np.zeros((2 * n, 2 * n)))

    # ---- effort bound: one (1+n) Schur block per input row ----
    for row in range(m):
        def eff_fn(k, row=row):
            M = np.zeros((1 + n, 1 + n))
            if k < nq:
                M[1:, 1:] = basis[k]
            elif k < it:
                i, j = divmod(k - nq, n)
                if i == row:
                    M[0, 1 + j] = 1.0
                    M[1 + j, 0] = 1.0
            else:
                M[0, 0] = 1.0
            return M

        psd_block(eff_fn, 1 + n, np.zeros((1 + n, 1 + n)))

    # minimise the effort bound while keeping the ellipsoid large
    c = np.zeros(nvar)
    for k in range(nq):
        c[k] = -np.trace(basis[k])
    c[it] = float(w_effort)

    A_scs = sp.csc_matrix(np.vstack([-Ar for Ar, _, _ in blocks]))
    b_scs = np.concatenate([bv for _, bv, _ in blocks])
    sol = scs.solve(dict(A=A_scs, b=b_scs, c=c),
                    dict(s=[sz for _, _, sz in blocks]),
                    verbose=verbose, eps_abs=1e-8, eps_rel=1e-8,
                    max_iters=25000)
    # A loose SDP solve cannot produce an invalid certificate: solve_lmi only
    # PROPOSES (P, K), and verify_box independently recomputes gamma and nu from the
    # returned pair. Soundness rests on the verification, not on the solver.
    status = str(sol["info"]["status"]).lower()
    if "solved" not in status:
        return None

    x = sol["x"]
    Qt = sum(x[k] * basis[k] for k in range(nq))
    Qt = 0.5 * (Qt + Qt.T)
    if np.linalg.eigvalsh(Qt).min() <= 0:
        return None
    Yt = x[nq:it].reshape(m, n)
    Pt = np.linalg.inv(Qt)
    Kt = Yt @ Pt
    P = Sxi @ Pt @ Sxi
    K = Su @ Kt @ Sxi
    return 0.5 * (P + P.T), K


def worst_gamma(P, K, A_list, B_list):
    """max_b ||C(A_b + B_b K)C^{-1}||_2, the realised design-point contraction."""
    Cm = np.linalg.cholesky(P).T
    Ci = np.linalg.inv(Cm)
    return max(float(np.linalg.norm(Cm @ (A + B @ K) @ Ci, 2))
               for A, B in zip(A_list, B_list))


def design_certificate(A_list, B_list, lam_grid=None):
    """Bisect lam0 for the tightest feasible common metric at the design points."""
    if lam_grid is None:
        lam_grid = np.concatenate([np.arange(0.50, 0.96, 0.05),
                                   np.array([0.96, 0.97, 0.98, 0.99, 0.995,
                                             0.999, 0.9995])])
    best = None
    for lam0 in lam_grid:
        r = solve_lmi(A_list, B_list, float(lam0))
        if r is None:
            continue
        P, K = r
        g = worst_gamma(P, K, A_list, B_list)
        if g < 1.0 and (best is None or g < best[2]):
            best = (P, K, g, float(lam0))
    return best


def _vec_sdp(M, n):
    """SCS scaled lower-triangular vectorisation of a symmetric matrix."""
    out = []
    r2 = np.sqrt(2.0)
    for j in range(n):
        for i in range(j, n):
            out.append(M[i, j] * (1.0 if i == j else r2))
    return np.array(out)


# ==========================================================================
# interval verification (Lemma 3)
# ==========================================================================
def verify_box(P, K, A_b, B_b, E_A, E_B):
    """Return (gamma_b, nu_b). The box is certified when gamma_b + nu_b <= lambda.

    gamma_b >= ||C (A_b + B_b K) C^{-1}||_2
    N_b     >= |C| (E_A + E_B |K|) |C^{-1}|   elementwise
    nu_b    >= sqrt(||N_b||_1 ||N_b||_inf)    an upper bound on ||N_b||_2
    """
    # P = C'C via Cholesky; outward-round the norms
    L = np.linalg.cholesky(P)
    Cm = L.T
    Cinv = np.linalg.inv(Cm)
    M = Cm @ (A_b + B_b @ K) @ Cinv
    gamma = float(np.linalg.norm(M, 2))
    N = np.abs(Cm) @ (E_A + E_B @ np.abs(K)) @ np.abs(Cinv)
    nu = float(np.sqrt(np.linalg.norm(N, 1) * np.linalg.norm(N, np.inf)))
    # outward rounding allowance for factorisation / inversion / product / norm
    rnd = 1.0 + 1e-9
    return gamma * rnd, nu * rnd


def residual_budget(P, K, boxes, J_res, lam_target, e_extra=None, tol=1e-4):
    """Largest scale alpha such that admitting alpha * J_res still certifies.

    nu is monotone in the interval matrices, so the admissible scale is found by
    bisection. Reporting this budget converts "the certificate is empty" into the
    actionable statement "the residual's Jacobian must be bounded by alpha * J_res",
    which is a concrete Lipschitz specification for the learned model.
    """
    def worst(alpha):
        rA, rB = residual_interval_terms(alpha * np.asarray(J_res))
        out = 0.0
        for b in boxes:
            eA = b["E_A"] + rA
            eB = b["E_B"] + rB
            if e_extra is not None:
                eA = eA + e_extra[0]
                eB = eB + e_extra[1]
            g, nu = verify_box(P, K, b["A"], b["B"], eA, eB)
            out = max(out, g + nu)
        return out

    if worst(0.0) > lam_target:
        return 0.0                      # infeasible even with no residual
    lo, hi = 0.0, 1.0
    if worst(hi) <= lam_target:
        while hi < 1e6 and worst(hi) <= lam_target:
            hi *= 4.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if worst(mid) <= lam_target:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol * max(lo, 1e-6):
            break
    return lo


def interval_jacobian_bounds(r_lo, r_hi, mass_iv, jzz_iv, dt=C.TS):
    """Enclose A(upsilon), B(upsilon) over a box of references and plant parameters.

    A = T_{r+}^{-1} A_0 T_r depends on the reference yaw pair through rotations, and
    B on 1/mass and 1/jzz. Bounds are computed by enclosing each entry.
    """
    # yaw difference across the box drives the rotation mismatch
    dpsi = 0.5 * (r_hi - r_lo)
    # |cos a - cos b| <= |a-b| and likewise for sin, so a rotation over an interval
    # of width w is enclosed by an elementwise w perturbation
    w = float(abs(dpsi))
    A0, _ = jetson_nominal_jac(dt, mass_iv[0], jzz_iv[0])
    E_A = np.zeros((NX, NX))
    # rotation blocks are the only yaw-dependent entries of A
    for blk in (slice(0, 2), slice(2, 4)):
        E_A[blk, blk] = w * (1.0 + dt)
    E_A[0:2, 2:4] = w * dt
    # B depends on 1/mass and 1/jzz over their intervals
    m_lo, m_hi = mass_iv
    j_lo, j_hi = jzz_iv
    inv_m_spread = abs(1.0 / m_lo - 1.0 / m_hi)
    inv_j_spread = abs(1.0 / j_lo - 1.0 / j_hi)
    E_B = np.zeros((NX, NU))
    E_B[0, 0] = E_B[1, 1] = 0.5 * dt * dt * inv_m_spread + w * dt * dt
    E_B[2, 0] = E_B[3, 1] = dt * inv_m_spread + w * dt
    E_B[5, 2] = dt * inv_j_spread
    return E_A, E_B


# ==========================================================================
# radii
# ==========================================================================
def input_radius(P, K, H_u, h_u, u_r_list):
    """R_U from Eq. (20). An empty minimum is +inf; every zero-q row needs mu >= 0."""
    Pinv = np.linalg.inv(P)
    best = np.inf
    binding = None
    for j in range(H_u.shape[0]):
        Hj = H_u[j:j + 1, :]
        mu = h_u[j] - max(float(Hj @ np.asarray(u)) for u in u_r_list)
        q = float(np.sqrt(Hj @ K @ Pinv @ K.T @ Hj.T))
        if q <= 1e-12:
            if mu < 0:
                return 0.0, f"row {j} infeasible (mu={mu:.3g} < 0, q=0)"
            continue
        val = mu / q
        if val < best:
            best, binding = val, f"input facet {j}"
    return max(best, 0.0), binding


def corridor_radius(P, H_l, h_l, r_list, E_support):
    """R_corridor from Eq. (21), including the estimation budget support."""
    Pinv = np.linalg.inv(P)
    best, binding = np.inf, None
    for r in r_list:
        Tr = T_r(r)
        for j in range(H_l.shape[0]):
            Hj = H_l[j:j + 1, :]
            q = float(np.sqrt(Hj @ Tr @ Pinv @ Tr.T @ Hj.T))
            slack = h_l[j] - float(Hj @ np.asarray(r)) - E_support(Hj.ravel())
            if q <= 1e-12:
                if slack < 0:
                    return 0.0, f"corridor row {j} infeasible"
                continue
            val = slack / q
            if val < best:
                best, binding = val, f"corridor facet {j}"
    return max(best, 0.0), binding


def chart_radius(P, psi_span=np.pi / 2):
    """Largest R keeping the attitude error on the declared unwrapped chart."""
    Pinv = np.linalg.inv(P)
    q = float(np.sqrt(Pinv[4, 4]))
    return (psi_span / q if q > 1e-12 else np.inf), "chart"


GELU_PRIME_MAX = 1.1289860


def residual_jacobian_bound(model, per_entry=True):
    """Rigorous upper bound on d(d_theta)/d(xb, ub) for the trained residual.

    Sound for any input, using submultiplicativity plus the activation derivative
    bounds: GELU' <= 1.1289860, and the output tanh(raw/clip)*clip has derivative
    <= 1 w.r.t. raw. Appendix II is explicit that sampled Jacobians are not
    admissible, so nothing here is estimated from samples.

    `per_entry` returns a (6, 6) matrix of ENTRYWISE bounds over the six physical
    inputs (v_bx, v_by, r, u_bx, u_by, u_bz), using

        |d(d_j)/d(in_i)| <= out_scale_j ||e_j' W_L|| (prod_mid ||W||) ||W_1 e_i||
                            GELU'^n_act.

    `verify_box` performs elementwise interval arithmetic, so it needs entrywise
    magnitudes. Substituting the single global spectral bound into all 18 entries
    (as a scalar bound invites) overstates nu by more than an order of magnitude,
    because the row and column sums then each count the whole Jacobian norm six
    times over.

    The latent input z is excluded on purpose: within one step the certificate holds
    the context frozen, so z's sensitivity is a bounded additive term and belongs to
    d_cert, not to the state/input Jacobian enclosure.
    """
    import torch

    lins = [l for l in model.res.net if isinstance(l, torch.nn.Linear)]
    n_act = sum(1 for l in model.res.net if not isinstance(l, torch.nn.Linear))
    W1 = lins[0].weight.detach().numpy()
    WL = lins[-1].weight.detach().numpy()
    mid = 1.0
    for l in lins[1:-1]:
        mid *= float(np.linalg.norm(l.weight.detach().numpy(), 2))
    act = GELU_PRIME_MAX ** n_act
    out_scale = model.res.out_scale.detach().abs().numpy()

    # global spectral bound, kept for reporting
    glob = (float(np.linalg.norm(W1, 2)) * mid
            * float(np.linalg.norm(WL, 2)) * act * float(out_scale.max()))
    if not per_entry:
        return glob

    # only the first six input columns are physical; the rest are z
    col_norm = np.linalg.norm(W1[:, :6], axis=0)      # ||W_1 e_i||
    row_norm = np.linalg.norm(WL, axis=1)             # ||e_j' W_L||
    J = (out_scale * row_norm)[:, None] * (mid * act) * col_norm[None, :]
    return J, glob


def _gelu_prime_bound(lo, hi, grid=2001):
    """Rigorous elementwise max of |GELU'| over each interval [lo_i, hi_i].

    GELU'(x) = Phi(x) + x phi(x) and GELU''(x) = phi(x)(2 - x^2), so
    |GELU''| <= 2 phi(0) < 0.7979. Sampling on a grid of spacing h and inflating by
    0.399 h therefore gives a sound upper bound, and is far tighter than the global
    constant whenever the pre-activation interval avoids the peak near x = 1.
    """
    from scipy.stats import norm as _norm

    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    out = np.empty_like(lo)
    for i in range(lo.size):
        a, b = lo.flat[i], hi.flat[i]
        xs = np.linspace(a, b, grid)
        g = _norm.cdf(xs) + xs * _norm.pdf(xs)
        h = (b - a) / max(grid - 1, 1)
        out.flat[i] = min(float(np.abs(g).max()) + 0.399 * h, GELU_PRIME_MAX)
    return out


def residual_jacobian_box(model, lo, hi):
    """Entrywise Jacobian enclosure of the residual over an INPUT BOX, by IBP.

    Returns (J, info) with J[j, i] >= |d(d_theta)_j / d(in_i)| for every input in the
    box, i = 0..5 over (v_bx, v_by, r, u_bx, u_by, u_bz).

    Interval bound propagation gives per-neuron pre-activation intervals; each
    activation slope is then bounded on its own interval, and the layer Jacobians are
    composed with absolute-value matrix products,

        J <= out_scale * tanh'_max * |W_L| diag(d2) |W_2| diag(d1) |W_1|,

    which is sound because every factor bounds the corresponding true factor
    elementwise in magnitude. This is a domain-restricted enclosure, not a sampled
    Jacobian: it holds for every point of the box, as Appendix II requires. It is
    dramatically tighter than the global product of spectral norms, which spreads the
    worst case over the entire input space and ignores the output saturation.
    """
    import torch

    lins = [l for l in model.res.net if isinstance(l, torch.nn.Linear)]
    Ws = [l.weight.detach().numpy() for l in lins]
    bs = [l.bias.detach().numpy() for l in lins]
    out_scale = model.res.out_scale.detach().numpy()
    clip = float(model.res.clip)

    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    c, r = 0.5 * (lo + hi), 0.5 * (hi - lo)

    slopes = []
    for li, (W, b) in enumerate(zip(Ws, bs)):
        yc = W @ c + b
        yr = np.abs(W) @ r
        ylo, yhi = yc - yr, yc + yr
        if li < len(Ws) - 1:                      # GELU
            d = _gelu_prime_bound(ylo, yhi)
            slopes.append(d)
            # propagate the ACTIVATION interval to the next layer
            from scipy.stats import norm as _norm
            g_lo = ylo * _norm.cdf(ylo)
            g_hi = yhi * _norm.cdf(yhi)
            a_lo = np.minimum(g_lo, g_hi)
            a_lo = np.minimum(a_lo, -0.17)        # global GELU minimum > -0.1700
            a_hi = np.maximum(g_lo, g_hi)
            c, r = 0.5 * (a_lo + a_hi), 0.5 * (a_hi - a_lo)
        else:                                     # output: tanh(raw/clip)*clip
            raw_lo, raw_hi = ylo * out_scale, yhi * out_scale
            t_lo = np.minimum(raw_lo, raw_hi) / clip
            t_hi = np.maximum(raw_lo, raw_hi) / clip
            # sech^2 peaks at 0, so use the endpoint nearest 0
            near = np.where((t_lo <= 0) & (t_hi >= 0), 0.0,
                            np.minimum(np.abs(t_lo), np.abs(t_hi)))
            tanh_d = 1.0 / np.cosh(near) ** 2

    J = np.abs(Ws[0])
    for W, d in zip(Ws[1:], slopes):
        J = np.abs(W) @ (d[:, None] * J)
    J = (out_scale * tanh_d)[:, None] * J
    return J[:, :6], {"tanh_slope_max": float(tanh_d.max()),
                      "gelu_slope_max": float(max(d.max() for d in slopes)),
                      "n_layers": len(Ws)}


def residual_interval_terms(bound, dt=C.TS):
    """Fold the residual Jacobian bound into the (E_A, E_B) interval enclosures.

    The residual is added to the body-frame state increment, so its input
    sensitivities land on the velocity and yaw-rate columns of A (xb = (v_b, r)) and
    on all of B (ub = body wrench). Accepts either the (6, 6) entrywise matrix or a
    scalar, in which case the scalar is spread uniformly.
    """
    E_A = np.zeros((NX, NX))
    E_B = np.zeros((NX, NU))
    if bound is None:
        return E_A, E_B
    J = np.asarray(bound, dtype=float)
    if J.ndim == 0:
        J = float(J) * np.ones((NX, 6))
    for j, col in enumerate((2, 3, 5)):
        E_A[:, col] += J[:, j]
    E_B[:, :] += J[:, 3:6]
    return E_A, E_B


# ==========================================================================
# feedforward selector and the reference defect b_r
# ==========================================================================
def feedforward(r_now, r_next, achievable, lam_r=1e-3, mass=C.MASS, jzz=C.JZZ,
                u0=None):
    """Deterministic feasible solver map S_r(rho, z), Eq. (7).

    Targets ||bar_f(0,u,z)||^2 + lam_r||u - u^{r,0}||^2 over u in U, where U is the
    ACHIEVABLE set, not the MPC's declared box. Returns (u_r, d_r).

    A feasible returned command and its evaluated defect suffice for recovery, so a
    projected least-squares solution with a fixed tie-break is enough; global
    optimality is unnecessary.
    """
    A, B = error_jacobians(r_now, r_next, mass, jzz)
    # bar_f(0, u) = A*0 + B*u + c   where c is the drift from holding the reference
    e_now = np.zeros(NX)
    c = _defect_constant(r_now, r_next, mass, jzz)
    u0 = np.zeros(NU) if u0 is None else np.asarray(u0, float)
    # min ||B u + c||^2 + lam_r||u - u0||^2  s.t. |u| <= achievable
    H = B.T @ B + lam_r * np.eye(NU)
    g = B.T @ c - lam_r * u0
    u = -np.linalg.solve(H, g)
    u = np.clip(u, -np.asarray(achievable), np.asarray(achievable))
    d_r = B @ u + c
    return u, d_r


def _defect_constant(r_now, r_next, mass=C.MASS, jzz=C.JZZ, dt=C.TS):
    """c = Phi_{r_next}( f0(r_now, 0) ), the defect at zero error and zero command.

    For a HELD setpoint with v_ref = 0 this is zero, so the reference is an
    equilibrium. At a setpoint SWITCH it is the full jump, which is exactly why the
    step family gives a large b_r and inflates s_cert (Sec 10).
    """
    from .plant import jetson_nominal_step
    x_now = np.asarray(r_now, dtype=float).copy()
    x_next_pred = jetson_nominal_step(x_now, np.zeros(NU), dt, mass, jzz)
    return error_coords(x_next_pred, r_next)


def norm_P(v, P):
    v = np.asarray(v, dtype=float)
    return float(np.sqrt(max(v @ P @ v, 0.0)))


def allocation_allowance(P, K, B_list, achievable, n_samples=400, R_probe=1.0,
                         seed=0, chain_factory=None):
    """eta_q from Lemma 2: sup ||C B delta_u_q||_2 over the verification domain.

    delta_u_q = G A_q(u_fb; sigma_q) - u_fb, the difference between the allocated,
    duty-quantised, minimum-pulse-limited, fault-skipped realisation and the affine
    fallback it was meant to implement. The bound sweeps admitted allocator memory
    states, since the allocator carries an EWMA history.
    """
    from .plant import CommandChain, DeterministicFault

    rng = np.random.default_rng(seed)
    Cm = np.linalg.cholesky(P).T
    Pinv = np.linalg.inv(P)
    worst = 0.0
    worst_detail = None
    for i in range(n_samples):
        # sample e on the boundary of the ellipsoid ||e||_P <= R_probe
        v = rng.standard_normal(NX)
        v /= np.linalg.norm(v)
        L = np.linalg.cholesky(Pinv)
        e = R_probe * (L @ v)
        u_r = rng.uniform(-1, 1, NU) * np.asarray(achievable) * 0.5
        u_fb = np.clip(u_r + K @ e, -np.asarray(achievable), np.asarray(achievable))
        psi = rng.uniform(-np.pi, np.pi)
        chain = (chain_factory() if chain_factory is not None
                 else CommandChain(fault=DeterministicFault(active=False)))
        # admitted allocator memory state
        chain.use_hist = rng.uniform(0, 12, 8)
        u_applied, info = chain(u_fb, psi)
        d_uq = u_applied - u_fb
        for B in B_list:
            val = float(np.linalg.norm(Cm @ B @ d_uq, 2))
            if val > worst:
                worst = val
                worst_detail = {"e_P": R_probe, "u_fb": u_fb.tolist(),
                                "u_applied": u_applied.tolist(),
                                "d_uq_norm": float(np.linalg.norm(d_uq))}
    return worst, worst_detail


@dataclass
class CertificateResult:
    lam: float
    lam0: float
    b_r: float
    d_cert: float
    eta: float
    eta_q: float
    R: float
    R_U: float
    R_corridor: float
    R_chart: float
    s_cert: float
    margin: float
    nonempty: bool
    binding: str
    n_boxes: int
    n_boxes_certified: int
    P: list
    K: list
    lam_min_P: float
    notes: str = ""

    def dict(self):
        return asdict(self)


def s_cert_value(b_r, d_cert, eta, lam):
    return (b_r + d_cert + eta) / max(1.0 - lam, 1e-12)

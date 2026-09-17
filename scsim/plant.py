"""Plant, allocator, duty law and fault injection.

The command chain reproduces send_thruster_commands() in the exact order given in
build_scSim.md Sec 3:

  1 MPC solves u*
  2 cap_wrench_heading_first
  3 tiny-axis zeroing
  4 safety_filter deadband (on the commanded wrench, BEFORE allocation)
  5 thrust_gain = 2.0 on all three components
  6 cap_wrench_heading_first again          <- makes the gain a no-op above half cap
  7 QP allocation
  8 duty conversion
  9 fault pulse-skip                        <- after the logged wrench is published
 10 publish

The predictor (JetsonNominalDynamics) is deliberately separate: the plant is never
rolled from the learned model.
"""
from __future__ import annotations

import numpy as np
from scipy.linalg import solve_triangular as _solve_tri_raw
from scipy.optimize import lsq_linear as _lsq_linear_raw

from . import config as C


def _solve_tri(L, b, lower=True):
    return _solve_tri_raw(L, b, lower=lower, check_finite=False)


def _lsq_linear(M, c, fmax):
    return _lsq_linear_raw(M, c, bounds=(0.0, fmax), method="bvls",
                           tol=1e-14).x


# ==========================================================================
# predictor: JetsonNominalDynamics, unchanged
# ==========================================================================
def wrap_pi(a):
    return (a + np.pi) % (2.0 * np.pi) - np.pi


def jetson_nominal_step(x, u, dt=C.TS, mass=C.MASS, jzz=C.JZZ):
    """Exact ZOH on translation, forward Euler on yaw.

    x = [x, y, vx, vy, psi, r]; u = [tau_x, tau_y, Mz] in the WORLD frame.
    Note the asymmetry is real: translation carries the 0.5*dt^2 term, yaw does not.
    """
    x = np.asarray(x, dtype=float)
    ax, ay = u[0] / mass, u[1] / mass
    az = u[2] / jzz
    out = np.empty_like(x)
    out[0] = x[0] + dt * x[2] + 0.5 * dt * dt * ax
    out[1] = x[1] + dt * x[3] + 0.5 * dt * dt * ay
    out[2] = x[2] + dt * ax
    out[3] = x[3] + dt * ay
    out[4] = wrap_pi(x[4] + dt * x[5])
    out[5] = x[5] + dt * az
    return out


def jetson_nominal_jac(dt=C.TS, mass=C.MASS, jzz=C.JZZ):
    """Jacobians of the predictor. Constant, since the predictor is linear."""
    A = np.eye(6)
    A[0, 2] = dt
    A[1, 3] = dt
    A[4, 5] = dt
    B = np.zeros((6, 3))
    B[0, 0] = 0.5 * dt * dt / mass
    B[1, 1] = 0.5 * dt * dt / mass
    B[2, 0] = dt / mass
    B[3, 1] = dt / mass
    B[5, 2] = dt / jzz
    return A, B


# ==========================================================================
# steps 2 and 6: cap_wrench_heading_first
# ==========================================================================
def cap_wrench_heading_first(u):
    """Clip to (+/-5 N, +/-5 N, +/-0.8 N m). Yaw first, hence the name."""
    return np.array(
        [
            np.clip(u[0], -C.FX_MAX, C.FX_MAX),
            np.clip(u[1], -C.FY_MAX, C.FY_MAX),
            np.clip(u[2], -C.MZ_CAP, C.MZ_CAP),
        ]
    )


# ==========================================================================
# step 3: tiny-axis zeroing
# ==========================================================================
def tiny_axis_zero(u, frac=C.TINY_AXIS_FRAC):
    u = u.copy()
    dom = max(abs(u[0]), abs(u[1]))
    if dom > 0.0:
        if abs(u[0]) < frac * dom:
            u[0] = 0.0
        if abs(u[1]) < frac * dom:
            u[1] = 0.0
    return u


# ==========================================================================
# step 4: safety_filter deadband
# ==========================================================================
def safety_filter(u):
    u = u.copy()
    if abs(u[0]) < C.DEADBAND_FORCE:
        u[0] = 0.0
    if abs(u[1]) < C.DEADBAND_FORCE:
        u[1] = 0.0
    if abs(u[2]) < C.DEADBAND_YAW:
        u[2] = 0.0
    return u


# ==========================================================================
# step 7: QP allocation
# ==========================================================================
def alloc_matrix(psi):
    """A(psi) = [Rz(psi) @ G[0:2] ; G[2]]. Force rows rotated, yaw row not."""
    c, s = np.cos(psi), np.sin(psi)
    Rz = np.array([[c, -s], [s, c]])
    A = np.empty((3, 8))
    A[0:2, :] = Rz @ C.G_MAP[0:2, :]
    A[2, :] = C.G_MAP[2, :]
    return A


_EYE8 = np.eye(8)


def alloc_qp_terms(tau, psi, use_hist):
    """Build the (Q, g) of the allocator QP: min F'QF + 2g'F s.t. 0 <= F <= fmax."""
    A = alloc_matrix(psi)
    Aw = A * C.W_TAU[:, None]          # W_tau A
    tw = C.W_TAU * tau                 # W_tau tau
    h = _normalized_use(use_hist)
    Q = Aw.T @ Aw + C.ALLOC_REG_L2 * _EYE8 + C.ALLOC_REG_USE * np.diag(1.0 + 3.0 * h)
    # gradient of the 5e-4*sum(F) term is 5e-4; halved to match the 2g' convention
    g = -(Aw.T @ tw) + 0.5 * C.ALLOC_REG_L1
    return Q, g


def solve_box_qp(Q, g, fmax):
    """Exact minimiser of F'QF + 2g'F over the box [0, fmax]^n.

    Q is strictly positive definite (the regularisation floor is 1e-4 + 1e-3), so
    factor Q = L L' and rewrite the objective as a bounded least-squares problem,

        F'QF + 2g'F = ||L'F - c||^2 + const,   L c = -g,

    then solve it with Lawson-Hanson BVLS, an exact active-set method. Verified to
    a 1e-13 KKT residual over 2500 random and saturating problems.

    Two cheaper schemes were tried and rejected. Cyclic coordinate descent needed
    >20000 sweeps for a 1e-10 residual, because Q is a rank-3 term plus ~1e-3
    regularisation with condition number ~1e4. Projected Newton with an Armijo
    line search stalled at a 7e-3 residual and was no faster.
    """
    L = np.linalg.cholesky(Q)
    c = -_solve_tri(L, g, lower=True)
    return _lsq_linear(L.T, c, fmax)


def allocate(tau, psi, use_hist, fmax=C.FMAX_PER_THRUSTER):
    """Solve the allocator QP.

        min_F ||W_tau (A(psi) F - tau)||^2
              + 1e-4||F||^2 + 5e-4 sum(F) + 1e-3 F' diag(1+3h) F
        s.t.  0 <= F <= fmax

    `use_hist` is the persistent EWMA accumulator: allocation for a given tau
    depends on the whole firing history. Unachievable requests are NOT detected -
    no scaling, no infeasible return, just the least-squares compromise.
    """
    tau = np.asarray(tau, dtype=float)
    if np.linalg.norm(tau) < C.TAU_DEADZONE:
        return np.zeros(8)
    Q, g = alloc_qp_terms(tau, psi, use_hist)
    return solve_box_qp(Q, g, fmax)


def _normalized_use(use_hist):
    """h = normalized cumulative usage from the EWMA accumulator."""
    m = np.max(use_hist)
    if m <= 1e-9:
        return np.zeros(8)
    return use_hist / m


def update_use_hist(use_hist, F):
    """EWMA with decay 0.995, updated every cycle."""
    return C.USE_HIST_DECAY * use_hist + F


# ==========================================================================
# step 8: duty conversion
# ==========================================================================
def duty_from_force(F):
    """dt_on = clip(4.829*F/25 - 0.07686, 0, 0.040) seconds.

    Consequences: near-zero on-time below F ~ 0.40 N, saturation at 40 ms above
    F ~ 0.65 N, so the usable proportional band is only about 0.40-0.65 N.
    """
    dt_on = C.FIT_SLOPE * np.asarray(F, dtype=float) / C.F_CL + C.FIT_OFFSET
    return np.clip(dt_on, 0.0, C.PWM_PERIOD)


def apply_min_pulse(dt_on, F):
    """min_on_time branch for use_accumulator = False.

    F > 0.001 N  -> pulse stretched up to 12 ms
    F <= 0.001 N -> zeroed
    Neither dropped nor accumulated.
    """
    dt_on = np.asarray(dt_on, dtype=float).copy()
    F = np.asarray(F, dtype=float)
    active = F > C.PULSE_ZERO_THRESHOLD
    dt_on[~active] = 0.0
    stretch = active & (dt_on < C.MIN_ON_TIME)
    dt_on[stretch] = C.MIN_ON_TIME
    return dt_on


def condense_pairs_by_dt(dt_on, F):
    """Merge opposing pairs (0,4),(1,5),(2,6),(3,7) only when both on-times are
    below the minimum pulse AND net XY contribution is negligible."""
    dt_on = np.asarray(dt_on, dtype=float).copy()
    for a, b in ((0, 4), (1, 5), (2, 6), (3, 7)):
        if dt_on[a] < C.MIN_ON_TIME and dt_on[b] < C.MIN_ON_TIME:
            net = abs(dt_on[a] - dt_on[b])
            if net < 1e-4:
                dt_on[a] = 0.0
                dt_on[b] = 0.0
    return dt_on


# ==========================================================================
# step 9: fault pulse-skip
# ==========================================================================
class DeterministicFault:
    """Sec 6. No RNG, nothing seeded; fully determined by the cycle count.

    fault_cycle += 1
    should_fire = (fault_cycle*fault_fraction - fault_fired) >= 0.5
    if should_fire: fault_fired += 1
    else:           dt_ms[6] = dt_ms[7] = 0.0

    fmax stays 1.2 N for all eight thrusters at every level; there is no thrust
    reduction. Onset is a step at t=0, constant for the whole run.
    """

    def __init__(self, fault_fraction=1.0, active=False, thrusters=C.FAULT_THRUSTERS):
        self.fault_fraction = float(fault_fraction)
        self.active = bool(active)
        self.thrusters = tuple(thrusters)
        self.fault_cycle = 0
        self.fault_fired = 0
        self.n_skips = 0

    def _would_fire(self):
        """The decision for the NEXT cycle, without consuming it."""
        nxt = self.fault_cycle + 1
        return (nxt * self.fault_fraction - self.fault_fired) >= 0.5

    def preview(self, dt_on):
        """What the fault would do to this on-time array, counters untouched."""
        if not self.active:
            return dt_on, False
        if self._would_fire():
            return dt_on, False
        dt_on = np.asarray(dt_on, dtype=float).copy()
        for i in self.thrusters:
            dt_on[i] = 0.0
        return dt_on, True

    def advance(self):
        """Consume one control cycle. Called exactly once per transmitted command."""
        if not self.active:
            return
        self.fault_cycle += 1
        if (self.fault_cycle * self.fault_fraction - self.fault_fired) >= 0.5:
            self.fault_fired += 1
        else:
            self.n_skips += 1

    def apply(self, dt_on):
        """Preview then advance, i.e. the hardware path where every command is sent."""
        out, skipped = self.preview(dt_on)
        self.advance()
        return out, skipped


# ==========================================================================
# the full chain
# ==========================================================================
class CommandChain:
    """Steps 2-9 with the persistent allocator memory carried across cycles."""

    def __init__(self, fault: DeterministicFault | None = None,
                 duty_ceiling=C.PWM_PERIOD, fmax=C.FMAX_PER_THRUSTER,
                 fit_offset=C.FIT_OFFSET, eta_smooth=None):
        self.use_hist = np.zeros(8)
        self.fault = fault if fault is not None else DeterministicFault(active=False)
        # sweep knobs (Sec 12); hardware values are the defaults
        self.duty_ceiling = float(duty_ceiling)
        self.fmax = float(fmax)
        self.fit_offset = float(fit_offset)
        # smooth-eta is a DISTINCT intervention from the pulse skip, never
        # relabelled as "x% effectiveness" of it
        self.eta_smooth = eta_smooth

    def duty_from_force(self, F):
        dt_on = C.FIT_SLOPE * np.asarray(F, dtype=float) / C.F_CL + self.fit_offset
        return np.clip(dt_on, 0.0, self.duty_ceiling)

    def trial(self, u_star, psi):
        """Run steps 2-9 WITHOUT mutating allocator memory or the fault counter.

        Algorithm 1 requires that candidate and fallback are both trial-allocated
        from the same frozen sigma_q and intended transmission slot, and that only
        the chosen duty vector is transmitted with its memory update committed.
        Re-allocating a stored fallback after mutating allocator memory would
        invalidate its earlier check.
        """
        info = {}
        u = cap_wrench_heading_first(np.asarray(u_star, dtype=float))  # step 2
        u = tiny_axis_zero(u)                                          # step 3
        u = safety_filter(u)                                           # step 4
        u = u * C.THRUST_GAIN                                          # step 5
        u = cap_wrench_heading_first(u)                                # step 6
        info["u_commanded"] = u.copy()  # this is what /sc2/mpc_output logs

        F = allocate(u, psi, self.use_hist, fmax=self.fmax)            # step 7
        info["F_alloc"] = F.copy()
        info["tau_alloc_achieved"] = alloc_matrix(psi) @ F

        dt_on = self.duty_from_force(F)                                # step 8
        dt_on = apply_min_pulse(dt_on, F)
        dt_on = condense_pairs_by_dt(dt_on, F)
        info["dt_on_pre_fault"] = dt_on.copy()

        # step 9 is previewed here without advancing the fault counter, so a trial
        # allocation cannot change the deterministic skip phase
        dt_on, skipped = self.fault.preview(dt_on)
        info["dt_on"] = dt_on.copy()
        info["fault_skip"] = skipped

        valve = np.full(8, C.VALVE_THRUST)
        if self.eta_smooth is not None:
            valve = valve * self.eta_smooth
        f_avg = valve * dt_on / C.TS
        info["f_avg"] = f_avg.copy()
        # transmitted-equivalent wrench: what the allocator geometry delivers
        info["u_applied"] = alloc_matrix(psi) @ f_avg
        info["_F_for_commit"] = F
        return info["u_applied"].copy(), info

    def commit(self, info):
        """Transmit: advance the fault counter and the allocator EWMA exactly once."""
        self.fault.advance()
        self.use_hist = update_use_hist(self.use_hist, info["_F_for_commit"])

    def __call__(self, u_star, psi):
        """Trial then immediately commit. This is the hardware behaviour: there was
        no acceptance check, so every allocation was transmitted."""
        u_applied, info = self.trial(u_star, psi)
        self.commit(info)
        return u_applied, info


# ==========================================================================
# true plant integration
# ==========================================================================
def plant_step(x, dt_on, psi_hold, substeps=C.PLANT_SUBSTEPS, valve=C.VALVE_THRUST,
               eta_smooth=None, mass=C.MASS, jzz=C.JZZ, drag=0.0, yaw_damp=0.0):
    """Integrate the continuous plant at Ts/substeps with left-aligned pulses.

    Pulse timing is resolved inside the slot rather than averaged, so the 12 ms
    minimum pulse and the 40 ms ceiling act on the true trajectory. `psi_hold` is
    the yaw used by the allocator for this slot (allocation is computed once per
    control cycle, not re-rotated mid-slot).
    """
    x = np.asarray(x, dtype=float).copy()
    h = C.TS / substeps
    v = np.full(8, valve, dtype=float)
    if eta_smooth is not None:
        v = v * eta_smooth
    A = alloc_matrix(psi_hold)
    for s in range(substeps):
        t0 = s * h
        t1 = t0 + h
        # fraction of this substep for which each valve is open (left-aligned)
        frac = np.clip((np.asarray(dt_on) - t0) / h, 0.0, 1.0)
        f = v * frac
        u = A @ f
        ax = u[0] / mass - drag * x[2]
        ay = u[1] / mass - drag * x[3]
        az = u[2] / jzz - yaw_damp * x[5]
        x[0] += h * x[2] + 0.5 * h * h * ax
        x[1] += h * x[3] + 0.5 * h * h * ay
        x[2] += h * ax
        x[3] += h * ay
        x[4] = wrap_pi(x[4] + h * x[5] + 0.5 * h * h * az)
        x[5] += h * az
    return x

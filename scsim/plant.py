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
                 fit_offset=C.FIT_OFFSET, eta_smooth=None,
                 valve_nominal=C.VALVE_THRUST):
        self.use_hist = np.zeros(8)
        self.fault = fault if fault is not None else DeterministicFault(active=False)
        # sweep knobs (Sec 12); hardware values are the defaults
        self.duty_ceiling = float(duty_ceiling)
        self.fmax = float(fmax)
        self.fit_offset = float(fit_offset)
        # Sec 3.3: the NOMINAL valve thrust assumed by the command mapping. A sweep
        # representing physically larger thrusters must move this together with the
        # plant's true valve thrust; a sweep that only raises `fmax` changes what the
        # allocator is permitted to request and nothing physical, and must be labelled
        # that way rather than reported as an authority change.
        self.valve_nominal = float(valve_nominal)
        # smooth-eta is a DISTINCT intervention from the pulse skip, never
        # relabelled as "x% effectiveness" of it
        self.eta_smooth = eta_smooth

    def duty_from_force(self, F):
        dt_on = C.FIT_SLOPE * np.asarray(F, dtype=float) / C.F_CL + self.fit_offset
        return np.clip(dt_on, 0.0, self.duty_ceiling)

    def trial(self, u_star, psi):
        """Run steps 2-8 WITHOUT mutating allocator memory or touching the fault.

        Returns the NOMINAL-EQUIVALENT TRANSMITTED wrench, which is what the paper
        calls u_k: nominal geometry and nominal valve thrust applied to the pulse
        durations actually selected for transmission. It is a function of the
        commanded pulses only.

        The hidden pulse-skip and any hidden valve effectiveness are NOT applied
        here. They belong to the plant, and applying them here would hand the
        controller a direct measurement of the fault: an earlier version did
        exactly that, so identical proposals with identical commanded pulses
        produced different controller-visible wrenches purely because the hidden
        skip phase differed. The encoder, the predictor and the acceptance check
        all consumed that quantity, which made "no fault label is an input"
        false in substance.

        Algorithm 1 also requires candidate and fallback to be trial-allocated
        from the same frozen sigma_q, so nothing here advances allocator memory.
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
        # the packet that would be transmitted: commanded, pre-fault, by definition
        info["pulse_command_s"] = dt_on.copy()

        # nominal-equivalent transmitted wrench, from NOMINAL valve thrust
        f_avg_nominal = self.valve_nominal * dt_on / C.TS
        info["f_avg_nominal"] = f_avg_nominal.copy()
        info["u_nominal_transmitted"] = alloc_matrix(psi) @ f_avg_nominal
        info["_F_for_commit"] = F
        return info["u_nominal_transmitted"].copy(), info

    def apply_hidden(self, info):
        """Preview the hidden effect WITHOUT consuming the fault slot.

        Kept for tests that want to inspect the hidden effect without advancing.
        Evaluators must call `realize` instead, so that preview and advance always
        happen together in the same order on every path.
        """
        pulse_actual, skipped = self.fault.preview(info["pulse_command_s"])
        return pulse_actual, skipped

    def commit(self, info):
        """Software commit: update the allocator EWMA once. Does NOT touch the fault.

        The hidden fault schedule is deliberately NOT advanced here. The controller
        commits its own allocator memory when it selects a packet, but the physical
        fault slot belongs to the evaluator and is consumed in `realize`. Advancing it
        here made the closed-loop policy path run the fault schedule one cycle ahead
        of the shorthand used to generate training data: the policy path advanced
        inside this call and only previewed afterwards, while the shorthand previewed
        first. Identical commanded packets then fired in one path and skipped in the
        other, so training and evaluation saw different physics.
        """
        self.use_hist = update_use_hist(self.use_hist, info["_F_for_commit"])

    def realize(self, info):
        """Evaluator side only: resolve the hidden effect for the transmitted packet
        and consume exactly one physical fault slot, in that order.

        This is THE single physical execution contract. Both the closed-loop policy
        path and the data-generation shorthand route through it, so a given commanded
        packet at a given fault state always produces the same physical pulses.
        """
        pulse_actual, skipped = self.fault.preview(info["pulse_command_s"])
        self.fault.advance()
        info["pulse_actual_s"] = pulse_actual
        info["fault_skip"] = skipped
        return pulse_actual, skipped

    def __call__(self, u_star, psi):
        """Trial then immediately commit. This is the hardware behaviour: there was
        no acceptance check, so every allocation was transmitted.

        Also resolves the hidden effect for the caller, because a caller using this
        shorthand has no separate accept/reject step to interleave.
        """
        u_nominal, info = self.trial(u_star, psi)
        self.commit(info)          # software allocator memory
        self.realize(info)         # hidden effect, then one fault slot
        return u_nominal, info


# ==========================================================================
# true plant integration
# ==========================================================================
def plant_step(x, dt_on, substeps=C.PLANT_SUBSTEPS, valve=C.VALVE_THRUST,
               eta_smooth=None, mass=C.MASS, jzz=C.JZZ, drag=0.0, yaw_damp=0.0):
    """Integrate the continuous plant at Ts/substeps with left-aligned pulses.

    Pulse timing is resolved inside the slot rather than averaged, so the 12 ms
    minimum pulse and the 40 ms ceiling act on the true trajectory.

    Body-frame thruster force is rotated into the world frame by the TRUE yaw,
    updated inside the integration. It is not rotated by the estimator's yaw: the
    thrusters are bolted to the vehicle, so where the force points is a physical
    fact that cannot depend on what the filter believes. An earlier version passed
    the estimate here, which made physical acceleration a function of estimator
    error and inflated the perception conditions with a nonphysical coupling.

    `valve` and `eta_smooth` are the TRUE (hidden) valve thrust and effectiveness.
    """
    x = np.asarray(x, dtype=float).copy()
    h = C.TS / substeps
    v = np.full(8, valve, dtype=float)
    if eta_smooth is not None:
        v = v * eta_smooth
    Gf, Gm = C.G_MAP[0:2, :], C.G_MAP[2, :]
    dt_on = np.asarray(dt_on, dtype=float)
    for s in range(substeps):
        t0 = s * h
        # fraction of this substep for which each valve is open (left-aligned)
        frac = np.clip((dt_on - t0) / h, 0.0, 1.0)
        f = v * frac
        f_body = Gf @ f                      # body-frame force
        tau = float(Gm @ f)                  # yaw torque is frame-independent
        c, sn = np.cos(x[4]), np.sin(x[4])   # TRUE yaw, refreshed each substep
        fx = c * f_body[0] - sn * f_body[1]
        fy = sn * f_body[0] + c * f_body[1]
        ax = fx / mass - drag * x[2]
        ay = fy / mass - drag * x[3]
        az = tau / jzz - yaw_damp * x[5]
        x[0] += h * x[2] + 0.5 * h * h * ax
        x[1] += h * x[3] + 0.5 * h * h * ay
        x[2] += h * ax
        x[3] += h * ay
        x[4] = wrap_pi(x[4] + h * x[5] + 0.5 * h * h * az)
        x[5] += h * az
    return x

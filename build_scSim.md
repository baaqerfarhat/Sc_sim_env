# Simulation build specification

Prepared 16 September 2026. Consolidates `Simulation_Validation_Protocol.md`, the Jetson code answers in `answers.md`, and measurements taken from the logs in `rovio_ws/experiments/`.

Every parameter below is either **confirmed from Jetson code**, **measured from logs**, or explicitly marked **OPEN** with a provisional value. Nothing here is invented without a label.

## 0. Locked decisions

| Decision | Choice |
|---|---|
| Platform | Planar 3-DOF spacecraft. No new robot platform. |
| Fidelity | Full documented chain: deadband, gain, caps, 8-thruster QP allocation, duty law, minimum-pulse floor, deterministic fault skip. |
| Plant vs predictor | Plant = full chain. Predictor = `JetsonNominalDynamics` + learned residual. Never roll the plant from the learned model. |
| Hardware anchoring | Required before any comparison runs. Sim must reproduce the measured targets in Section 7. |
| MPC cost | Implement manuscript Eq. (16) pseudo-Huber as the **proposed** method. State plainly that the deployed hardware ran plain `sum_squares` with N = 12. |
| Certificate | Sweep authority and horizon to locate where the region is nonempty; report where the hardware configuration sits relative to that boundary. |
| Runtime | Plain Python / numpy, no ROS, no Gazebo. Episode budget is ~5000 episodes × 600 steps. |

## 1. State, control, timing

- State `x = [x, y, vx, vy, psi, r]`, world frame, `psi` wrapped to [−π, π]. **Confirmed** — matches `sc_dynamics.py` and the Jetson. Note the manuscript writes `[px, py, psi, vx, vy, omega]`; fix the manuscript, not the code.
- Control `u = [tau_x, tau_y, Mz]`, forces in the **inertial/world** frame. **Confirmed** — never rotated by `psi` in the prediction model. `psi` enters only in the allocator's `A(psi)`.
- `Ts = 0.1` s, control rate 10 Hz, hardcoded. **Confirmed.**
- Measured achieved timing: dt median 0.1000 s, p95 0.1006 s, max 0.111 s. The loop held rate despite having no deadline mechanism. Simulate exact 10 Hz; jitter is not a material effect.

## 2. Predictor (what the MPC believes)

Use `JetsonNominalDynamics` unchanged. **Confirmed** exactly:

```
ax = tau_x/m,  ay = tau_y/m,  az = Mz/Jzz
p+   = p + dt*v + 0.5*dt^2*a      (exact ZOH, includes the 1/2 dt^2 term)
v+   = v + dt*a
psi+ = wrap(psi + dt*r)           (forward Euler, NO 1/2 dt^2 term)
r+   = r + dt*az
```

`m = 25.0` kg, `Jzz = 2.0` kg·m², **no drag, no damping**.

**OPEN:** mass and inertia are round numbers with no measurement provenance. Treat as nominal. A mass error is confounded with the `thrust_gain` and duty-ceiling effects, so this is worth a bench measurement.

The learned residual is added on top of this, in estimate space, predicting the **next estimate** per manuscript Eq. (3).

## 3. Plant (what actually happens)

Integrate the continuous plant at `Ts/10` or finer; refine if pulse timing demands it. The plant is the predictor's physics **plus** the following chain, applied in exactly this order. **Confirmed** from `send_thruster_commands()`.

1. MPC solves → `u*`
2. `cap_wrench_heading_first`: clip to (±5.0 N, ±5.0 N, ±0.8 N·m). Yaw limit is `yaw_share × Mz_max = 0.40 × 2.0`.
3. **Tiny-axis zeroing**: if one force axis is < 5% of the dominant axis, zero it.
4. `safety_filter`: deadband **0.1 N** on force axes, **0.02 N·m** on yaw, applied to the **commanded wrench before allocation**.
5. `thrust_gain = 2.0`, multiplying **all three** components including yaw.
6. `cap_wrench_heading_first` **again**, same limits.
7. QP allocation (Section 4).
8. Duty conversion (Section 5).
9. **Fault pulse-skip** (Section 6).
10. Publish.

Because step 6 repeats the cap after the ×2 in step 5, `thrust_gain` doubles only the region below half the caps and is a no-op above 2.5 N / 0.4 N·m. Do not model it as a clean factor of two.

## 4. Allocation

Thruster order, indices 0–7:

`[FX−MZ−, FX−MZ+, FY−MZ−, FY−MZ+, FX+MZ−, FX+MZ+, FY+MZ−, FY+MZ+]`

With `geom_l = geom_b = 0.20` m:

```
G = [[-1, -1,  0,  0, +1, +1,  0,  0],
     [ 0,  0, -1, -1,  0,  0, +1, +1],
     [-0.2, +0.2, -0.2, +0.2, -0.2, +0.2, -0.2, +0.2]]
```

Allocator uses `A(psi) = [Rz(psi) @ G[0:2] ; G[2]]` — force rows rotated to inertial, yaw row not.

Objective, **confirmed**:

```
min_F  || W_tau (A(psi) F - tau) ||^2
       + 1e-4 ||F||^2
       + 5e-4 * sum(F)
       + 1e-3 * F' diag(1 + 3h) F
s.t.   0 <= F <= 1.2
```

- `W_tau = diag(1, 1, 8)` — yaw weighted 8× the force axes, so **yaw is preserved at the expense of translation** when the request is unachievable.
- Achieved wrench is a **soft penalty, not an equality**. Only the bounds are hard.
- `h` is normalized cumulative usage, from `use_hist`, an EWMA accumulator with **decay 0.995 updated every cycle**. This is persistent allocator memory — allocation for a given `tau` depends on the whole firing history. Must be carried in the sim and included in the certificate's allocator-state domain.
- Unachievable requests are **not detected**: no scaling, no infeasible return, just the least-squares compromise.
- Strictly convex, so unique and deterministic given history. `‖tau‖ < 1e-6` returns zeros.
- `use_accumulator = False`; the `dt_accum` on-time carry-forward is **disabled**.
- `condense_pairs_by_dt` merges opposing pairs (0,4), (1,5), (2,6), (3,7) only when both on-times are below the minimum pulse **and** net XY contribution is negligible.

**Achievable set** — critical, and much smaller than the MPC's declared box:

| Quantity | MPC believes | Physically achievable |
|---|---|---|
| \|F_x\|, \|F_y\| | 5.0 N | 2.4 N (two thrusters × 1.2 N) |
| \|M_z\| | 2.0 N·m | 0.96 N·m (pure couple, indices 1,3,5,7) |

The MPC routinely commands wrenches outside the achievable set. For the post-allocation command check, **this structural gap is the dominant effect, not the fault.** The theory's admissible input set `U` must be the achievable set, not the declared box.

## 5. Duty conversion and pulse realization

PWM period `f_cl = 25.0` Hz → `T = 40` ms. Control slot is **100 ms**. So maximum realizable duty is **40% of a slot** — this is the single largest authority limiter.

```
dt_on = 4.829 * F / 25 - 0.07686      seconds
dt_on = clip(dt_on, 0, 0.040)
```

`fit_slope = 4.829`, `fit_offset = -0.07686` s, described in code as "Table 6 @ 50 psi", **uniform across all eight thrusters** with no per-thruster calibration.

Consequences to reproduce faithfully:
- Below `F ≈ 0.40` N the linear term yields near-zero on-time.
- Above `F ≈ 0.65` N it saturates at the 40 ms ceiling.
- So the usable proportional band is only about **0.40–0.65 N**; everything above is clipped.

Minimum-pulse floor, `min_on_time_ms = 12.0`, in the `use_accumulator = False` branch:
- `F > 0.001` N → pulse **stretched up to 12 ms**
- `F <= 0.001` N → **zeroed**
- Neither dropped nor accumulated.

Net realizable average force per thruster is therefore `{0} ∪ [0.12, 0.40] × F_valve`. This on/off quantization with a dead band and a hard ceiling is exactly the mechanism that can invalidate a feasible proposed command, so it is the core of the post-allocation-check experiment.

**OPEN, and load-bearing:** whether `F` in the duty law is valve thrust or a commanded average force. The whole authority calculation rests on this. Provisional reading: `F` is commanded thrust, the valve delivers ~1.2 N when open, average force = `1.2 × dt_on / 0.100`. This reading reproduces the measured acceleration (Section 7), which is why it is provisional-but-trusted.

**OPEN:** pulse phase/centering within the slot, and valve rise/fall time. Requires INSboard firmware. Provisional: left-aligned pulse, instantaneous valve. Note as a fidelity limitation.

## 6. Fault injection

**Confirmed**, and different from what the protocol assumed. Not a smooth effectiveness scale.

```
fault_thrusters = [6, 7]            # T7, T8 (1-based) = FY+MZ-, FY+MZ+
fault_cycle  += 1
should_fire = (fault_cycle * fault_fraction - fault_fired) >= 0.5
if should_fire: fault_fired += 1
else:           dt_ms[6] = dt_ms[7] = 0.0
```

- At `fault_fraction = 0.7`, on-time for both faulted thrusters is zeroed on ~30% of control cycles, in a **fixed regular pattern**. About 3 skips per second at 10 Hz.
- **No RNG, nothing seeded.** Fully deterministic from the cycle count, so sim reproduction is exact.
- `fmax` stays 1.2 N for all eight thrusters at every level. There is no thrust reduction.
- Always T7/T8, at every level, not level-dependent.
- **Applied after allocation**, on the final on-time array. The allocator and MPC never know. Also applied **after** `/sc2/mpc_output` is published, so the fault is invisible in the logged wrench.
- **Onset is a step at t = 0**, constant for the entire run. No ramp, no schedule.

Both faulted thrusters push **+Y** and cover both yaw signs, so the fault degrades +Y translation authority and both yaw directions at once.

For the sim, implement this mechanism exactly for hardware-matched runs. A separate smooth-η mechanism may be added for the severity sweep, but must be labeled as a distinct intervention, not as "70% effectiveness."

**Do not reuse the Vicon-stack fault semantics** (all eight thrusters at 60% with a timed boost window) — that is a different controller file and a different intervention.

## 7. Hardware anchoring targets

The sim is not credible until it reproduces these, measured from `rovio_ws/experiments/`. Fit the unmodeled layer to hit them; do not tune the estimator to be good.

| Quantity | Measured target | Source |
|---|---|---|
| Achieved linear acceleration | p95 **0.025–0.063** m/s², median ≈ 0.035 | Smoothed Vicon differencing, C1 runs |
| Chain prediction of same | 0.96 N / 25 kg = **0.038** m/s² | Independent, agrees — validates the chain |
| Estimation error, healthy | \|dx\| p95 **0.22–0.65** m, dψ p95 **0.10–0.27** rad | `states` − `vicon_states`, C1 |
| Estimation error, occluded, zero context | \|dx\| p95 **0.79–4.86** m, dψ up to **2.72** rad | V2 |
| Estimation error, occluded, learned | \|dx\| p95 **0.33–1.03** m | V4 |
| Position RMSE, healthy | ≈ **1.03** m, peak ≈ 2.01 m | Table I |
| Control rate | dt median 0.1000 s, p95 0.1006 s | Logged timestamps |

The independent agreement between measured acceleration and the chain calculation is the strongest validation available. **Reproduce it first, before anything else is built on top.**

Exclude the V4 batch's constant ~1.1 rad yaw offset from envelope fitting — it is very likely a `flip_x`-versus-yaw handedness inconsistency interacting with the initial pose, not estimation error.

## 8. Estimator surrogate

Do not build a good estimator. Build **this** one, because its lag is the dominant contributor to the measured error and therefore to the certificate's estimation envelope.

Three stages, **confirmed**:

1. **Visual odometry surrogate** for ROVIO: monocular, 25 max features, drift-prone, no absolute reference after initialization. Model at the measurement level: pose with noise, bias drift, and dropout. Intrinsics if needed: `cam0.yaml`, fx 649.919, fy 649.516, cx 310.643, cy 211.249.
2. **One-shot alignment** at t₀ against ground truth, then never again. This anchors the origin and initial heading, so drift is measured relative to a truth-defined origin.
3. **The controller's own filter layer** — the part that matters most:
   - Position LPF, **hardcoded τ = 0.5 s**, `alpha = 1 − exp(−dt/0.5)`. The declared parameters `pos_lpf_tau_s = 0.4` and `yaw_lpf_tau_s = 0.3` are **dead code**; do not use them.
   - Yaw LPF, also **τ = 0.5 s**, on the sin/cos pair.
   - Velocity = `0.8 × d(LPF position)/dt + 0.2 × VO twist`, finite difference clipped to ±2 m/s, minimum dt 10 ms.
   - Yaw rate = `0.7 × d(filtered yaw)/dt + 0.3 × VO angular.z`, clipped to ±2 rad/s.

Gating, **confirmed**: position jump > 0.5 m within < 0.2 s → rejected, previous retained. Yaw jump > 90° within < 0.2 s → rejected.

**The IMU does not enter the controller's state estimate at all** — the callback subscribes to the wrong topic and never fires. Do not model an IMU channel into the controller. (ROVIO uses IMU internally; that stays inside the VO surrogate.)

Missing-measurement behavior: the `hold` branch runs unconditionally and re-assigns an already-filtered state, so it is functionally a no-op and the `predict` branch is unreachable. Reproduce as: on missing pose, the filter simply does not update, and the LPF continues from its last value.

**Perception degradation is modeled here**, at the measurement/estimator level. The occlusion was **physical tape on the lens** — there is no code path, no logged onset, and no logged duration. Model as increased pose noise, bias growth, and dropout blocks; take onset and duration from lab notes. Describe it in the paper as a measurement-level perception-degradation experiment, never as reproduced visual occlusion.

Covariance and feature count are **not available** from the logs: ROVIO published a full 6×6 covariance, but `rovio_aligner.py` builds a fresh message and never copies the fields, so the channel is all zeros. Feature count was never published as a scalar. A two-line aligner fix would recover both for future runs.

## 9. MPC to implement

Implement manuscript **Eq. (16)** pseudo-Huber as the proposed method. Record the state ordering, every `w_j` and `s_j`, `R_u`, `Q_N`, and the feedforward regularization in the run manifest.

For the hardware-matched reference variant, the deployed controller was, **confirmed**:

- Plain `cp.sum_squares`, no pseudo-Huber anywhere.
- **N = 12**, not 10. Preview 1.2 s.
- Weights and floors:

| Weight | Nominal | Floor |
|---|---|---|
| `w_pos` | 30.0 | 5.0 |
| `w_vel` | 5.0 | 1.0 |
| `w_psi` | 0.1 | 0.01 |
| `w_r` | 0.05 | 0.01 |
| `w_u` | 0.1 | 0.01 |
| `w_du` | 1.0 | 0.1 |

- Two slack weights: `w_ang_slack = 2e3` quadratic on angular-rate slack, `w_headband = 10.0` linear on heading-band slack.
- `Q_N = 4Q` on position, velocity, yaw, yaw rate. No terminal input term.
- Constraints: hard input box (±5, ±5, ±2); `|r| ≤ 1.8` soft via slack; `|r| ≤ 2.5` hard; `|psi − psi_ref| ≤ 15°` soft via slack.
- **No position, velocity, corridor, or terminal-set constraints. No first-action constraint.** Input rate is penalized but never constrained.
- Solver OSQP, first pass `eps_abs = eps_rel = 1e-2`, `polish=False`, `warm_start=True`, retry once at 1e-3 with polish. **First-pass tolerances are loose, so most logged solutions are coarse** — reproduce this if matching hardware behavior.
- Solver-failure fallback is a near-coast: `Fx = clip(0.5·e_x, ±0.2)`, `Fy = clip(0.5·e_y, ±0.2)`, `Mz = clip(0.1·e_head, ±0.02)`.

The proposed method adds the first-action condition, eligibility gate, post-allocation acceptance check, and stored fallback from Sections III–IV. None of these existed on hardware.

## 10. Reference and task

**Confirmed**, and not what the protocol assumed. The ROVIO campaign used `traj_simple_y.py`, a **setpoint sequence with position-triggered transitions**, not a time-parameterized trajectory:

- Stage 1: hold `start + [0, −2.0]`
- Transition when `|y − y_wp1| < 0.15` m
- Stage 2: hold `start + [+1.0, −2.0]`
- Total commanded path **3.0 m Manhattan**, published at 50 Hz
- **`vel_setpt` and `acc_setpt` are always zero**
- No termination; the final setpoint republishes forever

Verified in the logs: 2–3 unique setpoints per run, consistent with this structure.

This matters twice over. A smooth time-parameterized reference will **not** reproduce the observed behavior, since the step at the 15 cm switch is a large part of the dynamics. And a step reference with `v_ref ≡ 0` gives a **large reference defect `b_r`**, which directly inflates `s_cert`. Include both a step-setpoint family (hardware-matched) and a dynamically feasible smooth family (for the certificate to have a chance), and report them separately.

`L_task` provisional: **3.0 m**, the commanded path length.

**OPEN:** table dimensions, corridor and keep-out boundaries do not exist anywhere in the Jetson code — there is no spatial safety envelope of any kind. Measure the table and supply these.

**OPEN:** no physically derived docking tolerance exists. The only tolerance in code is `TARGET_REACHED_THRESHOLD = 0.05` m, a hardcoded constant that zeros the wrench but does not end the run. Define success tolerances from the docking mechanism geometry, and sanity-check them against the estimation error in Section 7 — a 0.05 m tolerance is an order of magnitude below the healthy estimation error, so it cannot be certified.

Episode termination: **no code path ends a run.** Observed early stops (73.7 s, 89.9 s, 50.9 s against 120/150 s requests) were operator stops once the vehicle reached its final position, with variation from floor dust and push differences. Benign, but it means episode length is not a controlled variable — **score on a fixed onset-relative window, not whole-run averages.**

## 11. Context integration

Two architectures existed. Keep them distinct.

**April/May campaigns** — `/sc2/latent_z` only, 32 floats, load-bearing:
- `set_latent()` mapped z → six weights via `softplus(a_w·z + b_w) + weight_mins`, and z → `delta` via a sigmoid, using `jetson_actor_params.npz`.
- **There was no dynamics residual at all.** None existed in the prediction model.
- So these runs are **context-modulated MPC tuning**, not learned-dynamics MPC.

**June onward** — adds `/sc2/mpc_weights`, `/sc2/mpc_delta`, `/sc2/dyn_residual`. Residual is a single `cp.Parameter(6)` added **identically at every horizon step**, constant over the horizon. `deployment_manifest.json` describes only this architecture, and its "diagnostics only" label for `latent_z` is **wrong for April/May**.

In **neither** architecture did z enter the prediction model directly. `m` and `Jzz` were always fixed constants, never learned or modulated.

`delta` is multiplicative tightening, `limit = (1 − δ) × nominal`, on `Fx_max`, `Fy_max`, `Mz_max`, `ang_vel_max`, `psi_tol`. **Not** applied to the hard `ang_vel_guard`.

Staleness threshold 0.3 s. Stale means nominal weights and `delta = 0`.

**A trap for any analysis of the logged weights.** Weights and tightened limits are baked into the CVXPY graph as constants for DPP compliance, so rebuilds are gated:
- April/May: rebuild only when `‖Δz‖ > 2.0`. **The solver could run many consecutive cycles with stale weights while the logs recorded freshly computed values.** Logged weights are not necessarily active weights.
- June onward: > 25% relative change on any weight, or > 0.02 absolute on `delta`.

Rebuild events are detectable as step changes in `solve_time_ms`. Do not assume logged weights were active for April/May.

## 12. Authority and horizon sweep

The reason for the sweep: at hardware authority the certificate is very likely empty. Establish where the boundary is.

The arithmetic to beat. At 0.038 m/s², an N = 12 preview of 1.2 s moves the vehicle about **3 cm**, against tracking errors of 1–2 m. Per-step contraction is therefore tiny, λ sits just below 1, and since

```
s_cert = (b_r + d_cert + eta) / (1 - lambda)
```

`s_cert` becomes enormous and the strict margin `s_cert < R ≤ min(R_U, R_corridor, R_chart)` fails. The step reference compounds it by making `b_r` large.

Sweep axes, with the hardware value first:

| Axis | Hardware | Sweep range | Why |
|---|---|---|---|
| Duty ceiling | 0.40 (40 ms / 100 ms) | 0.40 → 1.0 | Largest single authority limiter |
| Horizon N | 12 | 12 → 50 | Determines achievable per-solve correction |
| Per-thruster `fmax` | 1.2 N | 1.2 → 4.0 N | Raises the achievable set |
| Duty-law offset | −0.07686 s | → 0 | Removes the low-thrust dead band |
| Reference family | step setpoints | → smooth feasible | Reduces `b_r` |

Report the certificate's binding bound at each point, and mark where the hardware configuration sits. The deliverable is a boundary in this space, plus a plain statement of which term binds on the hardware side.

## 13. Build order

Do not proceed to a stage until the previous one matches its target.

1. **Plant, allocator, duty law, fault — open loop.** Verify the achievable set (2.4 N per force axis, 0.96 N·m yaw couple), the 0.40–0.65 N proportional band, the 12 ms stretch behavior, and the deterministic 3-skips-per-10-cycles fault pattern.
2. **Closed loop with `JetsonNominalDynamics` + Eq. (16) MPC.** Verify achieved acceleration reproduces p95 0.025–0.063 m/s² and position RMSE lands near 1 m on the step reference. **This is the gate.** If it fails, stop and fix the plant.
3. **Estimator surrogate.** Verify healthy estimation error reproduces \|dx\| p95 0.22–0.65 m and dψ p95 0.10–0.27 rad.
4. **Perception degradation.** Verify the occluded band, 0.79–4.86 m for the degraded case.
5. **Data generation, probe branches, behavioral supervision, training.** Five splits, no leakage, three seeds.
6. **Baselines and the comparison table.** Trained constant-context, adaptive MPC, no-behavioral-loss, full, full-without-post-allocation-check.
7. **Certificate.** LMIs, interval verification, freeze, then the single calibration pass. Then the authority/horizon sweep.

## 14. Open items to resolve

Blocking the plant build:
- Duty-law semantics: is `F` valve thrust or commanded average force? Provisional reading in Section 5 reproduces the measured acceleration, so this is low-risk but should be confirmed.

Blocking certificate numbers:
- Table dimensions and any corridor boundary, for `R_corridor`.
- A physically derived docking tolerance, for the success definition.
- Measured mass and inertia with tolerance.

Fidelity improvements, non-blocking:
- INSboard firmware: pulse phase within the slot, valve rise/fall time.
- Supply-pressure history across the campaign; the duty fit assumes 50 psi and pressure was never logged.
- Occlusion onset and duration from lab notes.
- Air-bearing levelness and any residual tilt.

Recoverable without asking anyone:
- Translational drag and yaw damping — fit from C1 runs with `identify_nominal()`.
- Achieved rate and jitter — already computed, Section 7.
- Whether logged weights were active — detect rebuild events via `solve_time_ms` step changes.

## 15. Manuscript items surfaced by this exercise

Not simulation work, but they came out of the code reading and should not be lost.

- Eq. (16) pseudo-Huber and N = 10 describe neither the deployed controller nor the identified plant. Keep Eq. (16) as the proposed method and state the deployed variant plainly.
- State ordering in the manuscript disagrees with all code.
- Fig. 3's "oracle" label should read "hand-tuned." The Jetson cannot confirm this either way — hand-set and inferred z are indistinguishable from its side — so it must be settled from the WSL-side `build_oracle_z()` evidence.
- April/May runs had no dynamics residual, so they support context-modulated tuning rather than learned-dynamics MPC. Scope those results accordingly.
- The MPC's declared input box is physically unreachable. Any claim that transmitted commands stayed within `U` must use the achievable set.
- The one-shot Vicon anchor at t₀ means the system is not fully Vicon-free. Continuous Vicon never entered control or estimation — `cb_vicon_ground_truth` reaches only the CSV logger — but the origin and initial heading are inherited from Vicon, and that should be stated.
- Two camera calibrations in the tree disagree by ~16% in focal length. ROVIO reads `cam0.yaml`; the driver publishes the other. Possible contributor to scale error.

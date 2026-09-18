> # ⚠ SUPERSEDED — DO NOT SEND OR CITE
>
> This is the **voided v1 development campaign**, kept only for provenance.
> Four defects confirmed in the code that produced it invalidate its numbers:
>
> 1. The controller-visible wrench was computed from **post-fault** pulses, so the
>    context encoder, the predictor and the acceptance check were all **observing the
>    hidden actuation fault directly**. The paper's no-fault-label premise is false for
>    every number below.
> 2. The plant rotated body thruster force into the world frame with the **estimated**
>    yaw, so physical acceleration depended on estimator error.
> 3. A fallback that **failed its own acceptance check** was transmitted anyway.
> 4. The interval Jacobian enclosure was **unsound** (falsifiable by sampling), so every
>    certificate number was meaningless.
>
> Its configuration hash coincides with the corrected run's for some stages, so the hash
> **cannot** be used to tell them apart. Use the run id instead.
>
> **The report to send is `results/results.md` (run id `v2-corrected`).**

---

# Simulation results

Companion evidence for *Multimodal Context Learning for Actuation and Perception
Fault-Tolerant Model Predictive Control*, targeting the two items the abstract
lists as unvalidated: the behavioural-supervision gain and the numerical recovery
certificate.

Configuration manifest hash: `155bb5109e93c543`.

Figures: `results/figures/`.

---

## 0. Verdicts at a glance

| Paper claim | Verdict | Evidence |
|---|---|---|
| Simulation reproduces the hardware envelopes | **supported** | 10/10 anchoring gates pass; accel p95 0.0543 m/s^2 inside the measured 0.025-0.063 band; Sec 1 |
| Behavioural-supervision gain (`L_impact`) | **not supported** | costs +0.059 to +0.085 m, 4/4 conditions significantly WORSE; no gain in prediction, retrieval or OOD transfer; Sec 2 |
| Inferring a *changing* context helps | **supported, small** | -0.028 to -0.010 m, 1/4 significant; Sec 3.1 |
| Learned context beats the hardware comparator | **supported** | -0.394 to -0.201 m, 4/4 significant; Sec 3 |
| Learned context beats adaptive MPC | **supported** | -0.676 to -0.379 m, 4/4 significant; Sec 3.1 |
| The post-allocation acceptance check is load-bearing | **supported, large** | -1.601 to -1.422 m, 4/4 significant; Sec 3.1, 3.3 |
| Recovery after onset is faster | **supported** | median t_rec 3.6 s vs 9.6 s for the comparator (recovery rate 99.6% vs 98.9%, both high, so time is the separating quantity); Sec 3 |
| Numerical recovery certificate | **not supported (empty)** | 0 of 2100 swept cells certify; boundary and binding terms located instead; Sec 4 |

The two items the abstract lists as unvalidated remain unvalidated, and this study says
so explicitly. What it does establish is the *architecture* around them: the learned
context input and the post-allocation acceptance check are both real, measurable, matched-comparison
effects, and the certificate analysis converts an empty region into two concrete design
requirements (a feasible reference and a Lipschitz-bounded residual).

---

## 1. The simulation environment and its hardware anchoring

A planar 3-DOF spacecraft simulator built to be a *replica of the flight stack*, not a
clean-room model of the same physics. Wherever the deployed Jetson code does something
unusual, the simulator reproduces the unusual thing: the 0.40 duty ceiling, the 5% tiny-axis
zeroing, the 12 ms minimum on-time, the 0.5 s position filter that is hardcoded while a 0.4 s
parameter sits unused, and the yaw share that turns a declared 2 N m cap into an
actual 0.80 N m. Every constant carries a provenance tag: **24 CONFIRMED** from the
deployment source, **4 OPEN** (no measurement provenance), **6 SIM** (a declared
study choice). The full manifest is hashed into every result file.

### 1.1 Layers, in the order a command passes through them

1. **Rigid body.** Planar double integrator, m = 25 kg, J_zz = 2.0 kg m^2, integrated at Ts/20 = 5 ms so that 12 ms pulses resolve. Control runs at 10 Hz.
2. **Safety filter on the commanded wrench.** Caps at (5, 5) N and 0.80 N m; zeroes a force axis below 5% of the dominant axis; applies dead bands of 0.1 N and 0.02 N m; then multiplies all three components by 2.
3. **Thruster allocation.** 8 fixed thrusters on a 0.20 m x 0.20 m body, 1.2 N each. Box-constrained weighted least squares with yaw weighted 8x, plus L2/L1/use-history regularisers and an EWMA (0.995) wear term. Solved exactly by bounded-variable least squares, and Stage 1 verifies the KKT conditions rather than trusting the solver.
4. **Duty law and pulse realisation.** duty = 4.829*F -0.07686 s (F in N), clipped to the 40 ms PWM period inside a 100 ms slot, so the duty ceiling is 0.40. Anything above 0.001 N is stretched to at least 12 ms; anything below is dropped. An open valve delivers 1.2 N.
5. **Fault injection.** Deterministic pulse skipping on thrusters (6, 7) (the FY+ pair), applied *after* allocation and after the logged wrench is published - which is exactly why the fault is invisible in the flight logs and must be inferred.
6. **Estimator stack.** A three-stage surrogate for the ROVIO pipeline: a visual-odometry measurement model, jump gating (0.5 m or 90 deg inside 0.2 s is rejected), and a 0.5 s low-pass with velocity blended 0.8 finite-difference / 0.2 VO twist. The controller sees only this estimate.

### 1.2 The one place parameters were fitted, and why that is not circular

The VO noise parameters are the **only** free quantities in the build. ROVIO's logged
covariance channel is all zeros and feature count was never published as a scalar, so there
is no measured noise parameter available. They were therefore fitted so that the *closed-loop*
estimation error reproduces the measured envelopes, which is the procedure the source
document prescribes: fit the unmodelled layer to hit the envelopes, do not tune the estimator
to be good. Three profiles result (healthy / mild / occluded).

The fit is also not doing the work the physics should: with **all VO noise set to zero** the
healthy error is still 0.157 m of 0.337 m (47%), so the envelope is dominated by the
0.5 s filter *lag*, not by the fitted noise. That is a structural property of the
deployed estimator, and it is reproduced rather than fitted.

### 1.3 What the controller is

Two MPC variants share one plant, one estimator and one allocator:

- **Hardware-matched.** Sum-of-squares cost, N = 12 (the deployed value, not the manuscript's 10), deployed weights, terminal scaling Q_N = 4Q, soft yaw-rate limit at 1.8 rad/s with a hard limit at 2.5, and the deliberately loose OSQP tolerance (1e-02) that the flight code uses. This is the variant Stage 2 anchors.
- **Proposed.** The pseudo-Huber cost of Eq. (16), solved by iterative majorisation, plus the learned context entering as a dynamics residual and reference feedforward.

The context encoder is a 3-layer, 4-head transformer over a 10-step causal
history of estimator innovations, modality availability, motion and applied commands, producing
a 32-dimensional latent. The residual is clipped to 0.5 per state in body frame, as
in the deployment code. No fault label, severity, or onset time is ever an input.

### 1.4 Scenario population and data

Episodes are 60 s (600 control steps) on the hardware step-setpoint task
(waypoints (0.0, -2.0) then (1.0, -2.0), position-triggered at 0.15 m). Impairment onset is drawn
uniformly in [15, 20] s. Four main conditions: healthy, actuator, perception, combined.

Every episode also draws plant mismatch, so the evaluation plant is never the predictor's
plant: mass and inertia at +/-10% (+/-15% in labelled stress cells) plus a small bounded drag and
yaw damping. Without this, prediction accuracy and certificate compliance would be partly
built in.

Training data: **360 parent episodes**, **216,000 transitions**, and **3832 probe branches** (229,920 extra transitions) used only for behavioural supervision. Splits are by *parent episode* - train, dev, fitting, calibration, test - so no window leaks across a split boundary. Normalisation statistics come from training data only.

### 1.5 Experimental discipline

The properties that make the comparisons worth quoting:

- **Matched draws.** For a given (condition, episode seed) every method sees the identical reference, disturbance, mismatch, estimator noise and onset. Trajectories diverge only through the control.
- **Reproducible.** Scenario draws are seeded by CRC32 of the draw key, not Python's per-process salted `hash`, so a re-run reproduces stored values to nine decimals. Manifest hash is recorded in every artefact.
- **3 training seeds** per learned method, with seed-level numbers shown, not only pooled intervals.
- **60 episodes per condition** on the test split; the parent episode is the bootstrap resampling unit, so overlapping windows and time samples are never treated as replicates.
- **Calibration is disjoint from test.** The recovery tolerance, eligibility radius R and acceptance allowance eta are all frozen on a separate calibration split before any test episode runs.
- **Trial/commit discipline.** The acceptance check is evaluated at the *transmitted-equivalent* wrench - after allocation, dead bands, duty quantisation and pulse realisation - not at the MPC's intended wrench, which is the only version that means anything on this hardware.

Open-loop verification of plant, allocator, duty law and fault injection: **29/29 checks pass** (Stage 1).

### 1.6 Hardware anchoring: the gates (Stages 1-4)

Nothing below is claimed until the simulation reproduces the measured
envelopes. These are gates, not results.

| Quantity | Hardware target | Simulation | In band |
|---|---|---|---|
| Achieved linear accel, p95 | 0.025-0.063 m/s^2 (measured) | 0.0543 m/s^2 | yes |
| Position RMSE, step reference | 1.034 m (Table I healthy) | 0.896 m | yes |
| Peak position error | 2.013 m | 2.000 m | yes |
| Healthy \|dx\| p95 | 0.22-0.65 m (C1) | 0.337 m | yes |
| Healthy dpsi p95 | 0.10-0.27 rad (C1) | 0.124 rad | yes |
| Occluded \|dx\| p95 | 0.79-4.86 m (V2) | 1.462 m | yes |

Open-loop plant, allocator, duty law and fault injection: **29/29 checks pass** (Stage 1).

Two facts from these stages matter for everything after:

- **78% of commanded wrenches lie outside the achievable set.** The structural authority gap, not the declared box, is what the theory's `U` must be.
- **The estimator's LPF lag is the dominant error contributor.** With all VO noise zeroed the healthy error is still 0.157 m of 0.337 m (47%), so the estimation envelope is a lag property, not a noise property.

---

## 2. Claim 1 - behavioural supervision gain

> *Abstract: "The behavioral-supervision gain ... remain[s] to be validated."*

`full` and `no_impact` share architecture, initial weights (same seed), data,
optimiser budget, epochs, learning rate, checkpoint rule and prediction-loss
weights. The single intentional difference is `lambda_I`.

Training set: 360 parent episodes, 216,000 transitions, 3832 probe branches (229,920 extra transitions).

### 2.1 The behavioural loss does optimise

| Model | lambda_I | L_impact first -> last epoch | dev one-step loss |
|---|---|---|---|
| `full_s0` | 1.0 | 0.1355 -> 0.0061 | 0.001573 |
| `no_impact_s0` | 0.0 | 0.0000 -> 0.0000 | 0.001238 |
| `full_s1` | 1.0 | 0.1358 -> 0.0071 | 0.001594 |
| `no_impact_s1` | 0.0 | 0.0000 -> 0.0000 | 0.001247 |
| `full_s2` | 1.0 | 0.1334 -> 0.0058 | 0.001605 |
| `no_impact_s2` | 0.0 | 0.0000 -> 0.0000 | 0.001226 |
| `const_s0` | 0.0 | 0.0000 -> 0.0000 | 0.001796 |
| `const_s1` | 0.0 | 0.0000 -> 0.0000 | 0.001795 |
| `const_s2` | 0.0 | 0.0000 -> 0.0000 | 0.001795 |

`L_impact` falls by a factor of ~22, so the behavioural geometry is genuinely being
shaped. Note the ordering of the one-step loss: `no_impact` fits transitions BEST.
The behavioural term is a constraint, and it costs one-step accuracy. The question
is therefore whether it buys closed-loop performance.

### 2.2 Retrieval: does the latent carry behavioural structure?

For each probe anchor, the nearest latent neighbour from a *different* episode is
retrieved and the behavioural signature distance actually incurred is reported.
`chance` is the same statistic under a random pairing. Ratio < 1 means the latent
retrieves behaviourally similar neighbours.

| Model | prediction error | retrieval error | chance | ratio |
|---|---|---|---|---|
| `full_s0` | 0.001708 | 1.0751 | 1.3089 | **0.821** |
| `full_s1` | 0.001726 | 1.0631 | 1.3089 | **0.812** |
| `full_s2` | 0.001738 | 1.0689 | 1.3089 | **0.817** |
| `no_impact_s0` | 0.001345 | 1.0318 | 1.3089 | **0.788** |
| `no_impact_s1` | 0.001368 | 1.0322 | 1.3089 | **0.789** |
| `no_impact_s2` | 0.001345 | 1.0547 | 1.3089 | **0.806** |
| `const_s0` | 0.001931 | 1.1873 | 1.3089 | **0.907** |
| `const_s1` | 0.001931 | 1.1873 | 1.3089 | **0.907** |
| `const_s2` | 0.001930 | 1.1873 | 1.3089 | **0.907** |

### 2.3 Closed-loop paired effect (the headline test)

Paired `full - no_impact`, block bootstrap over parent episodes (episodes are the
resampling unit; time samples and overlapping windows are not treated as
replicates). Negative = full is better.

| Condition | dRMSE (m) | 95% CI | blocks | significant |
|---|---|---|---|---|
| healthy | +0.0624 | [+0.0482, +0.0776] | 60 | **yes** |
| actuator | +0.0674 | [+0.0543, +0.0817] | 60 | **yes** |
| perception | +0.0587 | [+0.0361, +0.0844] | 60 | **yes** |
| combined | +0.0846 | [+0.0606, +0.1104] | 60 | **yes** |

### 2.4 Out-of-distribution stress (the axis the loss targets)

In-distribution the behavioural term costs a little tracking accuracy. The claim it
is meant to support is transfer, so the same frozen checkpoints are re-run on two
shifts never seen in training: plant parameters at double the training mismatch,
and an unseen reference family. Nothing is re-tuned and these cells are never
pooled with the calibrated population.

| Stress | Condition | Method | RMSE (m) | peak (m) | recovery |
|---|---|---|---|---|---|
| mismatch | actuator | `zero_context` | 1.029 ± 0.108 | 2.00 | 40/40 |
| mismatch | actuator | `constant_context` | 0.857 ± 0.087 | 2.00 | 40/40 |
| mismatch | actuator | `no_impact` | 0.772 ± 0.047 | 2.00 | 120/120 |
| mismatch | actuator | `full` | 0.834 ± 0.096 | 2.00 | 120/120 |
| mismatch | combined | `zero_context` | 1.390 ± 0.307 | 2.06 | 40/40 |
| mismatch | combined | `constant_context` | 1.082 ± 0.191 | 2.00 | 40/40 |
| mismatch | combined | `no_impact` | 0.991 ± 0.154 | 2.00 | 120/120 |
| mismatch | combined | `full` | 1.030 ± 0.181 | 2.00 | 120/120 |
| smooth_ref | actuator | `zero_context` | 0.224 ± 0.067 | 0.38 | 40/40 |
| smooth_ref | actuator | `constant_context` | 0.226 ± 0.057 | 0.38 | 40/40 |
| smooth_ref | actuator | `no_impact` | 0.223 ± 0.055 | 0.38 | 120/120 |
| smooth_ref | actuator | `full` | 0.222 ± 0.054 | 0.38 | 120/120 |
| smooth_ref | combined | `zero_context` | 0.817 ± 0.321 | 1.68 | 40/40 |
| smooth_ref | combined | `constant_context` | 0.680 ± 0.315 | 1.24 | 40/40 |
| smooth_ref | combined | `no_impact` | 0.628 ± 0.214 | 1.22 | 120/120 |
| smooth_ref | combined | `full` | 0.620 ± 0.250 | 1.22 | 120/120 |

Paired `full - no_impact` in the stress cells (negative = behavioural supervision helps):

| Stress | Condition | dRMSE (m) | 95% CI | significant |
|---|---|---|---|---|
| mismatch | actuator | +0.0615 | [+0.0474, +0.0774] | **yes** |
| mismatch | combined | +0.0389 | [+0.0124, +0.0655] | **yes** |
| smooth_ref | actuator | -0.0007 | [-0.0023, +0.0009] | no |
| smooth_ref | combined | -0.0080 | [-0.0299, +0.0174] | no |

Of 4 stress cells: **0** favour `full`, **2** favour `no_impact`, and **2** are not separated from zero (smooth_ref|actuator, smooth_ref|combined).

**Honest reading of Claim 1 - the behavioural-supervision gain is NOT demonstrated.**

The evidence points one way on every axis measured:

- In-distribution it *costs* tracking accuracy, +0.06 to +0.08 m, all four conditions significant (Sec 2.3).
- It does not improve one-step prediction: `no_impact` has the lower held-out error (Sec 2.1, 2.2).
- It does not improve latent retrieval: `no_impact` reaches a *better* signature-distance ratio than `full` (Sec 2.2). Both beat a constant latent, so the encoder does carry behavioural structure - the `L_impact` term simply is not what puts it there.
- Under parameter shift beyond the training range it *costs* accuracy again, significantly.
- On an unseen reference family it is statistically indistinguishable from no supervision.

`L_impact` optimises by a factor of ~22 (Sec 2.1), so this is not a training failure:
the objective is met and the closed-loop benefit still does not appear. **The paper
should not claim a behavioural-supervision gain on this evidence.** The abstract already
lists it as remaining to be validated; the correct update is that a direct, matched,
3-seed attempt to validate it at hardware authority found no gain in tracking,
prediction, retrieval, or transfer, and a small consistent cost. What survives is the
weaker and still useful statement that inferring a *changing* context helps: `full` beats
`constant_context` in all four conditions (Sec 3.1), which is a claim about the context
input, not about `L_impact`.

---

## 3. Matched method comparison (Stage 6)

60 matched episodes per condition, 3 training seeds. Every variant sees
the same references, limits, estimator, timing and scenario draws; trajectories
diverge only through the control.

| Condition | Method | RMSE (m) | peak (m), median | recovery | t_rec (s) | rejected |
|---|---|---|---|---|---|---|
| healthy | `zero_context` | 1.060 ± 0.119 | 2.00 | n/a | n/a | n/a |
| healthy | `adaptive_mpc` | 1.216 ± 0.190 | 2.00 | n/a | n/a | n/a |
| healthy | `constant_context` | 0.847 ± 0.063 | 2.00 | n/a | n/a | 0.682 |
| healthy | `no_impact` | 0.775 ± 0.048 | 2.00 | n/a | n/a | 0.697 |
| healthy | `full` | 0.838 ± 0.108 | 2.00 | n/a | n/a | 0.694 |
| healthy | `full_no_check` | 2.260 ± 0.486 | 3.52 | n/a | n/a | n/a |
| actuator | `zero_context` | 1.052 ± 0.103 | 2.00 | 60/60 | 9.90 | n/a |
| actuator | `adaptive_mpc` | 1.274 ± 0.196 | 2.00 | 60/60 | 11.10 | n/a |
| actuator | `constant_context` | 0.868 ± 0.074 | 2.00 | 60/60 | 6.20 | 0.686 |
| actuator | `no_impact` | 0.784 ± 0.052 | 2.00 | 180/180 | 0.00 | 0.696 |
| actuator | `full` | 0.851 ± 0.110 | 2.00 | 180/180 | 3.60 | 0.696 |
| actuator | `full_no_check` | 2.275 ± 0.482 | 3.62 | 35/60 | 17.10 | n/a |
| perception | `zero_context` | 1.461 ± 0.434 | 2.07 | 58/60 | 8.20 | n/a |
| perception | `adaptive_mpc` | 1.743 ± 0.470 | 2.61 | 50/60 | 9.40 | n/a |
| perception | `constant_context` | 1.095 ± 0.198 | 2.00 | 60/60 | 5.10 | 0.713 |
| perception | `no_impact` | 1.009 ± 0.162 | 2.00 | 179/180 | 0.00 | 0.691 |
| perception | `full` | 1.067 ± 0.209 | 2.00 | 180/180 | 2.60 | 0.703 |
| perception | `full_no_check` | 2.668 ± 0.551 | 4.38 | 29/60 | 17.20 | n/a |
| combined | `zero_context` | 1.349 ± 0.216 | 2.00 | 60/60 | 9.60 | n/a |
| combined | `adaptive_mpc` | 1.677 ± 0.410 | 2.53 | 53/60 | 9.70 | n/a |
| combined | `constant_context` | 1.079 ± 0.163 | 2.00 | 60/60 | 6.00 | 0.725 |
| combined | `no_impact` | 0.969 ± 0.131 | 2.00 | 180/180 | 0.00 | 0.684 |
| combined | `full` | 1.054 ± 0.183 | 2.00 | 178/180 | 3.85 | 0.707 |
| combined | `full_no_check` | 2.626 ± 0.606 | 4.61 | 37/60 | 17.00 | n/a |

Achieved-acceleration p95 across all healthy runs: 0.0542 ± 0.0054 m/s^2, still inside the measured band: **yes**. The comparison did not silently change the actuator authority.

### 3.1 All paired effects

| Comparison | Condition | dRMSE (m) | 95% CI | significant |
|---|---|---|---|---|
| `full-no_impact` | healthy | +0.0624 | [+0.0482, +0.0776] | **yes** |
| `full-no_impact` | actuator | +0.0674 | [+0.0543, +0.0817] | **yes** |
| `full-no_impact` | perception | +0.0587 | [+0.0361, +0.0844] | **yes** |
| `full-no_impact` | combined | +0.0846 | [+0.0606, +0.1104] | **yes** |
| `full-constant_context` | healthy | -0.0097 | [-0.0217, +0.0038] | no |
| `full-constant_context` | actuator | -0.0162 | [-0.0281, -0.0043] | **yes** |
| `full-constant_context` | perception | -0.0283 | [-0.0688, +0.0113] | no |
| `full-constant_context` | combined | -0.0249 | [-0.0554, +0.0053] | no |
| `full-adaptive_mpc` | healthy | -0.3786 | [-0.4217, -0.3384] | **yes** |
| `full-adaptive_mpc` | actuator | -0.4229 | [-0.4707, -0.3774] | **yes** |
| `full-adaptive_mpc` | perception | -0.6756 | [-0.7977, -0.5685] | **yes** |
| `full-adaptive_mpc` | combined | -0.6229 | [-0.7149, -0.5315] | **yes** |
| `full-zero_context` | healthy | -0.2219 | [-0.2468, -0.1978] | **yes** |
| `full-zero_context` | actuator | -0.2006 | [-0.2208, -0.1811] | **yes** |
| `full-zero_context` | perception | -0.3935 | [-0.5015, -0.3017] | **yes** |
| `full-zero_context` | combined | -0.2951 | [-0.3336, -0.2563] | **yes** |
| `full-full_no_check` | healthy | -1.4223 | [-1.5409, -1.2979] | **yes** |
| `full-full_no_check` | actuator | -1.4237 | [-1.5410, -1.3058] | **yes** |
| `full-full_no_check` | perception | -1.6006 | [-1.7357, -1.4746] | **yes** |
| `full-full_no_check` | combined | -1.5719 | [-1.7196, -1.4386] | **yes** |

### 3.2 Seed-level RMSE

Required with only three seeds: pooled intervals alone would hide seed spread.

| Method | Condition | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| `constant_context` | healthy | 0.8473 | n/a | n/a |
| `constant_context` | actuator | 0.8677 | n/a | n/a |
| `constant_context` | perception | 1.0955 | n/a | n/a |
| `constant_context` | combined | 1.0790 | n/a | n/a |
| `no_impact` | healthy | 0.7684 | 0.7716 | 0.7856 |
| `no_impact` | actuator | 0.7747 | 0.7826 | 0.7951 |
| `no_impact` | perception | 0.9909 | 1.0198 | 1.0150 |
| `no_impact` | combined | 0.9580 | 0.9684 | 0.9819 |
| `full` | healthy | 0.8654 | 0.7879 | 0.8595 |
| `full` | actuator | 0.8774 | 0.8012 | 0.8758 |
| `full` | perception | 1.1027 | 1.0075 | 1.0915 |
| `full` | combined | 1.0824 | 0.9927 | 1.0871 |
| `full_no_check` | healthy | 2.2599 | n/a | n/a |
| `full_no_check` | actuator | 2.2752 | n/a | n/a |
| `full_no_check` | perception | 2.6678 | n/a | n/a |
| `full_no_check` | combined | 2.6260 | n/a | n/a |

### 3.3 How eta was chosen

The one-step decrease condition is violated by the MPC candidate in **80.4%** of monitored steps at hardware authority.
Conformal calibration at delta=0.025 would give eta = 3.8295, which accepts
~97.5% and is therefore near-inert. Conformal calibration targets coverage of a
*certificate* claim, and Stage 7 finds no certificate to cover, so eta is instead
selected as the value minimising calibration-split RMSE over a declared grid.
Test episodes are disjoint from calibration.

| eta | calibration RMSE (m) | peak (m) | rejected fraction |
|---|---|---|---|
| 0.0000 | 0.9256 | 2.011 | 0.714 **<- selected** |
| 0.5000 | 1.2280 | 2.087 | 0.314 |
| 1.0000 | 1.6536 | 2.482 | 0.181 |
| 2.0000 | 2.1141 | 3.381 | 0.073 |
| 3.8295 | 2.3629 | 4.081 | 0.019 |

The relationship is monotone: as the check is enforced harder the rejected fraction rises from 1.9% to 71.4% and RMSE falls from 2.363 m to 0.926 m, a **61% reduction**. This is independent evidence that the post-allocation check of Eq. (18) is load-bearing, and it is consistent with the `full` vs `full_no_check` contrast above, which uses the same checkpoint on the test split.

**This must not be reported as a rarely-active safety net.** At the selected eta the
check rejects 71% of candidate wrenches, so for most samples the transmitted
command is the fallback, and the closed loop is nearer to the certified gain than to
the MPC. The honest framing is that the supervision layer is a *frequent override* whose
authority happens to help tracking at hardware thrust, and that the MPC candidate
clears the one-step decrease test only a minority of the time (19.6%). Both facts are consequences of the same
underactuation that empties the certificate in Sec 4.

---

## 4. Claim 2 - the numerical recovery certificate

> *Abstract: "... and numerical recovery certificate remain to be validated."*

**Result: the certified region is empty at every point of the swept grid (0 of 1050 cells per reference family).**
This is the outcome build_scSim.md Sec 12 predicted. The value of the stage is that
it locates the boundary and names the binding term, rather than asserting a bound.

### 4.1 The contraction condition vs plant-parameter tolerance

Sec 14 lists "measured mass and inertia with tolerance" as an OPEN item explicitly
blocking certificate numbers, so it is swept rather than assumed. gamma+nu < 1 is
required before any radius matters.

| Tolerance | step: best gamma+nu | contracts | smooth: best gamma+nu | contracts |
|---|---|---|---|---|
| ±0% | 0.9616 | **yes** | 0.9127 | **yes** |
| ±1% | 0.9685 | **yes** | 0.9238 | **yes** |
| ±2% | 0.9743 | **yes** | 0.9349 | **yes** |
| ±5% | 0.9918 | **yes** | 0.9683 | **yes** |
| ±10% | 1.0073 | no | 1.0070 | no |

**The contraction condition requires mass and inertia known to within ±5%.** At ±10% no design in the grid contracts.

### 4.2 Where the boundary sits, and which term binds

`s_cert/R` is the distance to a nonempty region: it must reach 1. Reported at every
tolerance so the best cell is not quoted under an unrealistic assumption of perfectly
known mass.

| Family | Tolerance | best cell | lambda | s_cert/R | binding term |
|---|---|---|---|---|---|
| step | ±0% | duty=0.70 | 0.9800 | **97.3** | b_r |
| step | ±1% | duty=0.70 | 0.9830 | **115** | b_r |
| step | ±2% | duty=0.70 | 0.9861 | **140** | b_r |
| step | ±5% | duty=0.70 | 0.9952 | **403** | b_r |
| step | ±10% | - | - | - | no contracting design |
| smooth | ±0% | duty=1.0,fmax=4.0,offset=0 | 0.9127 | **1.99** | eta |
| smooth | ±1% | duty=1.0,fmax=4.0,offset=0 | 0.9238 | **2.28** | eta |
| smooth | ±2% | duty=1.0,fmax=4.0,offset=0 | 0.9349 | **2.67** | eta |
| smooth | ±5% | duty=1.0,fmax=4.0,offset=0 | 0.9683 | **5.48** | eta |
| smooth | ±10% | - | - | - | no contracting design |

At the realistic end (±5% tolerance, the tightest that still contracts):

- **step**: short by a factor of **403**, binding on `b_r` (b_r = 1.9451, eta_q = 0.0471, R_U = 1.080).
- **smooth**: short by a factor of **5.48**, binding on `eta` (b_r = 0.0450, eta_q = 0.5054, R_U = 3.632).

Two clean findings:

- **The step-setpoint reference is structurally uncertifiable.** Its 1.0 m setpoint jump in one 0.1 s sample is a reference defect no bounded thrust can follow, giving b_r up to 33.2 against R_U ~ 1. Sec 12 predicted exactly this.
- **The smooth feasible reference comes close.** At the maximum-authority corner (duty 1.0, fmax 4.0 N, no dead band) it is short by a factor of 2 with perfectly known mass and 5.5 at ±5%. Crucially the binding term there is the **allocator** allowance eta_q, not the reference defect: once the reference is feasible and the authority is raised, what stands between this system and a certificate is the quantised pulse-width allocator. That is the boundary the sweep was asked to locate, and it points at a different subsystem than expected.

### 4.3 The trained residual is not admissible, by four orders of magnitude

The residual enters Lemma 3 through a *sound enclosure* of its Jacobian. Two were
computed, and the tighter used: a domain-restricted interval propagation bound
(5.330) and the global product-of-spectral-norms bound
(3.767). Neither is a sampled Jacobian, so both are
admissible under Appendix II.

- The trained residual's sensitivity of the state increment to the commanded wrench is up to **603x the nominal value** (nominal Ts/m = 0.0040). That is physically nonsensical and is an artefact of unconstrained training.
- The largest admissible scale is **alpha <= 0.000248**, so the residual is inadmissible by roughly four orders of magnitude.

**This converts "the certificate is empty" into an actionable design requirement:**
the learned residual must be trained under an explicit Lipschitz budget (for example
spectral normalisation with a fixed coefficient) before it can appear inside a
certificate at all. That is a concrete, checkable specification, and it is the most
useful thing this stage produces.

### 4.4 The horizon axis

The certificate is a one-step contraction under K, so N does not appear in it
algebraically. Sec 12 lists N because it determines achievable per-solve
correction, which is an operational statement, so N is swept in closed loop.

| Condition | N | RMSE (m) | rejected fraction | wall ms/step |
|---|---|---|---|---|
| healthy | 12 | 0.857 | 0.700 | 7.49 |
| healthy | 20 | 0.782 | 0.704 | 7.60 |
| healthy | 30 | 0.769 | 0.708 | 7.96 |
| healthy | 40 | 0.769 | 0.715 | 9.33 |
| healthy | 50 | 0.739 | 0.720 | 10.66 |
| combined | 12 | 1.013 | 0.714 | 6.96 |
| combined | 20 | 0.944 | 0.701 | 6.91 |
| combined | 30 | 0.943 | 0.688 | 8.02 |
| combined | 40 | 0.943 | 0.699 | 9.55 |
| combined | 50 | 0.932 | 0.686 | 10.95 |

---

## 5. How this simulation supports the paper

### 5.1 It independently replicates the hardware effect, with power the hardware cannot have

The strongest use of this study is as an independent replication of the one result the
hardware does establish: conditioning the controller on a learned context beats zero-context
MPC. Hardware has 3 comparisons at n = 3-5 runs with no paired intervals. Simulation has
4 conditions at 60 matched episodes x 3 seeds with block bootstrap intervals, on a plant whose
authority, estimator envelopes and duty law were anchored to the measured hardware first.

| Comparison | Hardware zero -> learned | Simulation zero_context -> full |
|---|---|---|
| actuation fault | 1.105 -> 0.950 m, **-14.0%** (n=5) | 1.052 -> 0.851 m, **-19.1%** (n=60) |
| perception degradation | 1.895 -> 0.798 m, **-57.9%** (n=5) | 1.461 -> 1.067 m, **-26.9%** (n=60) |
| healthy | no matched hardware pair | 1.060 -> 0.838 m, **-20.9%** (n=60) |
| combined | no matched hardware pair | 1.349 -> 1.054 m, **-21.9%** (n=60) |

Hardware's largest actuation gain (1.315 -> 0.781 m, -40.6%, n=3) came from the act30 severity
level, which has **no matched simulated counterpart**: the simulated actuator condition
corresponds to the 70% level, and the smooth-eta severity sweep is a deliberately distinct
intervention that the protocol requires to be labelled separately. It is left out of the
table rather than paired with something it does not correspond to.

Read this honestly in both directions:

- **The direction and the significance replicate everywhere.** All four simulated conditions favour learned context over zero-context, with intervals excluding zero, on matched draws. That is a much harder claim to attack than three small-n hardware comparisons.
- **The magnitudes do not all replicate.** The simulated perception improvement is roughly half the hardware's 57.9%. The hardware occluded cells have the largest spread in Table I, so the honest inference is that the biggest hardware percentage sits at the optimistic end of what this mechanism delivers. Saying so pre-empts the obvious reviewer objection and costs nothing, because the *claim* survives.

This is also the answer to "why simulate at all when you have hardware?": the simulation
supplies the matched ablations that are impossible on the hardware - identical scenario
draws across six controllers, a trained-vs-untrained supervision ablation at fixed weights
and seeds, and a with/without acceptance-check contrast on the same checkpoint.

### 5.2 Mapping onto the two stated contributions

The introduction claims exactly two contributions, and this study reaches both. The results
are not symmetric, and the two should not be handled the same way.

**Contribution 1, behavioural supervision.** The mechanism claim does not survive. `L_impact`
optimises by ~22x and still buys nothing in tracking, one-step prediction, latent retrieval,
or either out-of-distribution family, while costing 0.06-0.08 m in-distribution across all
four conditions. This cannot be repaired by rewording. What *does* survive is the surrounding
architecture claim: conditioning on a **changing** learned context helps, both against
zero-context (Sec 3) and against a trained-but-constant latent (Sec 3.1), and the encoder does
carry behavioural structure - both learned variants retrieve behaviourally similar
neighbours far better than a constant latent (Sec 2.2). The recommendation is to restate
Contribution 1 around the context *input* and report the supervision ablation as a negative
result. Reporting your own null is a much stronger position than having a reviewer request
the ablation you did not run.

**Contribution 2, the constructive recovery condition.** This one is far less damaged than
an empty certified region sounds, for a specific reason: Theorem 1 is *conditional* - it holds
"under explicit realizability and envelope conditions". This study does not contradict the
theorem. It shows the hypotheses are not satisfiable at this platform's authority, and then
locates exactly what must change:

- A dynamically feasible reference instead of a step setpoint. The 1 m jump in one 0.1 s sample is a reference defect no bounded thrust can follow, and it alone accounts for the step family being uncertifiable.
- Mass and inertia known to +/-5%; at +/-10% nothing in the grid contracts. Sec 14 already lists this as an OPEN item, so the sweep quantifies a gap the manuscript had already flagged.
- A Lipschitz-bounded residual. The trained one exceeds the admissible scale by ~4 orders of magnitude, which is a checkable training specification, not a vague caveat.
- At full authority on a feasible reference the condition is short by only a factor of ~2, and the binding term is the **allocator allowance**, not the theory. That is a concrete engineering target.

And the mechanism that Contribution 2 introduces is empirically the **largest effect in the
entire study**: the post-allocation acceptance check is worth 1.42-1.60 m of RMSE, all 4
conditions significant, and enforcing it harder monotonically improves tracking across the
whole eta grid (Sec 3.3). So the check works operationally even where the guarantee does not
apply. Present Contribution 2 as a conditional theorem plus a numerical study that locates its
boundary, and lead its empirical support with the check.

### 5.3 What to change in the manuscript

In rough order of how much a reviewer would punish leaving it:

1. **Do not leave Contribution 1 worded as a supervision gain** while an appendix reports the negative ablation. An internal contradiction is worse than a null result. Restate it around the context input.
2. **Fix the framing of the acceptance check.** At the selected eta it rejects 69%-71% of candidate wrenches on the test split and the MPC candidate clears the one-step decrease test only 19.6% of the time. It is a *frequent override*, not a rarely-active safety net, and describing it as light-touch is contradicted by our own logs.
3. **Promote the acceptance-check result.** It is the largest and most robust number here and is currently under-sold relative to the context story.
4. **State the certificate result as a located boundary**, with the four requirements above, rather than as a guarantee or as a silent omission.
5. **Add the replication table of Sec 5.1** next to hardware Table I, including the honest note that the simulated perception gain is about half the hardware figure.
6. **Keep the abstract's admission** that both items remain to be validated, but say in the same breath what *is* validated: context conditioning and the allocated-command check, on hardware and in a 2400-episode matched simulation.

### 5.4 Claims this study does NOT let you make

- No safety, recursive-feasibility, or certified-recovery claim. The region is empty; the Stage 6 supervision design is operational, and its activity rates are not evidence of a guarantee.
- No claim that behavioural supervision helps, in-distribution or out.
- No real-time latency claim. Timings are accelerated-simulation wall time.
- No claim that simulated magnitudes transfer to hardware. The simulation is anchored to hardware envelopes, which licenses comparisons *within* the simulated population and replication of *directions*, not the export of percentages back onto the physical vehicle.

---

## 6. What this does not show

- The certified region is **empty** at hardware authority. No safety or recursive-feasibility guarantee is demonstrated. The supervision design used in Stage 6 is an *operational* one; its activity and acceptance rates are not evidence of a guarantee.
- Gate inactivity is not displayed as evidence of physical safety, per protocol Sec 9.2.
- The VO surrogate's noise parameters are the only *fitted* quantities in the build. They were fitted so the closed-loop estimation error reproduces the measured envelopes, which is the procedure the source document specifies. They are not measured ROVIO noise parameters; the logged covariance channel is all zeros.
- Solver timings are accelerated-simulation wall time and are **not** a real-time controller latency measurement.
- Conformal calibration of eta was not used, because there is no valid certificate claim to cover. eta was selected by a declared calibration-split rule instead, and that is a weaker statement.
- The corridor half-width and the prediction-error budget d_cert are declared simulation choices; no spatial safety envelope exists anywhere in the flight code.
- Simulation calibration supports the simulated population only.


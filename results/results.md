# Simulation results

Companion evidence for *Multimodal Context Learning for Actuation and Perception
Fault-Tolerant Model Predictive Control*, targeting the two items the abstract
lists as unvalidated: the behavioural-supervision gain and the numerical recovery
certificate.

**Run id `v2-corrected`.** This is the *corrected* campaign. It supersedes the earlier
development campaign, preserved unmodified in `results_v1_archive/`, whose numbers are **not**
comparable with these and should not be quoted. See section 0.

| Provenance | Value |
|---|---|
| Run id | `v2-corrected` |
| Code commit | `4f967a40f6477724258b53acf9cf6464edacddcf` |
| Config manifest hash (at report time) | `57bea4173319b8f6` |
| Python | 3.10.12 |

Per-stage configuration hashes are **not identical**, and that is expected rather than a
fault: Stage 3 refits the perception surrogate and writes those fitted values back into the
manifest, so every stage run before the refit carries the earlier hash. The stages whose
results are quoted in this report (6, 7, 8) all ran after it.

| Stage | Config hash recorded |
|---|---|
| 1 open-loop | `155bb5109e93c543` |
| 2 anchoring | `155bb5109e93c543` |
| 3 estimator | `155bb5109e93c543` |
| 6 comparison | `57bea4173319b8f6` |
| 7 certificate | `57bea4173319b8f6` |
| 8 horizon / OOD | `57bea4173319b8f6` |

**Reproducibility, verified rather than asserted.** Stages 7 and 8 were re-executed from the
same commit in a separate process. Stage 7 reproduced bit-identically. Stage 8 reproduced
bit-identically in every physical, tracking, selection and out-of-distribution quantity;
the only fields that moved were per-step solver wall-clock times (`ms_per_step`,
`solve_ms_p95`), which track machine load and are not properties of the system under
study. Timing figures should therefore be read as indicative, while every reported
behavioural number is exactly reproducible.

Figures: `results/figures/`.

---

## 0. Corrections that invalidated the previous campaign

Four defects were found in the earlier implementation by external review and confirmed
directly in that code. Each one broke an assumption the paper's argument rests on, so the
earlier results are void rather than merely imprecise, and no amount of extra episodes
would have revealed any of them.

| # | Defect | Why it invalidated the result |
|---|---|---|
| 1 | The controller-visible wrench was computed from **post-fault** pulse durations, and that quantity fed the context encoder, the predictor's training input and the acceptance check | The learned context was **observing the actuation fault directly** through the command channel. The paper's central premise is that no fault label, severity or onset is ever an input; in substance it was. Identical proposals with identical commanded pulses produced different controller-visible wrenches purely because the hidden skip phase differed |
| 2 | The plant rotated body thruster force into the world frame using the **estimated** yaw | Physical acceleration depended on the estimator's error. Thrusters are bolted to the vehicle, so where the force points cannot depend on what the filter believes. This inflated the perception conditions with a nonphysical coupling |
| 3 | A fallback that **failed its own acceptance check** was transmitted anyway (the verdict was computed, stored, and never read) | The 'verified fallback' of Algorithm 1 was not verified. The eligibility flag was also radius-only, so the full pre-action conditions were never enforced |
| 4 | The interval Jacobian enclosure left yaw-dependent off-diagonal entries of `E_B` at exactly zero | The enclosure was **unsound**: sampling broke it by 2e-5 on `E_B` and 4e-3 on `E_A`. Bounds a counterexample can break certify nothing, so every certificate number computed from them was meaningless |

Also corrected: the behavioural-supervision experiment shared one RNG stream between
minibatch ordering, multistep sampling and behavioural pair sampling, so enabling the extra
loss silently changed every subsequent minibatch - `full` and `no_impact` were never the
matched pair they were reported to be. Probe branches were reset to each parent's own state
and then paired as though matched, so signature distances mixed the impairment with the
initial condition. The probe signature regressed physical response against the *fault-reduced*
wrench, which divides out the very impairment the signature exists to describe.

**Semantic gate (Stage 0).** 17/18 checks pass. These run as a hard gate
ahead of every other stage, asserting that hidden fault information cannot reach the
controller, that physical thrust follows true attitude, that the selection logic transmits
what it claims to, and that the enclosures survive sampling.

**1 check(s) currently FAIL: 2.4f data-generation and policy paths fire identical physical pulses.** The gate is red, so Stage 0 exits nonzero and `run_all.py` will not proceed past it. The numbers in this report were produced *before* that check existed and are retained deliberately, with the affected scope stated in Sec 0.1, rather than deleted or quietly regenerated.

Selected checks:

| Check | Result |
|---|---|
| 2.4a hidden severity/phase does not change controller-visible trial | PASS. max |difference| over 5 hidden settings = 0.000e+00 (wrench, commanded wrench, allocated force, commanded pulses) |
| 2.4b physical successor still changes with the hidden fault | PASS. identical commanded pulses (max diff 0.0e+00) but physical state differs by 3.8400e-03; skip flags False/True |
| 2.4c repeated trials mutate neither allocator memory nor fault phase | PASS. 5 trials: max drift 0.0e+00, memory unchanged True, fault counter 0->0 |
| 2.4d one commit = one memory update and one fault slot | PASS. fault cycle 0->1; committed packet is the selected one: True |
| 2.4f data-generation and policy paths fire identical physical pulses | FAIL. 12 of 12 (firing fraction, phase) configurations produce different fire/skip sequences between the two execution paths; e.g. (0.3, 0). The policy path advances the fault counter in commit() before apply_hidden() previews it, so it runs one cycle ahead of the shorthand used to generate training data. |
| 2.4e u_k reconstructs from commanded pulses and nominal parameters | PASS. max |reconstruction - logged| = 0.00e+00 |
| 3.4a body force rotates with TRUE yaw | PASS. yaw 0 -> dv=(+0.00192,+0.00000), yaw 90deg -> dv=(+0.00000,+0.00192) |
| 3.4b physical integration takes no estimator yaw argument | PASS. plant_step parameters: ['x', 'dt_on', 'substeps', 'valve', 'eta_smooth', 'mass', 'jzz', 'drag', 'yaw_damp'] |
| 3.4c integration converges under refinement | PASS. max |x(n) - x(4000)|: n=20: 1.20e-07, n=40: 3.00e-08, n=80: 7.62e-09, n=160: 3.68e-09, n=320: 1.77e-09 (declared tol 5e-04 at the production n=20; 20->80 improves 15.7x) |
| 3.4d physical impulse scales with ACTUAL valve thrust | PASS. dv(1.2 N) = 0.002400, dv(2.4 N) = 0.004800, ratio 2.000000 (expected 2) |
| 3.4e planar rotation equivariance of the physical plant | PASS. max deviation 7.11e-15 over position, velocity, yaw, rate |
| 3.4f allocator-only vs physical authority are distinguishable | PASS. same commanded pulses: dv = 0.00192 at nominal valve thrust vs 0.00640 at 4.0 N. A sweep changing only the allocator's fmax leaves the first number unchanged and must be labelled as such. |
| 4.6a an unsatisfiable acceptance bar never transmits a candidate | PASS. action sources observed: ['supervisor']; rejects=0, first-action failures=0, supervisor=120 |
| 4.6b a failing fallback yields ineligibility and the fixed supervisor | PASS. supervisor share 100%, eligible steps 0 of 120 (eligibility requires a PASSING fallback) |
| 4.6c every step is accounted for by exactly one declared outcome | PASS. of 120 steps: 31 candidate, 78 diverted by the eta-free first-action condition, 10 by command admissibility / acceptance, 1 supervisor. A permissive eta cannot rescue the first-action condition by construction, which is why that share stays high. |
| 4.6d candidate and fallback slacks are recorded separately | PASS. slack_cmd (candidate) and slack_fb (fallback) are distinct log channels, so a candidate's slack cannot be read as the transmitted action's slack |
| 4.6e one transmitted command advances the fault schedule once | PASS. 0 skips over 120 control steps with 2-3 trial allocations each; only the committed packet advances the schedule |
| 6.1 interval enclosure not falsified by sampling | PASS. 6600 sampled points: worst (|dA| - E_A) = +0.000e+00, worst (|dB| - E_B) = +0.000e+00; both must be <= 0. Passing does NOT certify the continuum, only that no counterexample was found (step, span 0.05). |

Passing 6.1 does **not** certify the continuum; it only records that no counterexample was
found. A rigorous claim needs verified interval or exact arithmetic, which this does not
implement.

### 0.1 A further defect, confirmed after this campaign ran

The hidden pulse-skip is applied at a **different counter state** in the two execution paths.
`CommandChain.__call__`, the shorthand used for data generation, previews the fault and then
advances the counter. The closed-loop policy path does the opposite: `policy.act` calls
`chain.commit` (which advances the counter) and the runner calls `chain.apply_hidden`
afterwards, so evaluation runs the fault schedule one cycle ahead of training.

This was verified directly rather than inferred: across firing fractions {0.3, 0.5, 0.7, 0.9}
and initial phases {0, 1, 2}, **all 12 configurations produce different fire/skip sequences**
between the two paths, and the policy sequence equals the shorthand sequence at phase + 1.

Scope of the consequence, stated precisely. This is a **phase offset, not a change in fault
intensity**: the long-run skip rate, and therefore the mean lost impulse, is identical. So it
does not invalidate the healthy cells at all, and is unlikely to move the aggregate faulted
means much. What it does break is packet-level correspondence between the training
distribution and the evaluation distribution, which is exactly the correspondence a learned
residual is supposed to rely on. Faulted closed-loop numbers in this report should therefore
be treated as **provisional pending a single unified execution contract**.

Two approximations are declared rather than fixed, and their consequences are carried
through the results:

- **The first-action norm condition is not enforced inside the optimisation.** The solver is a QP and does not acquire a conic constraint by having its weights changed. The condition is instead *verified independently* on the returned proposal, and a proposal that fails it is not treated as a feasible candidate. This is permitted by the review's Sec 4.2 provided it is identified, which it is here and in the logs.
- **The floating-point allowance is a first-order rounding estimate**, scaled by the conditioning of the Cholesky factor and the operation count, not verified arithmetic. The previous blanket factor of 1+1e-9 was not a justified bound on a chain containing a factorisation, an explicit inverse, products and norms.

---

## 0. Verdicts at a glance

| Paper claim | Verdict | Evidence |
|---|---|---|
| Simulation reproduces the hardware envelopes | **supported** | 10/10 anchoring gates pass; accel p95 0.0543 m/s^2 inside the measured 0.025-0.063 band; Sec 1 |
| **PRIMARY:** behavioural supervision helps (M3 vs M2) | **not supported; adverse** | costs +0.045 to +0.115 m post-onset RMSE, 4/4 conditions significantly WORSE at the episode level. The seed-crossed intervals include zero in 4/4, so at the population level the effect is unresolved - but every point estimate is adverse. The pre-declared lambda_I grid also selected **zero**; Sec 2 |
| Inferring a *changing* context helps (M2 vs M1) | **supported** | -0.405 to -0.065 m, 4/4 conditions significant. This is the clean isolation: both sides carry no behavioural loss; Sec 3 |
| The learned residual helps (M3 vs M0) | **partially supported** | -0.321 to -0.005 m, 2/4 conditions significant, with the same recovery structure on both sides; Sec 3 |
| MPC planning adds value beyond the fallback (M3 vs M5) | **not supported** | -0.033 to +0.066 m; removing the optimiser entirely and keeping only the checked fallback changes little, and is significantly BETTER in 1/4 conditions. Much of the measured performance is the fallback and the eligibility logic, not MPC; Sec 3 |
| The **combined** command safeguards are load-bearing (M3 vs M4) | **supported, large; not an isolated component** | -3.206 to -1.460 m, 4/4 significant, compared per-checkpoint. But M4 switches off *three* mechanisms together - supervisor diversion when ineligible, the first-action condition, and the post-allocation test - so this does **not** isolate the allocated-command check. Without the bundle the controller diverges; Sec 3 |
| Beats the hardware-matched comparator (M3 vs HW) | **condition-dependent** | -0.503 to +0.613 m: better under perception and combined faults, **worse** under healthy and actuator-only. The earlier campaign's uniform win did not survive closing the fault-information leak; Sec 3 |
| Declared task specification is met | **not supported** | pos <= 0.15 m and yaw <= 5 deg held 2 s is reached in only 70/3840 rollouts overall; the best cell is `healthy|no_impact` at 11%. The **evaluated controllers rarely achieve it**; that is not evidence the specification is unattainable in principle, and the dwell is currently scored at the *current* waypoint rather than the final one; Sec 3 |
| Learned residual transfers to an unseen reference family | **not supported; fails badly** | on the held-out `transfer` family the learned methods reach 4.8-5.0 m RMSE against 0.37-1.35 m for the *zero-context* comparator - roughly an order of magnitude worse. The residual is trained on `step`/`smooth` and does not generalise off them; Sec 2.4 |
| Behavioural supervision helps on cross-reference transfer | **weak, and immaterial** | this is the one axis where M3 beats M2: significantly better in 2/2 held-out-family cells. But the gain is ~0.13-0.17 m on top of a ~5 m error, so it improves a regime in which the method has already failed; Sec 2.4 |
| The evaluated policy is mostly the *proposed* controller | **no** | the fixed supervisor issues 42%-65% of all transmitted actions under M3, because pre-action eligibility requires a fallback that passes its own check and it usually does not. What the table scores is largely a fixed velocity-damping law, not context-conditioned MPC; Sec 3 |
| Numerical recovery certificate | **not supported (empty)** | 0 of 2730 swept cells certify, now with a *sound* enclosure; boundary and binding terms located instead; Sec 4 |

**Net position.** Two mechanisms survive the corrected campaign: the learned residual and
the changing context both improve tracking against matched comparators, and the
post-allocation check is decisively load-bearing. Three claims do not survive: behavioural
supervision is adverse on the primary endpoint and was rejected by its own pre-declared
selection grid, MPC planning is not distinguishable from the checked fallback, and the
recovery certificate is empty under a sound enclosure. The method also no longer beats the
hardware-matched comparator uniformly - only under perception and combined faults.

The single most consequential change is closing the fault-information leak. Much of the
earlier campaign's positive result was the context encoder reading the fault out of the
command channel rather than inferring it from behaviour.

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
4. **Duty law and pulse realisation.** duty = 4.829*F/25 -0.07686 s (F in N, normalised by the 25 N closed-loop force scale), clipped to the 40 ms PWM period inside a 100 ms slot, so the duty ceiling is 0.40. Anything above 0.001 N is stretched to at least 12 ms; anything below is dropped. An open valve delivers 1.2 N.
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
healthy error is still 0.157 m of 0.316 m (50%), so the envelope is dominated by the
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
| Healthy \|dx\| p95 | 0.22-0.65 m (C1) | 0.316 m | yes |
| Healthy dpsi p95 | 0.10-0.27 rad (C1) | 0.128 rad | yes |
| Occluded \|dx\| p95 | 0.79-4.86 m (V2) | 1.276 m | yes |

Open-loop plant, allocator, duty law and fault injection: **29/29 checks pass** (Stage 1).

Two facts from these stages matter for everything after:

- **78% of commanded wrenches lie outside the achievable set.** The structural authority gap, not the declared box, is what the theory's `U` must be.
- **The estimator's LPF lag is the dominant error contributor.** With all VO noise zeroed the healthy error is still 0.157 m of 0.316 m (50%), so the estimation envelope is a lag property, not a noise property.

---

## 2. Claim 1 - behavioural supervision gain

> *Abstract: "The behavioral-supervision gain ... remain[s] to be validated."*

`full` and `no_impact` share architecture, initial weights (same seed), data,
optimiser budget, epochs, learning rate, checkpoint rule and prediction-loss
weights. The single intentional difference is `lambda_I`.

**Generated corpus:** 360 parent episodes, 216,000 transitions, 3832 probe branches (229,920 extra transitions).

**Of that, the training split is 160 parent episodes** (96,000 control steps, 94,240 windows). The remainder is held for dev, score fitting, calibration and test:

| Split | Parent episodes | Control steps | Purpose |
|---|---|---|---|
| `train` | 160 | 96,000 | gradient updates |
| `dev` | 40 | 24,000 | lambda_I selection, early stopping |
| `fitting` | 48 | 28,800 | score objects |
| `calibration` | 48 | 28,800 | eta / R selection |
| `test` | 64 | 38,400 | final reported comparisons |

### 2.1 The behavioural loss does optimise

| Model | lambda_I | L_impact first -> last epoch | dev one-step loss |
|---|---|---|---|
| `full_s0` | 1.0 | 0.1565 -> 0.0134 | 0.001481 |
| `no_impact_s0` | 0.0 | 0.0000 -> 0.0000 | 0.001118 |
| `full_s1` | 1.0 | 0.1585 -> 0.0146 | 0.001487 |
| `no_impact_s1` | 0.0 | 0.0000 -> 0.0000 | 0.001106 |
| `full_s2` | 1.0 | 0.1496 -> 0.0131 | 0.001490 |
| `no_impact_s2` | 0.0 | 0.0000 -> 0.0000 | 0.001120 |
| `const_s0` | 0.0 | 0.0000 -> 0.0000 | 0.001576 |
| `const_s1` | 0.0 | 0.0000 -> 0.0000 | 0.001577 |
| `const_s2` | 0.0 | 0.0000 -> 0.0000 | 0.001579 |

`L_impact` falls by a factor of ~22, so the behavioural geometry is genuinely being
shaped. Note the ordering of the one-step loss: `no_impact` fits transitions BEST.
The behavioural term is a constraint, and it costs one-step accuracy. The question
is therefore whether it buys closed-loop performance.

### 2.2 Retrieval: does the latent carry behavioural structure?

For each probe anchor, the nearest latent neighbour from a *different* episode is
retrieved and the behavioural signature distance actually incurred is reported.
`chance` is the same statistic under a random pairing. Ratio < 1 means the latent
retrieves behaviourally similar neighbours.

Retrieval candidates are restricted to *different parent episodes* within the *same
matched probe group*, so a neighbour is never retrieved by virtue of starting from the
same physical state. `constant_context` is reported as n/a rather than as a number: its latents
are identical by construction, so any ranking among them is arbitrary tie-breaking and
carries no behavioural information.

The prediction column is a **weighted MSE** in mixed state units (m, m/s, rad, rad/s),
not an RMSE; it is not square-rooted and the channel weights are those of the training
loss, so it is comparable across rows but is not a physical distance.

| Model | prediction (weighted MSE) | retrieval error | chance | ratio |
|---|---|---|---|---|
| `full_s0` | 0.001609 | 1.0249 | 1.1434 | **0.896** |
| `full_s1` | 0.001614 | 1.0146 | 1.1434 | **0.887** |
| `full_s2` | 0.001616 | 1.0483 | 1.1434 | **0.917** |
| `no_impact_s0` | 0.001210 | 1.0118 | 1.1434 | **0.885** |
| `no_impact_s1` | 0.001196 | 1.0128 | 1.1434 | **0.886** |
| `no_impact_s2` | 0.001213 | 1.0057 | 1.1434 | **0.880** |
| `const_s0` | 0.001703 | n/a | n/a | **n/a** |
| `const_s1` | 0.001703 | n/a | n/a | **n/a** |
| `const_s2` | 0.001705 | n/a | n/a | **n/a** |

### 2.3 Closed-loop paired effect (the headline test)

Paired `full - no_impact`, block bootstrap over parent episodes (episodes are the
resampling unit; time samples and overlapping windows are not treated as
replicates). Negative = full is better.

| Condition | dRMSE (m) | 95% CI | blocks | significant |
|---|---|---|---|---|
| healthy | +0.0517 | [+0.0117, +0.0922] | 60 | **yes** |
| actuator | +0.0815 | [+0.0344, +0.1279] | 60 | **yes** |
| perception | +0.0254 | [-0.0005, +0.0498] | 60 | no |
| combined | +0.0333 | [+0.0058, +0.0595] | 60 | **yes** |

### 2.4 Out-of-distribution stress (the axis the loss targets)

The claim the behavioural term is meant to support is transfer, so the same frozen
checkpoints are re-run on two shifts absent from training: plant parameters at **1.5x** the training
mismatch (+/-15% against +/-10%, not double, as an earlier version of this report stated), and
the held-out `transfer` reference family. `smooth` cannot serve as the unseen family any more,
because it is now part of the training mixture. Nothing is re-tuned and these cells are
never pooled with the calibrated population.

| Stress | Condition | Method | RMSE (m) | peak (m) | recovery |
|---|---|---|---|---|---|
| mismatch | actuator | `zero_context` | 1.036 ± 0.121 | 2.00 | 40/40 |
| mismatch | actuator | `constant_context` | 1.650 ± 0.301 | 2.06 | 17/40 |
| mismatch | actuator | `no_impact` | 1.335 ± 0.245 | 2.00 | 77/120 |
| mismatch | actuator | `full` | 1.442 ± 0.310 | 2.00 | 66/120 |
| mismatch | combined | `zero_context` | 1.483 ± 0.506 | 2.11 | 36/40 |
| mismatch | combined | `constant_context` | 1.299 ± 0.234 | 2.00 | 34/40 |
| mismatch | combined | `no_impact` | 1.218 ± 0.236 | 2.00 | 101/120 |
| mismatch | combined | `full` | 1.238 ± 0.184 | 2.00 | 102/120 |
| transfer_ref | actuator | `zero_context` | 0.374 ± 0.123 | 0.62 | 40/40 |
| transfer_ref | actuator | `constant_context` | 4.840 ± 0.797 | 7.24 | 0/40 |
| transfer_ref | actuator | `no_impact` | 5.037 ± 0.637 | 7.53 | 0/120 |
| transfer_ref | actuator | `full` | 4.911 ± 0.727 | 7.14 | 0/120 |
| transfer_ref | combined | `zero_context` | 1.347 ± 0.576 | 2.56 | 40/40 |
| transfer_ref | combined | `constant_context` | 4.682 ± 1.044 | 7.12 | 0/40 |
| transfer_ref | combined | `no_impact` | 4.921 ± 0.984 | 7.38 | 0/120 |
| transfer_ref | combined | `full` | 4.754 ± 1.005 | 7.12 | 0/120 |

Paired `full - no_impact` in the stress cells (negative = behavioural supervision helps):

| Stress | Condition | dRMSE (m) | 95% CI | significant |
|---|---|---|---|---|
| mismatch | actuator | +0.1067 | [+0.0582, +0.1551] | **yes** |
| mismatch | combined | +0.0201 | [-0.0367, +0.0724] | no |
| transfer_ref | actuator | -0.1261 | [-0.2500, -0.0081] | **yes** |
| transfer_ref | combined | -0.1673 | [-0.2803, -0.0582] | **yes** |

Of 4 stress cells: **2** favour `full`, **1** favour `no_impact`, and **1** are not separated from zero (mismatch|combined).

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
| healthy | `zero_context` | 1.082 ± 0.153 | 2.00 | n/a | n/a | n/a |
| healthy | `adaptive_mpc` | 1.236 ± 0.243 | 2.00 | n/a | n/a | n/a |
| healthy | `nominal_recovery` | 1.358 ± 0.291 | 2.00 | n/a | n/a | 0.031 |
| healthy | `constant_context` | 1.352 ± 0.239 | 2.00 | n/a | n/a | 0.041 |
| healthy | `no_impact` | 1.137 ± 0.159 | 2.00 | n/a | n/a | 0.031 |
| healthy | `full` | 1.189 ± 0.214 | 2.00 | n/a | n/a | 0.035 |
| healthy | `full_no_check` | 2.799 ± 0.695 | 5.81 | n/a | n/a | n/a |
| healthy | `fallback_only` | 1.222 ± 0.216 | 2.00 | n/a | n/a | 0.000 |
| actuator | `zero_context` | 1.069 ± 0.132 | 2.00 | 60/60 | 11.10 | n/a |
| actuator | `adaptive_mpc` | 1.255 ± 0.230 | 2.00 | 55/60 | 12.30 | n/a |
| actuator | `nominal_recovery` | 1.757 ± 0.366 | 2.16 | 21/60 | 0.00 | 0.022 |
| actuator | `constant_context` | 1.734 ± 0.397 | 2.18 | 22/60 | 0.00 | 0.030 |
| actuator | `no_impact` | 1.446 ± 0.296 | 2.00 | 118/180 | 1.85 | 0.024 |
| actuator | `full` | 1.528 ± 0.334 | 2.00 | 107/180 | 2.00 | 0.026 |
| actuator | `full_no_check` | 2.619 ± 0.744 | 5.02 | 42/180 | 17.40 | n/a |
| actuator | `fallback_only` | 1.523 ± 0.307 | 2.00 | 105/180 | 0.00 | 0.000 |
| perception | `zero_context` | 1.497 ± 0.417 | 2.19 | 52/60 | 10.70 | n/a |
| perception | `adaptive_mpc` | 1.843 ± 0.569 | 2.73 | 35/60 | 10.70 | n/a |
| perception | `nominal_recovery` | 1.209 ± 0.223 | 2.00 | 53/60 | 11.20 | 0.038 |
| perception | `constant_context` | 1.202 ± 0.214 | 2.00 | 55/60 | 11.10 | 0.051 |
| perception | `no_impact` | 1.166 ± 0.224 | 2.00 | 171/180 | 8.20 | 0.037 |
| perception | `full` | 1.191 ± 0.208 | 2.00 | 171/180 | 10.60 | 0.044 |
| perception | `full_no_check` | 3.645 ± 1.205 | 6.57 | 2/180 | 17.80 | n/a |
| perception | `fallback_only` | 1.150 ± 0.196 | 2.00 | 177/180 | 11.60 | 0.000 |
| combined | `zero_context` | 1.417 ± 0.283 | 2.07 | 55/60 | 10.70 | n/a |
| combined | `adaptive_mpc` | 1.694 ± 0.403 | 2.52 | 46/60 | 11.75 | n/a |
| combined | `nominal_recovery` | 1.237 ± 0.250 | 2.00 | 51/60 | 16.70 | 0.034 |
| combined | `constant_context` | 1.312 ± 0.329 | 2.00 | 48/60 | 14.10 | 0.045 |
| combined | `no_impact` | 1.200 ± 0.199 | 2.00 | 158/180 | 15.70 | 0.035 |
| combined | `full` | 1.233 ± 0.211 | 2.00 | 158/180 | 19.25 | 0.042 |
| combined | `full_no_check` | 3.539 ± 1.268 | 6.25 | 4/180 | 21.40 | n/a |
| combined | `fallback_only` | 1.220 ± 0.219 | 2.00 | 150/180 | 14.55 | 0.000 |

### 3.0 Complete action-source decomposition

Every transmitted command comes from exactly one source. The stored table logs three of
them; the eta-free first-action rejection was counted in `stats` but not aggregated, so the
logged shares do not sum to one. It is recovered below as the residual, which is valid here
only because the solver-failure share is identically zero in this run.

| Condition | candidate | supervisor | fallback (post-alloc) | fallback (solver) | fallback (first-action), *derived* | sum |
|---|---|---|---|---|---|---|
| healthy | 0.097 | 0.624 | 0.035 | 0.000 | **0.244** | 1.000 |
| actuator | 0.079 | 0.654 | 0.026 | 0.000 | **0.241** | 1.000 |
| perception | 0.121 | 0.423 | 0.044 | 0.000 | **0.412** | 1.000 |
| combined | 0.129 | 0.421 | 0.042 | 0.000 | **0.408** | 1.000 |

The derived first-action share is **large** - it is the second biggest source in every
condition and the largest single rejection mechanism. That matters for interpretation: the
reason MPC candidates are rarely transmitted is dominated by the eta-*free* first-action
condition, which no choice of eta can relax, rather than by the post-allocation test that
eta controls. Any attempt to raise the MPC action share by tuning eta is therefore aimed at
the smaller of the two mechanisms. This share should be logged directly rather than derived.

Achieved-acceleration p95 across all healthy runs: 0.0466 ± 0.0054 m/s^2, still inside the measured band: **yes**. The comparison did not silently change the actuator authority.

### 3.1 All paired effects on the primary endpoint

The primary endpoint is **post-onset position RMSE**, declared before the test run, with
M3 - M2 as the primary comparison. A negative dRMSE favours the first-named method.

Two interval levels are reported because they answer different questions. The **episode**
interval is conditional on the three trained checkpoints. The **crossed** interval resamples
training seeds *and* episodes, so it speaks for a broader training-and-deployment population; with
only three seeds its precision is genuinely poor, and more episodes cannot repair that.

| Comparison | Condition | d post-onset RMSE (m) | episode 95% CI | crossed 95% CI | draws | rollouts | notes |
|---|---|---|---|---|---|---|---|
| `full-no_impact` | healthy | +0.0517 | [+0.0117, +0.0922] | [-0.0028, +0.1071] | 60 | 180 | episode-significant |
| `full-no_impact` | actuator | +0.1153 | [+0.0472, +0.1800] | [-0.0100, +0.2264] | 60 | 180 | episode-significant |
| `full-no_impact` | perception | +0.0453 | [+0.0053, +0.0838] | [-0.0207, +0.1041] | 60 | 180 | episode-significant |
| `full-no_impact` | combined | +0.0513 | [+0.0087, +0.0917] | [-0.0130, +0.1107] | 60 | 180 | episode-significant |
| `no_impact-constant_context` | healthy | -0.2150 | [-0.2714, -0.1650] | n/a (single seed) | 60 | 180 | episode-significant, `constant_context` broadcast across seeds |
| `no_impact-constant_context` | actuator | -0.4048 | [-0.5076, -0.3076] | n/a (single seed) | 60 | 180 | episode-significant, `constant_context` broadcast across seeds |
| `no_impact-constant_context` | perception | -0.0649 | [-0.1225, -0.0057] | n/a (single seed) | 60 | 180 | episode-significant, `constant_context` broadcast across seeds |
| `no_impact-constant_context` | combined | -0.1644 | [-0.2759, -0.0678] | n/a (single seed) | 60 | 180 | episode-significant, `constant_context` broadcast across seeds |
| `full-nominal_recovery` | healthy | -0.1692 | [-0.2336, -0.1070] | n/a (single seed) | 60 | 180 | episode-significant, `nominal_recovery` broadcast across seeds |
| `full-nominal_recovery` | actuator | -0.3208 | [-0.4057, -0.2361] | n/a (single seed) | 60 | 180 | episode-significant, `nominal_recovery` broadcast across seeds |
| `full-nominal_recovery` | perception | -0.0316 | [-0.0885, +0.0233] | n/a (single seed) | 60 | 180 | `nominal_recovery` broadcast across seeds |
| `full-nominal_recovery` | combined | -0.0046 | [-0.0748, +0.0604] | n/a (single seed) | 60 | 180 | `nominal_recovery` broadcast across seeds |
| `full-fallback_only` | healthy | -0.0334 | [-0.0872, +0.0174] | [-0.0990, +0.0299] | 60 | 180 | - |
| `full-fallback_only` | actuator | +0.0015 | [-0.1016, +0.0960] | [-0.1156, +0.1090] | 60 | 180 | - |
| `full-fallback_only` | perception | +0.0662 | [+0.0057, +0.1238] | [+0.0025, +0.1288] | 60 | 180 | episode-significant |
| `full-fallback_only` | combined | +0.0217 | [-0.0498, +0.0908] | [-0.0590, +0.1000] | 60 | 180 | - |
| `full-full_no_check` | healthy | -1.6101 | [-1.7096, -1.5069] | [-2.0053, -1.3177] | 60 | 180 | episode-significant |
| `full-full_no_check` | actuator | -1.4602 | [-1.6158, -1.2967] | [-1.9137, -1.0884] | 60 | 180 | episode-significant |
| `full-full_no_check` | perception | -3.2058 | [-3.4353, -2.9750] | [-3.6990, -2.8078] | 60 | 180 | episode-significant |
| `full-full_no_check` | combined | -3.0207 | [-3.2496, -2.7837] | [-3.4546, -2.6405] | 60 | 180 | episode-significant |
| `full-adaptive_mpc` | healthy | -0.0469 | [-0.1007, +0.0045] | n/a (single seed) | 60 | 180 | `adaptive_mpc` broadcast across seeds |
| `full-adaptive_mpc` | actuator | +0.3409 | [+0.2489, +0.4351] | n/a (single seed) | 60 | 180 | episode-significant, `adaptive_mpc` broadcast across seeds |
| `full-adaptive_mpc` | perception | -0.9561 | [-1.1489, -0.7824] | n/a (single seed) | 60 | 180 | episode-significant, `adaptive_mpc` broadcast across seeds |
| `full-adaptive_mpc` | combined | -0.6906 | [-0.8373, -0.5545] | n/a (single seed) | 60 | 180 | episode-significant, `adaptive_mpc` broadcast across seeds |
| `full-zero_context` | healthy | +0.1065 | [+0.0694, +0.1441] | n/a (single seed) | 60 | 180 | episode-significant, `zero_context` broadcast across seeds |
| `full-zero_context` | actuator | +0.6135 | [+0.5323, +0.6928] | n/a (single seed) | 60 | 180 | episode-significant, `zero_context` broadcast across seeds |
| `full-zero_context` | perception | -0.5027 | [-0.6538, -0.3717] | n/a (single seed) | 60 | 180 | episode-significant, `zero_context` broadcast across seeds |
| `full-zero_context` | combined | -0.3272 | [-0.4396, -0.2220] | n/a (single seed) | 60 | 180 | episode-significant, `zero_context` broadcast across seeds |

### 3.2 Seed-level RMSE

Required with only three seeds: pooled intervals alone would hide seed spread.

| Method | Condition | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| `nominal_recovery` | healthy | 1.3579 | n/a | n/a |
| `nominal_recovery` | actuator | 1.7567 | n/a | n/a |
| `nominal_recovery` | perception | 1.2093 | n/a | n/a |
| `nominal_recovery` | combined | 1.2367 | n/a | n/a |
| `constant_context` | healthy | 1.3520 | n/a | n/a |
| `constant_context` | actuator | 1.7341 | n/a | n/a |
| `constant_context` | perception | 1.2022 | n/a | n/a |
| `constant_context` | combined | 1.3124 | n/a | n/a |
| `no_impact` | healthy | 1.1320 | 1.1381 | 1.1409 |
| `no_impact` | actuator | 1.4452 | 1.4102 | 1.4829 |
| `no_impact` | perception | 1.1570 | 1.1910 | 1.1496 |
| `no_impact` | combined | 1.1926 | 1.1981 | 1.2095 |
| `full` | healthy | 1.2263 | 1.1660 | 1.1738 |
| `full` | actuator | 1.5526 | 1.5394 | 1.4910 |
| `full` | perception | 1.1975 | 1.1916 | 1.1848 |
| `full` | combined | 1.2432 | 1.2081 | 1.2488 |
| `full_no_check` | healthy | 2.6056 | 3.2056 | 2.5851 |
| `full_no_check` | actuator | 2.5066 | 3.0125 | 2.3366 |
| `full_no_check` | perception | 3.5026 | 3.9762 | 3.4557 |
| `full_no_check` | combined | 3.5502 | 3.7428 | 3.3227 |
| `fallback_only` | healthy | 1.2221 | 1.2221 | 1.2221 |
| `fallback_only` | actuator | 1.5231 | 1.5231 | 1.5231 |
| `fallback_only` | perception | 1.1498 | 1.1498 | 1.1498 |
| `fallback_only` | combined | 1.2203 | 1.2203 | 1.2203 |

### 3.3 How eta was chosen

The one-step decrease condition is violated by the MPC candidate in **90.7%** of monitored steps at hardware authority.
Conformal calibration at delta=0.025 would give eta = 4.9093, which accepts
~97.5% and is therefore near-inert. Conformal calibration targets coverage of a
*certificate* claim, and Stage 7 finds no certificate to cover, so eta is instead
selected as the value minimising calibration-split RMSE over a declared grid.
Test episodes are disjoint from calibration.

| eta | calibration RMSE (m) | peak (m) | rejected fraction |
|---|---|---|---|
| 0.0000 | 1.7880 | 2.031 | 0.018 |
| 0.5000 | 1.7791 | 2.789 | 0.026 |
| 1.0000 | 1.5069 | 2.338 | 0.034 |
| 2.0000 | 1.3393 | 2.141 | 0.040 **<- selected** |
| 4.9093 | 1.3505 | 2.148 | 0.040 |

**Reading this table correctly.** eta is added to the right-hand side of Eq. (18), so a
larger eta *relaxes* the decrease inequality rather than enforcing it harder. Tracking
error nevertheless falls from 1.788 m to 1.339 m (**25%**) as eta grows from 0.00 to
2.00, while the rejected fraction *also* rises from 1.8% to 4.0%.

Those two facts look contradictory only if eta affected nothing but the candidate test.
It does not. The same eta appears in the fallback's own acceptance check, and a passing
fallback is one of the two pre-action eligibility conditions, so raising eta lets the fallback
pass more often, makes more samples eligible, and lets more candidates reach the test at
all. The number of rejections can therefore grow even though each individual test is
easier, and the trajectory changes as well, so the states at which the test is applied are
not held fixed across rows.

This curve is consequently **not** a clean isolation of the post-allocation check; it is a
joint eta-sensitivity of eligibility, supervisor share and candidate acceptance. The
eligibility-mediated part is unmeasured, because the sweep did not record per-eta
action-source fractions, and that instrumentation is required before any causal
attribution is stated. What the curve does support is narrower: eta matters for
closed-loop tracking, and eta = 0 is not the best available choice.

**This must not be reported as a rarely-active safety net.** At the selected eta the
check rejects 4% of candidate wrenches, so for most samples the transmitted
command is the fallback, and the closed loop is nearer to the certified gain than to
the MPC. The honest framing is that the supervision layer is a *frequent override* whose
authority happens to help tracking at hardware thrust, and that the MPC candidate
clears the one-step decrease test only a minority of the time (9.3%). Both facts are consequences of the same
underactuation that empties the certificate in Sec 4.

---

## 4. Claim 2 - the numerical recovery certificate

> *Abstract: "... and numerical recovery certificate remain to be validated."*

**Result: the certified region is empty at every point of the swept grid (0 of 1365 cells per reference family).**
This is the outcome build_scSim.md Sec 12 predicted. The value of the stage is that
it locates the boundary and names the binding term, rather than asserting a bound.

### 4.1 The contraction condition vs plant-parameter tolerance

Sec 14 lists "measured mass and inertia with tolerance" as an OPEN item explicitly
blocking certificate numbers, so it is swept rather than assumed. gamma+nu < 1 is
required before any radius matters.

| Tolerance | step: best gamma+nu | contracts | smooth: best gamma+nu | contracts |
|---|---|---|---|---|
| ±0% | 0.9616 | **yes** | 0.9127 | **yes** |
| ±1% | 0.9677 | **yes** | 0.9239 | **yes** |
| ±2% | 0.9728 | **yes** | 0.9353 | **yes** |
| ±5% | 0.9888 | **yes** | 0.9710 | **yes** |
| ±10% | 1.0043 | no | 1.0036 | no |

**The contraction condition requires mass and inertia known to within ±5%.** At ±10% no design in the grid contracts.

### 4.2 Where the boundary sits, and which term binds

`s_cert/R` is the distance to a nonempty region: it must reach 1. Reported at every
tolerance so the best cell is not quoted under an unrealistic assumption of perfectly
known mass.

| Family | Tolerance | best cell | lambda | s_cert/R | binding term |
|---|---|---|---|---|---|
| step | ±0% | duty=0.70 | 0.9800 | **97.3** | b_r |
| step | ±1% | duty=0.70 | 0.9822 | **110** | b_r |
| step | ±2% | duty=0.70 | 0.9845 | **126** | b_r |
| step | ±5% | duty=0.70 | 0.9916 | **233** | b_r |
| step | ±10% | - | - | - | no contracting design |
| smooth | ±0% | fmax=4.0N(alloc only) | 0.9573 | **2.11** | eta |
| smooth | ±1% | fmax=4.0N(alloc only) | 0.9628 | **2.42** | eta |
| smooth | ±2% | fmax=4.0N(alloc only) | 0.9684 | **2.85** | eta |
| smooth | ±5% | fmax=4.0N(alloc only) | 0.9859 | **6.4** | eta |
| smooth | ±10% | - | - | - | no contracting design |

At the realistic end (±5% tolerance, the tightest that still contracts):

- **step**: short by a factor of **233**, binding on `b_r` (b_r = 1.9451, eta_q = 0.0471, R_U = 1.080).
- **smooth**: short by a factor of **6.4**, binding on `eta` (b_r = 0.0913, eta_q = 0.3407, R_U = 5.683).

Two clean findings:

- **The step-setpoint reference is structurally uncertifiable.** Its 1.0 m setpoint jump in one 0.1 s sample is a reference defect no bounded thrust can follow, giving b_r up to 33.2 against R_U ~ 1. Sec 12 predicted exactly this.
- **The smooth feasible reference comes close.** At the maximum-authority corner (duty 1.0, fmax 4.0 N, no dead band) it is short by a factor of 2.1 with perfectly known mass and 6.4 at ±5%. Crucially the binding term there is the **allocator** allowance eta_q, not the reference defect: once the reference is feasible and the authority is raised, what stands between this system and a certificate is the quantised pulse-width allocator. That is the boundary the sweep was asked to locate, and it points at a different subsystem than expected.

### 4.3 Residual admissibility: not evaluated in this campaign

Stage 7 emits an empty `residual` object, so **no residual Jacobian enclosure was computed**
for this run and no admissible-scale bound exists to report. Earlier versions of this
section asserted a sensitivity ratio of "603x nominal" and inadmissibility "by four orders
of magnitude". Those were retained strings, not regenerated values, and the surrounding
fields printed as `n/a` at the same time. They are removed rather than reworded.

This also means the empty certificate result of Sec 4.1 **cannot** be attributed to residual
Lipschitz growth on this evidence. The swept certificate used nominal matrices, so it is a
statement about the nominal design budget, not about the learned model. Recovering the
residual analysis requires the checkpoint and latent-domain inputs that Stage 7 did not
find; until it runs, residual admissibility is **not evaluated**.

### 4.4 The horizon axis

The certificate is a one-step contraction under K, so N does not appear in it
algebraically. Sec 12 lists N because it determines achievable per-solve
correction, which is an operational statement, so N is swept in closed loop.

| Condition | N | RMSE (m) | rejected fraction | wall ms/step |
|---|---|---|---|---|
| healthy | 12 | 1.273 | 0.034 | 4.23 |
| healthy | 20 | 1.162 | 0.068 | 4.61 |
| healthy | 30 | 1.131 | 0.066 | 5.39 |
| healthy | 40 | 1.158 | 0.065 | 5.68 |
| healthy | 50 | 1.105 | 0.067 | 6.15 |
| combined | 12 | 1.259 | 0.051 | 4.67 |
| combined | 20 | 1.252 | 0.067 | 5.17 |
| combined | 30 | 1.313 | 0.071 | 5.61 |
| combined | 40 | 1.262 | 0.069 | 5.98 |
| combined | 50 | 1.311 | 0.076 | 6.52 |

---

## 5. How this simulation supports the paper

### 5.1 It reproduces the hardware effect with power the hardware cannot have

This is **not an independent replication**. The simulator's authority, estimator error
envelopes and duty law were *fitted* to the same hardware records the comparison is being
checked against, so agreement with those envelopes is calibration agreement, not independent
confirmation. What the study does add is statistical power on a controlled plant: hardware
has 3 comparisons at n = 3-5 runs with no paired intervals, while simulation has 4 conditions
at 60 matched scenario draws x 3 training seeds with paired intervals, and can run
ablations the hardware never flew.

| Comparison | Hardware zero -> learned | Simulation zero_context -> full |
|---|---|---|
| actuation fault | 1.105 -> 0.950 m, **-14.0%** (n=5) | 1.069 -> 1.528 m, **--42.9%** (n=60) |
| perception degradation | 1.895 -> 0.798 m, **-57.9%** (n=5) | 1.497 -> 1.191 m, **-20.4%** (n=60) |
| healthy | no matched hardware pair | 1.082 -> 1.189 m, **--9.8%** (n=60) |
| combined | no matched hardware pair | 1.417 -> 1.233 m, **-13.0%** (n=60) |

Hardware's largest actuation gain (1.315 -> 0.781 m, -40.6%, n=3) came from the act30 severity
level, which has **no matched simulated counterpart**: the simulated actuator condition
corresponds to the 70% level, and the smooth-eta severity sweep is a deliberately distinct
intervention that the protocol requires to be labelled separately. It is left out of the
table rather than paired with something it does not correspond to.

Read this honestly in both directions:

- **The direction is condition-dependent, and does not replicate everywhere.** Learned context significantly beats zero-context under perception and combined (2/4), and is significantly **worse** under healthy and actuator (2/4). The advantage is therefore specific to the perception-degraded regimes, which is the regime the hardware occlusion runs probe, and the healthy and actuator-only cells run the other way.
- **The magnitudes do not replicate either.** The simulated perception improvement is 20.4% against the hardware's 57.9%, i.e. roughly 2.8x smaller. The hardware occluded cells have the largest spread in Table I, so the honest inference is that the biggest hardware percentage sits at the optimistic end of what this mechanism delivers.
- **What this costs the paper.** A uniform win was claimed by the earlier campaign and did not survive closing the fault-information leak. The defensible claim is now narrower: context learning helps when perception is degraded, and is not a general improvement across fault modes.

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
entire study**: the post-allocation acceptance check is worth 1.09-2.45 m of RMSE, all 4
conditions significant, and enforcing it harder monotonically improves tracking across the
whole eta grid (Sec 3.3). So the check works operationally even where the guarantee does not
apply. Present Contribution 2 as a conditional theorem plus a numerical study that locates its
boundary, and lead its empirical support with the check.

### 5.3 What to change in the manuscript

In rough order of how much a reviewer would punish leaving it:

1. **Do not leave Contribution 1 worded as a supervision gain** while an appendix reports the negative ablation. An internal contradiction is worse than a null result. Restate it around the context input.
2. **Fix the framing of the acceptance check.** At the selected eta it rejects 3%-4% of candidate wrenches on the test split and the MPC candidate clears the one-step decrease test only 9.3% of the time. It is a *frequent override*, not a rarely-active safety net, and describing it as light-touch is contradicted by our own logs.
3. **Promote the acceptance-check result.** It is the largest and most robust number here and is currently under-sold relative to the context story.
4. **State the certificate result as a located boundary**, with the four requirements above, rather than as a guarantee or as a silent omission.
5. **Add the replication table of Sec 5.1** next to hardware Table I, including the honest note that the simulated perception gain is about half the hardware figure.
6. **Keep the abstract's admission** that both items remain to be validated, but say in the same breath what *is* validated: context conditioning and the allocated-command check, on hardware and in a 3840-episode matched simulation.

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


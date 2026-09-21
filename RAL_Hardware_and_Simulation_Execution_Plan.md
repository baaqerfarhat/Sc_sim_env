# RA-L execution plan: spacecraft experiments and simulation validation

**Prepared:** 19 September 2026  
**Manuscript:** `Multimodal_Context_Learning_for_Actuation_and_Perception_Fault_Tolerant_Model_Predictive_Control (3)(1).pdf`  
**Simulation baseline reviewed:** [commit 81f52657c7d16d8377ac0812d13295410de377a7](https://github.com/baaqerfarhat/Sc_sim_env/tree/81f52657c7d16d8377ac0812d13295410de377a7), run `v3-contract-and-ablation`  
**Purpose:** Instructions for the next implementation, hardware, and simulation work. This document updates the earlier guides where the latest review found completed repairs or new issues. It is an execution plan, not a report of experiments already performed.

## 1. The goal and the order of work

Keep the spacecraft hardware study as the primary physical experiment. Keep the current conditional recovery theory largely fixed. The next iteration must establish that the implemented controller matches the manuscript, that its distinctive components have useful effects, and that any numerical recovery claim has verified premises.

The present hardware supports latent-conditioned adaptation. It does not isolate the proposed behavioral loss or demonstrate the full recovery controller. The current simulation supplies valuable matched comparisons, but it still evaluates an incomplete implementation and reports poor practical completion, adverse behavioral-loss effects, and no successful recovery certificate.

Use this sequence:

1. **Recover hardware provenance and complete the log inventory.** This can proceed immediately alongside simulation repairs.
2. **Complete the controller and scoring implementation.** Do this before a new large comparison campaign or new hardware claims about that controller.
3. **Diagnose a small fixed development set.** Resolve the causes of supervisor dominance and transfer failure.
4. **Freeze the learning selection rule, controller, and evaluation protocol.** Separate development, calibration, and final evaluation roles.
5. **Run the focused simulation comparisons and prospective hardware blocks.** Use the same method definitions in both.
6. **Produce one useful verified recovery example if practical certification remains a contribution.** This is a separate validation track, not an interpretation of the ordinary tracking table.
7. **Revise the manuscript around what the completed evidence supports.** Retain adverse results and report their scope.

More trials are not a substitute for the first three steps. Conversely, a negative result is not a software failure simply because it is unfavorable. Each implementation gate below tests correctness; each experiment tests a scientific claim whose outcome remains open.

## 2. Evidence the paper needs

| Claim | Evidence needed | What would not establish it |
|---|---|---|
| Recent multimodal history improves adaptation | Dynamic context versus a separately trained constant context, with the same prediction losses and controller | Deployment-time zeroing of a learned context alone |
| Behavioral supervision contributes useful information | Positive behavioral weight versus zero weight with matched training and deployment; improved declared control or transfer endpoint | A falling behavioral training loss or attractive latent plot |
| Learned prediction improves control | Learned versus nominal prediction under the same recovery structure | Comparing controllers that also change cost, supervisor, and input limits |
| MPC planning contributes | MPC versus the same context-conditioned feedforward and feedback fallback, under matched gate/allocator/supervisor | Comparing MPC against a different nominal fallback |
| Checking after allocation contributes | Isolated check ablation, branch validation, and measured intervention consequences or a justified explanation for inactivity | Disabling eligibility, first-action screening, and the post-allocation check together |
| The robot completes or recovers the task | Physical final-target completion, post-fault reacquisition, maintained performance, and failures | Full-episode RMSE alone or a dwell before the relevant excursion |
| The recovery condition is numerically useful | Nonempty verified region, positive margin, accepted frozen-policy calibration, nontrivial eligible operation, interpretable physical bounds | An unsuccessful finite sweep, sampled Jacobians, or supervisor inactivity |
| The implementation operates at 10 Hz | Complete decision latency and deadline outcomes on the deployment computer | Solver time alone on a simulation workstation |

The paper does not have to demonstrate a positive effect for every component. It does have to align its contribution statements with the observed effects.

## 3. Preserve these existing assets and findings

### 3.1 Hardware

Keep Table I's physical measurements and individual trial records. The reported learned-versus-zero-context RMSE reductions are 14.0% at the recorded actuator 70% setting, 40.6% at actuator 30%, and 57.9% under half-camera occlusion. Keep the means, sample SDs, and actual run counts; do not retrospectively label these trials as tests of a newly implemented controller.

Recover individual time series wherever possible. Existing trials can support additional analyses if they contain the required signals and have compatible protocols. Never reconstruct missing trajectories or intervention times from aggregate RMSE values.

### 3.2 Simulation

Preserve the repaired command-information boundary, true-attitude plant rotation, unified physical execution contract, matched probe groups, separated training RNG streams, independent safeguard switches, and complete action-source decomposition. The fault-slot timing issue has been fixed in this version; do not redo that repair.

Preserve the negative results under their original version identifiers:

| Observation in the reviewed campaign | Interpretation to retain |
|---|---|
| Behavioral supervision adds approximately 0.052/0.138/0.045/0.066 m primary RMSE across healthy/actuator/perception/combined | No demonstrated tracking benefit from the evaluated positive behavioral weight |
| Development selection chose zero behavioral weight | Prediction-only is the selected model under that rule; the positive-weight model is an ablation |
| Isolated full-versus-no-post-check effect is zero | No measured incremental effect in this campaign; not a universal redundancy theorem |
| Full-method final-task successes are 10/180, 3/180, 2/180, 3/180 | Practical completion is poor under the declared specification |
| MPC candidates supply about 8–13% of commands; supervisor supplies about 42–66% | Attribution and supervisor diagnosis are essential |
| Transfer errors are about 4.8–5.1 m for learned methods | Transfer failure must be diagnosed and disclosed |
| No successful certificate in 2,730 searched cells; residual analysis absent | No verified recovery demonstration from that search |

These are development results for the reviewed implementation. Quantities affected by controller changes must be regenerated. Reuse training data and checkpoints when their inputs, targets, preprocessing, and training population remain valid; do not automatically retrain everything.

## 4. Freeze the method definitions before comparing them

Use explicit method identifiers in code, tables, and logs:

| ID | Definition | Main comparison |
|---|---|---|
| HW | One specified original zero-context hardware comparator, with its exact architecture, checkpoint, residual behavior, and cost documented | Continuity with existing physical results; a system-level comparison |
| M0 | Nominal predictor with the same recovery structure, constraints, cost, and supervisor as the learned controller | Learned prediction |
| M1 | Separately trained constant context; prediction losses only | Representation control |
| M2 | History-dependent context; prediction losses only | M2 versus M1 isolates changing context |
| M3 | Same history-dependent model plus the selected positive behavioral-loss coefficient | M3 versus M2 isolates behavioral supervision |
| M4 | M3 checkpoint, with only enforcement of the post-allocation decrease test disabled | Isolated decrease-check effect |
| M5 | M3's context-conditioned feedforward plus feedback and checks, with MPC candidate generation removed | MPC contribution |
| M6 | A documented adaptive-MPC comparator with fixed adaptation limits and tuning budget | Comparison with conventional adaptation |

Use M0–M3 with the same horizon, cost, model interfaces, allocator, source eligibility, fallback, supervisor, deadlines, and physical scenario draws. HW may intentionally differ; state those differences and do not use HW alone to attribute a particular component's effect.

M4 retains source eligibility, first-action screening, solver-failure handling, and command admissibility. M5 must use the same learned feedforward as M3; computing a neural residual and then discarding it is not this comparison.

If development selects M2 as the deployed method, also construct M2's own no-post-check and fallback-only counterparts when making claims about that selected controller. Do not infer those effects solely from M3's ablations. A deterministic baseline does not acquire additional independent replicates by repeating it for three checkpoint labels.

**Required deliverable:** a one-page method-to-equation map identifying the exact hardware and simulation implementation of Eqs. (2), (3), (7), (8), and (15)–(19). Distinguish the earlier hardware controller from the final proposed controller wherever they differ.

## 5. Simulation implementation: corrections required before final runs

### S0.1 Use one learned model consistently

Implement one canonical function `f_theta(x_hat, u_nom_tx, z)` with explicit state ordering, coordinate frame, units, normalization, and sample period. The manuscript and repository currently order the six state coordinates differently; implement and test the permutation rather than relying on matching array lengths.

Use this same model for training predictions and loss evaluation, reference feedforward, affine prediction, derivative construction, and mismatch evaluation. Training targets remain the observed successor estimates. For each reference pair and fixed current context:

1. Solve the manuscript's feasible feedforward problem over the declared input budget.
2. Evaluate the feedforward defect with the returned feasible input. Do not force this defect to zero.
3. Compute the reference-local error-model Jacobians, including the residual contribution and coordinate transformations.
4. Freeze the current context across the prediction horizon, as specified in the paper.
5. Use the resulting affine models consistently in optimization and the first-action and allocated-action checks.
6. Evaluate actual transition mismatch against that affine predictor at the nominal transmitted command.

The current shortcut—evaluate a residual once at the current state and previous transmitted input, then add it unchanged across the horizon—does not implement those equations. Do not substitute a direct nonlinear check for the paper's affine check without explicitly changing and re-deriving the formulation.

**Completion evidence:** selected fixed inputs produce consistent model outputs across all callers; numerical directional derivative checks agree with the implemented Jacobians away from declared nonsmooth boundaries; feedforward failure has a deterministic logged outcome. Numerical derivative checks validate code locally, not a continuum bound.

### S0.2 Implement the stated optimization or verify every required condition

Implement the componentwise pseudo-Huber objective, input constraints, predicted-state region constraints, terminal membership, and first-action decrease condition. Report solver tolerances and numerical feasibility margins.

The first-action decrease condition has no implementation allowance on its right-hand side; the subsequent allocated-action condition includes the allowance. Preserve this distinction in the solver and independent checks.

A proposal generator followed by an independent verifier can be used if declared clearly. The verifier must then check all relevant constraints, including affine dynamics residuals and solver feasibility tolerances. Verifying only the first action does not make the entire returned trajectory a feasible solution of Eq. (15).

The gate must distinguish operational checks from theorem eligibility. A radius test plus a passing fallback is not sufficient to establish verified model, context, reference, allocator-memory, and corridor/chart domains.

**Completion evidence:** known feasible and infeasible examples route to the correct action source. Solver failure and deadline miss route to the stored passing fallback when eligible. An ineligible source invokes the frozen supervisor and does not receive a recovery-guarantee label.

### S0.3 Preserve causal command execution and complete reference bookkeeping

Retain software-only `commit()` and evaluator-side `realize()` consuming exactly one hidden-fault slot. Neither controller histories nor command checks may receive physical fault-reduced pulses or hidden fault variables.

Fix reference logging: the current runner stores `ref_prev[1]` in both `log.ref` and `log.ref_next`. Store the actual current and committed successor references separately. Preserve that committed successor through the scored transition. A subsequent reference replacement must be explicitly accounted for in mismatch and pass any needed geometric-domain checks.

Retain H+1 physical states and H+1 timestamped estimates for H transmitted commands, including the final transition's successor. Do not fabricate the final estimate by copying the previous one. Log the estimator update timing needed to associate each command with its source and successor estimate.

**Completion evidence:** smooth-reference and waypoint-switch examples retain the correct reference pairs; every command has both required endpoints; source-context labels remain attached to fault-onset and domain-exit transitions.

### S0.4 Validate the isolated post-allocation branch correctly

The pre-allocation condition uses proposed input `u_star`; the post-allocation condition uses nominal-equivalent transmitted input `u_nom_tx`. An allowance on the second right-hand side does not by itself imply that passing the first guarantees passing the second.

Use controlled software examples to check these outcomes:

| Constructed situation | Enforced policy | No-post-decrease policy |
|---|---|---|
| Source ineligible or fallback fails | Supervisor | Same supervisor |
| Solver failure or deadline miss at eligible source | Stored passing fallback | Same fallback |
| Candidate fails first-action condition | Stored passing fallback | Same fallback |
| Candidate's allocated command violates the input budget | Stored passing fallback | Same fallback |
| Candidate passes earlier tests but fails allocated decrease, when compatible with the declared design | Stored passing fallback | Candidate; record the failed decrease verdict |

The last case requires a valid passing fallback and unchanged earlier tests. Extreme allowance settings that send every sample to the supervisor do not exercise that branch.

Use a separate evaluator to reconstruct the fixture's gate premises, candidate horizon feasibility, fallback admissibility, and pre/post-allocation slacks from saved values. The controller's own Boolean verdicts are not sufficient independent validation.

First determine what the allowance bounds. If it is a verified uniform bound on allocation error for **every feasible candidate**, the triangle inequality may make the post-allocation decrease test redundant over that domain. In that case, document the implication; do not manufacture a rejection. The manuscript's fallback-realization premise alone does not establish a bound for every candidate. Never shrink an allowance merely to obtain a favorable ablation.

Specifically, the sufficient redundancy condition is

\[
\sup_{\text{feasible candidates}}\|B(u_{\mathrm{tx}}-u^\star)\|_P\leq\eta.
\]

Under this condition, passing the first-action inequality implies the allocated decrease inequality. A bound on raw wrench error without its B/P transformation is not the same condition.

**Completion evidence:** independent switches differ only as declared; branch behavior is checked; zero intervention, if observed, is reported honestly with its operating conditions. No hardware experiment disabling this check is required by this plan.

## 6. Shared metrics: define and implement once

Use physical state for outcome scoring, and estimated state for the controller's internal checks. Vicon is scoring ground truth on hardware unless an explicitly identified comparator uses it; simulator truth is never an input to the proposed controller. If an independent physical safety interlock uses Vicon, disclose and log that separate channel. Do not claim Vicon is used exclusively for scoring when such an interlock exists.

### 6.1 Primary and practical endpoints

Declare one primary endpoint before final evaluation. A defensible continuation of the existing protocol is position RMSE over a fixed post-onset interval, with full-episode RMSE as secondary. Healthy trials have no fault onset; report their full-episode endpoint or a prespecified matched evaluation interval without calling it post-fault recovery.

Always accompany RMSE with:

- Final-task completion and completion time.
- Whether the final target remains satisfied at the end.
- Post-onset peak position and yaw errors.
- Recovery maintenance/reacquisition outcomes and latency.
- Failure, early stop, invalid measurement, and timeout counts.
- Command usage, saturation, and action-source fractions.
- Full decision latency and deadline misses.

For a final-target task, success requires position and yaw tolerances to hold for the declared dwell at the **final intended target** before the deadline. An intermediate waypoint does not count. For a continuously moving trajectory, report a declared tracking criterion; a terminal-waypoint completion metric may be undefined.

Retain the current 0.15 m, 5 degree, 2 s, 60 s specification as a documented development specification unless mission requirements justify a replacement. Choose any revised specification before final testing and explain its physical basis. Show sensitivity to tolerances without replacing an unfavorable primary result after seeing it.

The approximately 0.662 m recovery threshold was derived from baseline performance. Label it as a separate baseline-relative diagnostic; never merge it with the strict task-success metric.

### 6.2 Fix the recovery ordering bug

The reviewed code can mark a dwell at fault onset followed by a later excursion as reacquisition at time zero. Replace that logic with explicit temporal order using the **same declared recovery criterion** for onset status, excursion, return, and maintenance:

```text
Determine inside_recovery[k] from the declared recovery tolerance(s).
Start the recovery evaluation clock at fault onset k0.

If inside at k0, the full assessment window is valid, and no later excursion occurs:
    record maintained = true, reacquisition = not applicable.
Otherwise:
    if outside at k0: excursion_start = k0
    else: excursion_start = first later sample outside tolerance
    search for the first qualifying dwell AFTER excursion_start
    if found: record reacquired = true and the return/dwell timestamps
    otherwise: record reacquired = false, with failure/censoring reason
```

Record both time from onset and time from excursion. State whether latency ends at the start or completion of the qualifying dwell; retaining both timestamps avoids ambiguity. Use elapsed timestamps: at 0.1 s sampling, a 2 s dwell between observed endpoints spans 20 intervals and 21 observations. Twenty observations alone span only 1.9 s unless a different sample-hold convention is explicitly justified. Report subsequent departures as well: reacquisition followed by another failure is different from sustained recovery. Being outside tolerance already at onset must be distinguished from a fault-induced excursion.

An early stop or missing assessment interval cannot establish maintenance. Keep its failure or incomplete-observation status, and do not let the absence of later samples mean that no excursion occurred.

Test at least four synthetic traces: always inside; initially outside then return; inside then leave with no return; inside then leave then return. Include a trace that would trigger the current false time-zero label. These scoring checks do not require new physical experiments.

### 6.3 Fair horizons and early termination

Every method must face the same declared task duration, deadline, reference policy, and impairment intervention rule. A position-triggered reference can switch at different times because trajectories differ; record that behavior instead of claiming identical realized reference time series. The final intended objective must remain the same.

Do not make a failed controller look better by computing RMSE only over its short pre-stop record. Count task failure, retain the stop reason, and report how much of the planned window was observed. Prespecify any failure penalty or composite outcome; distinguish it from measured RMSE. Show observed-window RMSE separately when a complete window is unavailable. Do not impute an unobserved physical trajectory.

Predefine Vicon validity criteria, maximum permissible synchronization/interpolation gaps, and handling of invalid scoring windows. Do not interpolate long missing intervals or discard an impaired run because its observed score is unfavorable. Distinguish a controller/task failure from an unavailable outcome caused by independent scoring equipment; retain both in the attempt ledger and report the relevant denominators.

### 6.4 Common logging schema

| Group | Required fields |
|---|---|
| Run identity | Attempt ID, method ID, code/config/checkpoint identifiers, training seed, scenario or hardware block ID, operator/date |
| Timing | Sensor and command timestamps, control index, onset command and realized-onset estimate, solver and complete decision times |
| State | Physical scoring state, controller estimate, innovations, modality availability, tracking errors |
| Reference | Original task definition, current and committed next reference, switch events, final target, deadline |
| Learning/model | Context vector, model inputs/outputs, preprocessing identifiers, reference-local A/B matrices, feedforward input and defect |
| Commands | Proposed wrench, nominal transmitted wrench, commanded duties/pulses, allocator memory; actual faulted pulses evaluator-only in simulation |
| Checks | Source eligibility and reasons, fallback/candidate verdicts, separate slacks, solver feasibility/status, deadline status |
| Action attribution | Candidate, first-action fallback, allocated-decrease fallback, admissibility fallback, solver/deadline fallback, supervisor |
| Outcome | Completion, sustained completion, maintenance, ordered reacquisition, subsequent departure, stop/failure reason |

Separate logging visibility from controller visibility. Fault labels and Vicon may exist in evaluator logs without being made controller inputs.

## 7. Hardware: recover missing information before collecting new runs

### H0.1 Build an attempt ledger

List every available attempt, not only successful or stable trials. For each record, recover condition, method, task, start/end times, checkpoint/configuration, fault onset, completion/abort status, available signals, and inclusion decision.

For Table I's selected final five stable fixed-context trials, report how many earlier attempts existed, why they were not included, and whether the selection rule was defined before their outcomes. If a subset is justified by a configuration change, report it as a separate configuration rather than pooling it with other versions.

Do not invent paired comparisons retrospectively. Existing trials are paired only when the experimental design and run records support a genuine shared block. Otherwise report them as unpaired historical observations.

### H0.2 Document the physical implementation

Recover or measure:

1. Vehicle mass and inertia, with provenance and uncertainty; do not promote round simulation constants to measured values.
2. Thruster geometry, nominal thrust, pressure range or regulator behavior, duty ceiling, minimum pulse, deadbands, and allocation memory.
3. The exact meaning of each actuator setting: remaining impulse fraction, firing fraction, pulse scaling, disabled channels, or another intervention. Record affected thrusters and schedule/phase where applicable.
4. Occlusion geometry, camera/stream affected, duration, intervention repeatability, and available estimator diagnostics.
5. Actual deployed horizon, cost, weight adaptation if any, feedforward, residual model, gate, and fallback. Resolve N=10 versus N=12 from the configuration attached to the runs.
6. Onboard computer, software versions, estimator/controller rates, timestamp alignment, and Vicon-to-estimator frame alignment.
7. Exact reference/task used for each reported row. A listed library of trajectories is not evidence that each was evaluated.

**Deliverable:** a compact hardware protocol table and a configuration file associated with each controller generation. No new tracking campaign is needed merely to document these facts.

### H0.3 Re-score compatible existing records

Where time series exist, compute the shared metrics in Section 6. Plot individual outcomes, not only aggregate bars. Use uniform scoring windows only where the recorded protocols permit them; otherwise retain separate strata and explain the difference.

Priority plots are physical reference and trajectory, onset-aligned position/yaw error, estimator-versus-Vicon error, nominal transmitted commands, and context/action-source traces when logged. Mark missing channels explicitly.

Historical results remain useful even if some fields cannot be recovered. They should then be described as evidence for the earlier latent-adaptation implementation, with the new prospective experiment supplying the missing causal comparison.

## 8. Hardware: prospective matched experiment

### H1. Choose a focused core matrix

For the paper retaining behavioral supervision as a contribution, use this core:

| Condition | M1: trained constant context | M2: dynamic, prediction-only | M3: dynamic, behavioral loss |
|---|---:|---:|---:|
| Healthy | 6 blocks | 6 blocks | 6 blocks |
| One prespecified actuator impairment | 6 blocks | 6 blocks | 6 blocks |
| Half-camera occlusion | 6 blocks | 6 blocks | 6 blocks |

This is **54 episodes: 3 methods × 3 conditions × 6 blocks per condition**, or 18 matched method triplets. Six blocks per condition is a resource-planning starting point, not a claim of adequate statistical power or likely acceptance. Determine the fixed final count using an independent pilot and the precision procedure below.

Choose the actuator intervention on physical relevance and repeatability before the final campaign. Either recorded 70% or 30% can be the primary setting once its meaning is established. Preserve the existing results at the other severity as historical evidence, or add it as a prespecified extension.

If the final paper withdraws behavioral supervision as a main contribution, the core M1–M2 hardware comparison is **36 episodes**. Keep the unfavorable simulation loss ablation. Removing M3 from this hardware campaign is a change of scientific scope, not a way to conceal a failed test while retaining its benefit claim.

Decide the core methods before collecting the randomized blocks. If M3 becomes ready only after the M1–M2 study, collect fresh paired M2–M3 blocks. Adding M3 alone to historical M2 trials does not establish prospective pairing. Six new M2–M3 blocks across three conditions require 36 additional episodes; that sequence totals 72 episodes rather than the 54 of a planned three-method campaign.

Useful extensions, in priority order:

| Extension | Added episodes at six blocks | Purpose |
|---|---:|---|
| HW in the same three conditions | 18 | Matched continuity with the original spacecraft comparator |
| M1–M3 at a second actuator setting | 18 | Severity robustness; 12 if using M1–M2 only |
| M1–M3 under simultaneous actuator/perception impairment | 18 | Physical evidence for simultaneous faults; 12 with two methods |
| Selected controller versus its matched fallback-only version on a demanding task | 12 | Physical evidence for planning value |

Do not require every extension to fit in the first campaign. Combined faults are mandatory in simulation; they are needed on hardware if the paper claims experimentally demonstrated simultaneous-fault recovery on the spacecraft. Separate actuation and perception hardware trials alone support separate impairment conditions.

The HW extension covers one precisely specified legacy arm. Including separate legacy zero, hand-tuned, and learned arms would require additional episodes; they are not collectively one comparator.

### H2. Define a matched block and randomize order

A block contains one attempt for each compared method under the same condition, task definition, target duration, intended onset, starting-state tolerance, and closely matched physical operating conditions. Organize six rounds, each containing one block for each of the three conditions; randomize condition order within rounds.

1. Choose a block schedule in advance; balance or randomize method order within blocks.
2. Record pressure, battery state, estimator initialization, initial position/yaw/velocity, and environmental conditions that can drift.
3. Reset the vehicle and all controller/allocator/estimator histories according to the frozen protocol before each attempt.
4. Apply the same intervention rule. Evaluator-side onset is never sent to the controller.
5. Preserve all started attempts and stop reasons. Replacements for equipment failures follow a predeclared rule, with the original retained in the ledger.
6. Retain the existing physical testbed interlocks. A stop is an outcome to report, not an invitation to bypass an interlock.

Hardware pairing controls protocol and operating conditions; it does not create identical noise realizations. Describe it as blocked physical experimentation, not common-random-number replay.

Use a fixed, documented checkpoint per method for the minimal physical study, selected on development data before hardware outcomes are examined. The resulting hardware inference is conditional on those checkpoints. If resources permit, distribute blocks across matched training seeds and analyze that hierarchy; do not quietly choose each method's best hardware-performing seed.

### H3. Separate task completion from a recovery demonstration

For the main tracking task, use the same original mission and complete scoring horizon across methods. Record impairment onset during a prespecified phase with enough post-onset time to assess response.

A concrete starting configuration for comparison with the current 60 s simulator campaign is a 60 s episode, fixed onset at 20 s, and an impairment persisting for the remaining 40 s; healthy runs receive an evaluator-only sham event at 20 s. Validate in an independent engineering pilot that this duration can assess the selected mission under the real authority. If the mission requires a longer duration, freeze that revised duration before final collection, use it in the corresponding new simulation population, and report the earlier 60 s results separately. Do not compare different-duration RMSEs as though the protocols matched.

For a dedicated recovery test, establish pre-fault tracking or station keeping under a fixed dwell rule, then inject the impairment and evaluate maintenance or ordered reacquisition. Freeze a timeout for failure to reach the pre-fault state; report those failures instead of conditioning the study on controllers that happened to settle.

Choose one onset protocol:

- **Fixed-time onset:** all methods receive the intervention at the same elapsed time; analyze whether each was already inside tolerance.
- **Event-based onset:** inject after the same pre-fault dwell criterion, with a fixed timeout. This isolates disturbance response from initial approach but requires reporting readiness failures and differing onset times.

Do not mix these protocols under one recovery-time average. The theorem's recovery clock begins with eligibility and membership in its region, which is a third clock and must be logged separately when used.

### H4. Choose the final count using precision

Use separate pilot blocks to estimate the SD of within-block primary differences. For approximate planning of a mean paired difference, an initial estimate for a desired confidence half-width `h` is `n ≈ (1.96 s_difference / h)^2`; refine with the appropriate small-sample or simulation-based calculation. This is a planning approximation, not the final analysis.

Choose `h` and a practically relevant improvement from task requirements, not from whichever difference the pilot happens to favor. Binary task-success precision may require considerably more blocks than continuous RMSE. Freeze the final number before the final campaign, or prespecify a valid sequential design. Do not stop when a p-value first becomes favorable.

**What this hardware package should convince reviewers of:** the changing-context or behavioral component improves a physical outcome under matched conditions, without being explained by different controller settings or selected successful trials. The healthy comparison distinguishes general improvements from additional impairment-specific gains; helping healthy operation does not invalidate an impaired-operation improvement. If the effect remains uncertain, show the interval and narrow the claim.

## 9. Simulation: diagnose before scaling the campaign

### S1. Fix a small development set

Use approximately 3–5 prespecified episodes per main condition and 3–5 transfer episodes. Reuse them while debugging, identify them as development cases, and retain representative failures. They are not final test evidence.

For each episode, produce aligned panels showing:

1. Physical and estimated tracking errors, reference changes, onset, and task tolerance.
2. Eligibility and its separate failure reasons.
3. Candidate, each fallback cause, and supervisor action source.
4. Proposed versus transmitted nominal commands, saturation, and allocator effects.
5. Prediction mismatch, feedforward defect, and candidate/fallback check slacks.

### S1.1 Diagnose supervisor dominance

Identify where progress toward the target stops. Is the fallback failing decrease, the state outside the admitted region, the solver infeasible, or the candidate failing first-action screening? Does the supervisor dissipate velocity without advancing toward the target? Does a reference jump repeatedly make the domain ineligible?

Change one diagnosed cause at a time. If the supervisor is redesigned, keep its rule fixed across all compared methods and treat the change as a new policy requiring fresh final evaluation and calibration. Do not enlarge the gate or allowance solely to improve the MPC action percentage.

There is no required minimum MPC percentage for correctness. If planning is rarely used and provides no measurable benefit, the manuscript must explain the architecture's actual contribution rather than imply that MPC drives most observed recovery.

### S1.2 Diagnose transfer failure

Run M0, M1, M2, M3, the selected method's matched fallback, and HW on the same transfer draws. The existing comparison against HW alone does not isolate the residual, because the recovery structure also differs.

Check:

- Reference feasibility under actual impulse authority and the selected horizon.
- Coordinate transforms, angular wrapping, current/next reference timing, and velocity feedforward.
- One-step and frozen-context multistep prediction on common held-out sequences.
- Context distribution, residual magnitude/clipping, and out-of-range normalized inputs.
- Action-source and eligibility changes relative to in-distribution cases.

After tuning to the previously held-out family, it becomes development data for the revised controller. Evaluate a genuinely untouched transfer family or explicitly label further results on the original family as post-diagnosis validation. Do not continue calling the same repeatedly tuned family unseen.

**Gate to larger runs:** the controller executes its intended logic, scoring is correct, and the remaining poor outcomes have been investigated enough that another large campaign answers a scientific question. This gate does not require artificially favorable outcomes.

## 10. Simulation: final comparison package

### S2. Training and selection

Keep parent-episode splits; all ordinary windows and probe branches inherit the parent split. Fit normalization and signature scales only on training data. Keep matched probe initial-condition groups, warmup, excitation, duration, and noise-repetition rules. Regress physical response against nominal transmitted commands for offline supervision; hidden physical labels remain outside deployed histories.

Train M1, M2, and M3 with at least three matched training seeds for the initial final comparison; five seeds would better characterize training variability if compute permits. These counts are recommendations, not a guarantee of decisive intervals.

Match initialization wherever architectures permit, minibatch ordering, prediction/multistep sampling, optimizer steps, checkpoint selection, data volume, and prediction-loss weights. Keep behavioral sampling in its own RNG stream. Report extra training/probe-generation cost; do not describe equal optimizer steps as identical total computation.

Retain a zero coefficient in the behavioral-weight grid. If the scientific target is control or transfer, select the coefficient using a declared development control/transfer criterion rather than silently replacing the current one-step rule after inspecting test results. Report both the selected model and the positive-weight ablation. Do not claim a positive-weight method was selected when zero won.

### S3. Core matched comparison

| Population | Required methods | Suggested initial scale |
|---|---|---|
| Healthy | HW, M0, M1, M2, M3, M4, M5, M6 | 60 fresh scenario draws |
| Actuator impairment | Same | 60 fresh scenario draws |
| Perception impairment | Same | 60 fresh scenario draws |
| Combined impairment | Same | 60 fresh scenario draws |

Evaluate every learned method on all selected training seeds. Thus three seeds and 60 scenarios produce 180 rollouts per condition, but still only 60 distinct scenario draws. Run a deterministic baseline once per draw and pair it with each learned realization as appropriate; do not count its duplicated outcomes as independent evidence.

Use common exogenous random streams for process uncertainty, estimator noise, onset, and fault schedule. Controller branching must not consume those streams differently. Record state-dependent effects separately: the same noise stream does not force observations or event-triggered reference switches to be identical once trajectories diverge.

Use nominal hardware authority for the principal simulated-spacecraft comparison. Authority upgrades must change actual physical thrust or duty capability and be clearly labeled as a different plant; an allocator limit alone is not a thrust upgrade.

### S4. Focused stress tests

After freezing the method, evaluate:

1. **Held-out reference:** one genuinely untouched trajectory family under actuator and combined faults.
2. **Parameter shift:** a declared mismatch range beyond training, such as ±15% versus training ±10%; call this 1.5 times the range, not double.
3. **Fault timing/severity:** enough variation to establish that conclusions are not tied to one deterministic onset phase. Separate severity strata and preserve failures.

Forty fresh draws per selected stress condition across the same training seeds is a reasonable starting scale. Adjust using the required precision and resources, not a requirement to make every interval significant. Include M0 and the matched fallback in transfer diagnostics so failure attribution is possible.

Further horizon or authority grids are secondary. Resolve the actual hardware horizon from provenance. The current N=10 versus N=12 experiment finds small point estimates, but its wide intervals do not establish equivalence or that no conclusion could depend on horizon.

### S5. Statistical reporting

For each primary pair, compute paired differences on matched scenario draws. Report:

- Effect estimate in physical units and a 95% interval.
- Per-training-seed results.
- Episode-resampled intervals conditional on the fixed checkpoints.
- Crossed seed-and-scenario intervals where the sampling structure supports them.
- Distinct scenario count, training-seed count, and total rollout count separately.

Bootstrap whole scenario vectors containing all compared methods and checkpoint outcomes, preserving the shared-scenario dependence. For crossed intervals, also resample training-seed identities while retaining their paired method outcomes. Do not independently resample individual rollout rows as though each row came from an unrelated scenario.

For hardware, use the randomized block as the pairing unit and account for day/session structure where material. Do not treat timesteps, overlapping windows, or probe branches as independent trials.

Predeclare primary contrasts and endpoints. Treat many secondary condition/metric comparisons as exploratory or use a stated multiplicity procedure. Report binary success counts and uncertainty; report unsuccessful recovery attempts alongside latency. A latency average among successes alone does not establish superior recovery.

An interval containing zero does not establish equivalence. An interval excluding zero does not guarantee practical significance. Define any equivalence or noninferiority margin before testing. With only three training seeds, uncertainty about training variability remains substantial.

## 11. One useful recovery-bound demonstration

This track is necessary if the paper claims practical numerical validation of its recovery construction. It does not require certifying the entire spacecraft task library or every fault.

### C1. Select a narrow realistic operating case

Start with station keeping or a smooth feasible reference, modest initial error, a bounded context/reference domain, and realistic nonzero model/estimation uncertainty. Begin with healthy operation if needed, then test a declared impairment inside the supported population. Identify which parts of a full mission lie outside this local regime.

Preserve the real nominal hardware command chain if the example is called hardware-matched. A redesigned actuator or ideal estimator is a separate illustrative system. Do not erase uncertainty, impose oracle fault information, or tighten error envelopes by deleting difficult transitions.

### C2. Complete deterministic verification

Using the actual learned model and implemented feedforward, verify:

1. The admitted reference, context, state, and allocator-memory domains.
2. A common metric and feedback with a continuum bound `lambda < 1`.
3. A reference-defect bound over that domain.
4. Input, corridor, and attitude-chart upper limits on the radius.
5. Fallback realization over the declared domain, or an explicitly scoped pointwise-fallback formulation with its corresponding premises.
6. Sound treatment of numerical error in the claimed verified bounds. Sample checks and first-order rounding estimates are not substitutes for this claim.

If invoking the uniform fallback-realization lemma, use a rigorous allocation-error enclosure over its relevant domain, not a maximum from randomly sampled allocator calls. Include minimum pulse, saturation, and memory. Alternatively, the existing theorem can use the pointwise stored-fallback check with conservative numerical comparisons; do not claim uniform fallback availability in that case, and report actual eligibility and its duration. No new theorem is required for that existing conditional route. The model, region, and error-envelope premises still need verification. Report missing checkpoint/context-domain inputs as an error or explicit incomplete status; never turn an empty residual-analysis object into a successful learned-model bound.

Find a radius satisfying

\[
s_{\mathrm{cert}} = \frac{b_r+d_{\mathrm{cert}}+\eta}{1-\lambda}
< R \leq \min\{R_U,R_{\mathrm{corridor}},R_{\mathrm{chart}}\}.
\]

Report the strict margin and convert the resulting error region to position/yaw units using the manuscript's projections and physical-estimation allowance. A numerically positive radius is insufficient if its physical bound is uninformative for the chosen task.

### C3. Freeze before final calibration

Freeze model weights, normalization, feedforward solver, MPC, gate, supervisor, reference behavior, allocator, P, K, R, implementation allowance, and design error budgets. Use a separate fitting split for context cells and score objects.

Then generate independent complete episodes under this same frozen hybrid policy. For every recovery-active source k, retain the affine mismatch and both physical estimation errors at k and k+1, indexed by the **source context**. Include active fault-onset and exit-causing transitions. Retain zero-active episodes with the specified zero maximum; report their frequency so coverage cannot be mistaken for useful recovery activity.

Missing active-transition measurements do not receive a zero score. Resolve acquisition completeness or declare the calibration dataset inadequate for the stated procedure; do not replace difficult incomplete episodes with successful ones and silently change the calibration population.

Use one maximum score per complete episode and error channel. Do not calibrate per-timestep quantiles of check slacks and call that the paper's episode-level procedure.

For a concrete planning example, use 200 calibration episodes and 100 independent test episodes per frozen certified policy/population, in addition to fitting data. With delta_D = delta_E = 0.025, each calibration threshold uses sorted rank

\[
\left\lceil(200+1)(1-0.025)\right\rceil = 196.
\]

The paper's minimum of 39 calibration episodes permits a finite threshold at that error level; it does not ensure acceptance, precision, or a useful region. The suggested 200/100 allocation is not a guarantee of success either.

Accept the numerical certificate only if the calibrated bounds fit the previously frozen budgets. If calibration is used to redesign the policy or its budgets, that set becomes development data; generate fresh final calibration and test data for the revised policy.

### C4. Report what was actually established

Produce one table with P/K identifiers, lambda, reference bound, prediction budget, allowance, radius, strict margin, input/corridor/chart limits, calibration thresholds, acceptance outcome, and physical error projections.

On the test episodes, show active fractions and consecutive active-run lengths, empirical envelope violations, source and successor physical errors, bound traces, and the declared entry-time comparison. The theorem's clock starts inside C with eligibility; do not compare it directly to fault-onset latency when those events differ.

The statistical statement is marginal over the declared calibration/test population: it bounds the joint event of acceptance and a relevant violation. It is not a guarantee conditional on certificate acceptance, on a particular fault class, or on the gate being active. Report per-condition empirical results separately from that marginal statement.

Simulation calibration supports the simulated population. A hardware probability claim would require its own exchangeable complete hardware calibration/test episodes under the frozen physical policy. The small tracking campaign in Section 8 does not supply that evidence.

If no useful region survives this focused effort, report the failed sufficient-condition search and narrow the numerical guarantee claim. It does not prove physical impossibility or a universal necessary mass-identification tolerance.

## 12. Compute and mechanism measurements

On the deployment computer, time the complete cycle: preprocessing, context inference, feedforward, derivatives, optimization, allocations, verification, and command dispatch. Report median, p95, p99, maximum, and deadline-miss rate relative to the 100 ms period, along with the computation reserved for fallback and transmission.

Record cold starts and normal operation separately. A missed deadline must retain its source eligibility and failure label rather than being reclassified as inactive after the outcome.

Report action fractions using a common denominator of all control steps, and optionally conditional fractions among eligible steps. Separate first-action rejection, post-allocation decrease rejection, input-admissibility rejection, solver/deadline fallback, and supervisor. Do not describe the previous 3–4% input-budget rejection as the decrease-check rejection.

For MPC-versus-fallback, compare task performance, input usage, peak error, and compute. If planning adds no useful benefit in the evaluated task, say so. A harder but physically relevant task may test planning better; declare it before final evaluation rather than selecting only a task on which MPC happens to win.

## 13. Tables, figures, and manuscript integration

### Main-paper evidence package

| Item | Required content | Reviewer question answered |
|---|---|---|
| Hardware protocol table | Physical fault definitions, runs/blocks, task/onset, deployed controller, scoring, exclusions | Were the physical comparisons fair and reproducible? |
| Hardware outcome table | Existing historical rows clearly identified; new matched outcomes, RMSE, success, recovery and uncertainty | Does it work on the spacecraft? |
| Simulation component table | M1–M2, M2–M3, learned–nominal, MPC–fallback, isolated check; favorable and adverse rows | Which proposed components matter? |
| Recovery example table | Verified constants, acceptance, physical bounds, active coverage; only if completed | Is the theoretical construction useful? |
| Correct architecture figure | Actual history, offline supervision, learned model/feedforward, fixed-cost MPC, allocation, check, fallback/supervisor | What is actually implemented? |
| Physical response figure | Reference/trajectory and onset-aligned errors with individual-run information | Does average improvement reflect meaningful behavior? |
| Mechanism/bound figure | Action sources and errors, or observed eligible-run error against a valid bound | What produces improvement and where does the guarantee apply? |

Merge repetitive hardware summary graphics to create space. Replace the plotted `oracle` label with `hand-tuned context`. Resolve the horizon and cost descriptions from actual configurations. Add and discuss the closest context-aware adaptive-control literature, including the neural-ODE work cited in the review.

Generate numerical tables from validated artifacts, then check the surrounding conclusions manually. The reviewed report still contains text calling a zero check effect the largest significant benefit and text asserting residual bounds that were not computed. Automated report generation does not make those claims correct.

Keep detailed sweeps, code, logs, configurations, and additional diagnostic artifacts in the repository. Required scientific arguments and results must fit the journal's permitted manuscript; do not rely on an extra textual appendix outside RA-L's eight-page limit. Anonymize the initial submission according to the journal's instructions.

## 14. Completion checklist and decisions if outcomes remain negative

### Minimum checks before final evidence collection

- [ ] Hardware ledger and method/configuration identities are available.
- [ ] One canonical model and the stated feedforward, affine model, constraints, and checks are implemented.
- [ ] Hidden fault information and scoring truth remain outside controller inputs.
- [ ] Current/next references and H+1 endpoints are logged correctly.
- [ ] Ordered recovery scoring passes synthetic trace checks.
- [ ] Independent safeguard switches have targeted branch validation.
- [ ] Supervisor and transfer failures have been diagnosed on fixed development examples.
- [ ] Primary endpoints, tolerances, stopping rules, splits, and final trial counts are frozen.

### Minimum evidence before submission

- [ ] Hardware remains central, with physical fault definitions and all-attempt accounting.
- [ ] New comparisons identify the exact implemented controller and isolate their claimed differences.
- [ ] Constant-context and dynamic models use balanced training seeds in simulation.
- [ ] Primary effects include uncertainty and meaningful task outcomes, including failures.
- [ ] Complete latency and action-source attribution are reported.
- [ ] Every practical numerical recovery claim has a useful verified, calibration-accepted example; otherwise the claim is narrowed.
- [ ] Figures, equations, implemented methods, and conclusions agree.
- [ ] The manuscript meets the eight-page and anonymization requirements.

### Result-dependent decisions

| Final outcome | Appropriate paper decision |
|---|---|
| Dynamic context helps, behavioral loss does not | Retain the loss ablation as a negative result; do not advertise a demonstrated supervision benefit. Reassess novelty against context-conditioned dynamics work. |
| Behavioral supervision improves transfer but not in-distribution tracking | Report the tradeoff and absolute transfer competence, not just a relative gain within failed tracking. |
| Post-allocation decrease check remains inactive | Report its role and domain honestly; do not claim a measured performance benefit. Distinguish a verified implication from empirical inactivity. |
| MPC does not improve over matched fallback | Narrow the planning claim and explain what the architecture actually contributes. |
| Certificate remains empty or calibration rejects it | Retain the conditional theorem and failed search under their proper scope; do not claim numerically demonstrated recovery guarantees. |
| Hardware remains favorable but simulation differs | Investigate and state differences in controller, estimator, task, and fault population. Neither result automatically invalidates the other. |

The objective is a coherent, reproducible claim supported by physical outcomes and controlled simulation. Positive outcomes cannot be promised by the protocol, and negative findings should not be hidden to preserve a preferred contribution statement.

## Sources and version-specific references

- Reviewed manuscript: the attached nine-page `(3)(1).pdf`, especially Sections II–V, Table I, and Appendices I–III.
- [Reviewed repository](https://github.com/baaqerfarhat/Sc_sim_env/tree/81f52657c7d16d8377ac0812d13295410de377a7).
- [Results report](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/results/results.md).
- [Response identifying implemented and outstanding work](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/results/response_to_retention_plan.md).
- [Controller implementation](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/scsim/controllers.py).
- [Runner and reference logging](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/scsim/runner.py).
- [Method definitions and metric code](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/stage6_methods.py).
- [Stored comparison outcomes](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/results/stage6_methods.json).
- [Stored certificate search](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/results/stage7_certificate.json).
- [Stored horizon and transfer outcomes](https://github.com/baaqerfarhat/Sc_sim_env/blob/81f52657c7d16d8377ac0812d13295410de377a7/results/stage8_horizon.json).
- [RA-L author instructions](https://www.ieee-ras.org/publications/ra-l/ra-l-information-for-authors/) (checked during the manuscript review).
- [Learning Context-Aware Neural ODE Dynamics for Adaptive Robotic Control](https://arxiv.org/abs/2606.15469).

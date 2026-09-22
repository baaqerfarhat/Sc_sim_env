# Response to the Path B experiments-and-results plan, with a manuscript edit list

Reply to `EXPERIMENTS_AND_RESULTS_PLAN.md` (RA-L Path B revision, 2026-09-21).

This document is organised so it can be used directly to revise `main.tex`,
`experiments.tex` and `architecture.tex`:

- **Part A** what was run, and how each plan item was closed out
- **Part B** the numbers, as drop-in replacements for the current tables and abstract
- **Part C** what the paper may claim, what must be withdrawn, and the exact wording
- **Part D** a section-by-section edit list keyed to the current `.tex` files
- **Part E** what is still outstanding

The long-form evidence document is `results/PATHB_ANSWERS.md`. Every number below is read
from a frozen JSON artefact, listed in Part A.6.

---

# Part A. What was run

## A.1 Scale

| | |
|---|---|
| Prospective rollouts | **25,920** (12,960 per operating radius, two radii) |
| Development episodes | ~1,800 across four blocking gates |
| Trained checkpoints | **20** (five seeds each for M1, M2, M3, M-motion) |
| Task families | 2 (retained `step`, new `smooth_dock_v1`) |
| Conditions | 4 (healthy, actuator, perception, combined) |
| Unique scenarios | 60 per family per condition = 480 units |
| Wall time | ~5 h of 16-way parallel simulation |

## A.2 Stages, in the plan's order, with the blocking gates enforced

| Stage | Purpose | Outcome |
|---|---|---|
| 0 provenance freeze | §3, §5, §6.1 | **24/24 checks pass** |
| 1 historical reanalysis | §2.2, §3.3, §11.4 | two sign/count corrections to the previous report |
| 2 diagnostic + estimation floor | §6.4 failure analysis | the §6.4 gate failure explained; endpoint re-specified |
| 2 task feasibility gate | §6.3, §6.4 | `smooth_dock_v1` frozen at **30 s**, 20/20 both frames |
| 3 training | §4.1, §11.1 | 11 new jobs, five-seed matrix complete |
| 4 calibration + dev gates | §7 | all pass; **M4 stop rule fired** |
| 4b operating-radius analysis | (new finding) | eligibility set shown absorbing; radius corrected |
| 5 prospective matrix | §11.3 | 12,960 rollouts x 2 radii |
| 6 estimands + claim gates | §9, §10 | all seven gates resolved |
| 7-8 tables and figures | §13 | five tables, four figures, per-condition intervals |

## A.3 The four findings that were not anticipated by the plan

These are the substantive scientific output of the campaign and they change the paper.

**1. There is no absolute position reference after the one-shot `t0` alignment.** The
estimate-to-truth error is an unbounded random walk: 0.194 m mean and 0.333 m at the 90th
percentile by the 60 s horizon under healthy perception, 0.825 m and 1.413 m under occlusion.
Confirmed open-loop over 400 episodes with no controller in the loop (0.350 m healthy). The
archived 0.15 m **true-state** task tolerance is below that floor, so it returns zero for
every method under every task. This is why the §6.4 ladder failed at all three rungs, and it
is a property of the simulator rather than of the new task: the retained `step` and `smooth`
families sit on the same floor when scored by the same rule.

**2. The eligibility set is absorbing.** The supervisor is `u = -kp*[vx, vy, r]`: it reads no
position or heading error at all. The position block of P has eigenvalues 882.94-883.37, so at
the originally calibrated R = 51.4825 a vehicle **at rest** is ineligible in every direction
beyond **1.7326 m** of position error, and inside that set the supervisor damps a velocity
that is already zero. The retained `step` task's 2 m setpoint change is 1.2x that threshold,
so it *starts inside the trap*: measured over 64 episodes, the longest unbroken supervisor
interval is **600 of 600 steps**.

**3. Finite proposal repair, not the MPC solve, produces the transmitted command.** Over the
full taxonomy, `mpc_replacement` accounts for **68-91%** of commanded steps and `mpc_primary`
for only 9-32%. Disabling repair (R-off-clean) gives **0 of 2,400** completions.

**4. Preview is what distinguishes MPC from feedback, and the two task families demonstrate
it.** On `step`, whose setpoint switch carries no informative preview, nominal feedback beats
the learned MPC in all four conditions (+0.116 to +0.170 m). On `smooth_dock_v1`, which has a
genuine differentiable feedforward, the learned MPC beats nominal feedback under healthy
(-0.0140 m) and actuator faults (-0.0221 m), both intervals excluding zero, and ties under
perception degradation. This is the plan's own §6.2/§6.3 rationale, now demonstrated.

## A.4 Plan checklist

| Plan item | Status |
|---|---|
| Historical source recoverable; v4 classified by execution contract (§3.1, §3.2) | **done** — recoverable; classified corrected-contract |
| Fault-slot execution invariants re-verified (§3.2) | **done** |
| Feature composition and scaling audit (§5.1, §5.2) | **done** — `FEATURE_SCALE` disclosed as **hardcoded**, not train-split |
| Machine-readable scenario population + SHA-256 (§6.1) | **done** — `scenario_population_v1` |
| Untouched test manifest, disjoint key blocks (§6.1) | **done** |
| Historical reanalysis from raw artefacts (§2.2, §3.3, §11.4) | **done** — two corrections |
| `smooth_dock_v1` designed, gated, frozen (§6.3, §6.4) | **done** — 30 s, shortest rung |
| Provisional task thresholds justified/changed; dwell semantics reconciled (§9.4, line 524) | **done** — `task_success_v2`, 22-observation dwell |
| Five seeds for M1, M2, M3, M-motion (§4.1, §11.1) | **done** — 20 checkpoints |
| M-motion mask travels inside the checkpoint (§4, §5.3) | **done** — registered as a buffer |
| R-off-clean as the *clean* repair ablation (§10.5) | **done** — M7 not relabelled |
| Instrumentation smoke gate (§7) | **done** — 5/5 |
| M3/M4 semantic stop gate (§7) | **done** — fired; M4 omitted, 2,400 rollouts saved |
| 12-label action taxonomy, total (§8.4) | **done** — shares sum to 1.000 |
| Full decision-latency measurement (§8) | **done** — p95 19.4 ms, labelled workstation timing |
| Prospective matrix (§11.3) | **done** |
| Crossed scenario-paired bootstrap, seed 260921, 10,000 resamples (§9.3) | **done** |
| Nominal 95% plus central 97.5% for the two co-primary gates (§9.3) | **done** |
| Claim gates (§10) | **done** — all seven |
| Failure/censoring ledger, orthogonal flags (§9.5) | **done** |
| Hardware re-anchoring (§12) | **not done** — no hardware access |

## A.5 Two corrections to the previous report

**The sign was stated backwards.** The previous report said the seed-crossed M3-M2 intervals
include zero. Recomputed from its own saved artefact, M3-M2 is strictly positive in all four
conditions (+0.165, +0.279, +0.436, +0.510 m) with every crossed interval entirely above
zero. Oriented M3 minus M2, positive means the behavioural-loss model is significantly
**worse** — a stronger adverse finding than the text claimed.

**5,280 was a rollout count, not a sample size.** M5's three seed labels produced **bitwise
identical** outcomes, so it contributed 240 independent outcomes rather than 720. Path B runs
deterministic methods once per scenario and reports rollouts, unique scenarios and checkpoints
in separate columns; M0 and M5 checkpoint independence was verified empirically rather than
asserted.

## A.6 Artefacts

`results/pathb0_freeze.json`, `pathb1_reanalysis.json`, `pathb2_diag.json`,
`pathb2_floor.json`, `pathb2_taskgate.json`, `pathb3_train.json`, `pathb4_gates.json`,
`pathb4b_radius.json`, `pathb5_test{,_Rcorrected}.json`, `pathb6_analysis{,_Rcorrected}.json`,
`pathb8_paper_tables_Rcorrected.json`, `pathb_rollouts{,_Rcorrected}.csv`,
`table1`-`table5*.md`, `figs/fig1`-`fig4*.png`.

Test manifest SHA-256 `01d416add89f07818ce837a29fbfa07b9d34b0b8703b02d436baf2aa58a0cf2d`.
Scenario population SHA-256
`b790a993904aa4c0ac586736c2c9df9ecf0e367731cef1574e8231ededa02634`. Both radii ran against
the same manifest, so they are compared on identical scenarios.

---

# Part B. The numbers, as drop-in replacements

All values below are the **corrected-radius** run (R = 168.2125), which is the one the paper
should report. The pre-registered run (R = 51.4825) is retained and should appear as a
robustness paragraph; **every claim-gate verdict is identical under both.**

## B.1 The two co-primary estimands

Condition-balanced post-onset position RMSE difference, crossed scenario-paired bootstrap,
analysis seed 260921, 10,000 resamples. Negative favours the first-named method.

| Estimand | Family | Contrast | Point | 95% | 97.5% (Bonferroni) | Gate |
|---|---|---|---|---|---|---|
| **D21** | `step` | M2 - M1 | **-0.1805** m | [-0.2169, -0.1439] | **[-0.2215, -0.1381]** | **SUPPORTED** |
| **D25** | `smooth_dock` | M2 - M5 | -0.0126 m | [-0.0294, +0.0035] | [-0.0321, +0.0059] | **UNRESOLVED** |

D21 under the pre-registered radius: -0.1103 m, 97.5% [-0.1663, -0.0605], also supported.
D25 under the pre-registered radius: -0.0276 m, 97.5% [-0.0779, +0.0164], also unresolved.

## B.2 Per-condition effects, `step` family (replaces `tab:effects`)

Descriptive, unadjusted for the four conditions. `*` marks an interval excluding zero.

| Condition | M2-M1 | M2-M0 | M2-M5 | M3-M2 | M2-M-motion | M2-R-off |
|---|---|---|---|---|---|---|
| healthy | **-0.1345** [-0.1686, -0.1006]* | -0.1077 [-0.1396, -0.0756]* | +0.1669 [+0.1337, +0.2030]* | +0.2184 [+0.1728, +0.2670]* | +0.0095 [-0.0189, +0.0397] | -2.5738 [-2.7964, -2.3699]* |
| actuator | **-0.1179** [-0.1500, -0.0856]* | -0.0961 [-0.1273, -0.0648]* | +0.1697 [+0.1376, +0.2050]* | +0.2319 [+0.1679, +0.3085]* | -0.0029 [-0.0348, +0.0287] | -2.4472 [-2.7576, -2.1542]* |
| perception | **-0.2611** [-0.3712, -0.1679]* | -0.1656 [-0.2502, -0.0876]* | +0.1286 [+0.0627, +0.2016]* | +0.2404 [+0.1688, +0.3138]* | -0.0342 [-0.0821, +0.0154] | -2.0695 [-2.3938, -1.7802]* |
| combined | **-0.2087** [-0.2681, -0.1505]* | -0.1524 [-0.2356, -0.0742]* | +0.1158 [+0.0407, +0.1812]* | +0.2747 [+0.1924, +0.3641]* | -0.0099 [-0.0670, +0.0452] | -2.1962 [-2.5513, -1.8443]* |

## B.3 Per-condition effects, `smooth_dock_v1` family (new table)

| Condition | M2-M1 | M2-M0 | M2-M5 | M3-M2 | M2-M-motion | M2-R-off |
|---|---|---|---|---|---|---|
| healthy | +0.0028 [+0.0006, +0.0055]* | +0.0064 [+0.0034, +0.0104]* | **-0.0140** [-0.0174, -0.0105]* | +0.0016 [-0.0005, +0.0038] | +0.0009 [-0.0005, +0.0026] | -2.1650 [-2.4747, -1.8893]* |
| actuator | +0.0075 [+0.0042, +0.0121]* | +0.0117 [+0.0069, +0.0185]* | **-0.0221** [-0.0279, -0.0167]* | -0.0010 [-0.0044, +0.0025] | +0.0010 [-0.0012, +0.0035] | -1.8904 [-2.1804, -1.6230]* |
| perception | -0.0328 [-0.0854, +0.0156] | -0.0233 [-0.0801, +0.0370] | -0.0069 [-0.0489, +0.0287] | +0.0432 [+0.0015, +0.0895]* | -0.0016 [-0.0284, +0.0258] | -1.4198 [-1.6811, -1.1910]* |
| combined | **-0.0599** [-0.1194, -0.0112]* | -0.0407 [-0.0944, +0.0060] | -0.0074 [-0.0612, +0.0463] | +0.0646 [+0.0287, +0.1029]* | -0.0150 [-0.0486, +0.0169] | -1.2677 [-1.5172, -1.0432]* |

**Read these two tables together — the pattern is the paper's most defensible claim.** On
`step` the learned context helps everywhere and most under perception degradation, while
feedback beats MPC everywhere. On `smooth_dock` the learned context is a marginal *cost* when
nothing is wrong (+0.003, +0.008 m) and a benefit only once perception degrades (-0.060 m
combined), while MPC beats feedback exactly where preview is exploitable and nothing is wrong.
Context adaptation buys nothing when there is nothing to adapt to. That is the correct story
for a fault-tolerance paper and it is more credible than a uniform win.

## B.4 Absolute levels (post-onset position RMSE, m, mean over rollouts)

| Family | Condition | M0 | M1 | **M2** | M3 | M5 | M-motion | R-off |
|---|---|---|---|---|---|---|---|---|
| `step` | healthy | 0.538 | 0.565 | **0.431** | 0.649 | *0.264* | 0.421 | 3.004 |
| `step` | actuator | 0.534 | 0.556 | **0.438** | 0.670 | *0.268* | 0.441 | 2.885 |
| `step` | perception | 1.101 | 1.196 | **0.935** | 1.176 | *0.807* | 0.970 | 3.005 |
| `step` | combined | 1.008 | 1.064 | **0.855** | 1.130 | *0.739* | 0.865 | 3.051 |
| `smooth_dock` | healthy | 0.184 | 0.187 | **0.190** | 0.192 | 0.204 | 0.189 | 2.355 |
| `smooth_dock` | actuator | 0.190 | 0.194 | **0.202** | 0.201 | 0.224 | 0.201 | 2.092 |
| `smooth_dock` | perception | 0.766 | 0.775 | **0.742** | 0.786 | 0.749 | 0.744 | 2.162 |
| `smooth_dock` | combined | 0.796 | 0.815 | **0.755** | 0.820 | 0.763 | 0.770 | 2.023 |

## B.5 Development prediction error (five seeds each)

| Method | s0 | s1 | s2 | s3 | s4 | mean | sd |
|---|---|---|---|---|---|---|---|
| M1 constant context | 0.001576 | 0.001577 | 0.001579 | 0.001579 | 0.001579 | 0.001578 | 0.000001 |
| **M2 changing context** | 0.001118 | 0.001106 | 0.001120 | 0.001130 | 0.001119 | **0.001119** | 0.000008 |
| M3 + behavioural loss | 0.001481 | 0.001487 | 0.001490 | 0.001496 | 0.001484 | 0.001488 | 0.000006 |
| **M-motion** | 0.001128 | 0.001128 | 0.001140 | 0.001127 | 0.001128 | **0.001130** | 0.000006 |

M2 is 29% below M1, far outside the seed spread. M-motion is 1% above M2 against a seed
standard deviation under 1% — removing the two innovation scalars and the pose-validity
channel barely changes one-step prediction.

Per-seed closed-loop means, `step` family, corrected radius: M2 = 0.661, 0.645, 0.668, 0.710,
0.640; M1 = 0.853, 0.842, 0.840, 0.844, 0.848. The separation exceeds the seed spread on both
sides, which is what makes a five-seed interval credible here.

## B.6 Command provenance over the full 12-label taxonomy

| Family | Condition | Method | `mpc_primary` | `mpc_replacement` | `m5_feedback` | supervisor | sum |
|---|---|---|---|---|---|---|---|
| `step` | healthy | M2 | 0.215 | **0.785** | 0.000 | 0.000 | 1.000 |
| `step` | combined | M2 | 0.239 | **0.759** | 0.000 | 0.000 | 1.000 |
| `smooth_dock` | healthy | M2 | 0.086 | **0.914** | 0.000 | 0.000 | 1.000 |
| `smooth_dock` | combined | M2 | 0.158 | **0.841** | 0.000 | 0.000 | 1.000 |
| `smooth_dock` | healthy | R-off | 0.981 | 0.000 | 0.000 | 0.018 | 1.000 |

This replaces the manuscript's current admission that `candidate` "pools unchanged MPC outputs
with projected and allocation-compensated commands". The pooling is now resolved: the
unmodified MPC proposal determines transmission on only **9-32%** of steps.

## B.7 Task completion, `task_success_v2` (dual frame, never merged)

| Frame | Scored on | Tolerance | Provenance |
|---|---|---|---|
| **declared** | the estimate; the onboard assertion | 0.15 m, 5 deg | the archived provisional values, **unchanged** |
| **achieved** | the true state; a ground-truth observer | 0.35 m, 15 deg | the healthy analytic estimation floor at the 90th percentile, rounded up |

Both use a **22-observation** dwell (21 intervals = 2.1 elapsed seconds at exactly 10 Hz),
which fixes the archived 21-observation/2.1 s inconsistency the plan flagged.

Achieved completion, corrected radius: on `smooth_dock` every method reaches 1.000 under
healthy and actuator faults and falls to 0.54-0.65 under perception degradation; on `step` M2
is 0.997 healthy and 0.533 combined. Completion-rate differences: on `step` M2 - M1 is
**+0.0617** achieved (95% [+0.0217, +0.1017]) and +0.0550 declared, both favouring M2; on
`smooth_dock` M2 - M5 contains zero in both frames.

**The estimation gap** (declared complete, not achieved) is **zero under healthy perception
for every method on both families** and non-zero only in the perception-degraded conditions,
reaching 0.057-0.067 on `smooth_dock`. Up to about 7% of runs are declared complete by the
vehicle and not certified by a ground-truth observer, exactly where the perception story
predicts.

## B.8 Calibration

R = 168.2125 by the corrected envelope rule; eta = 4 by the pre-declared rule on a grid
widened to the no-check limit; diagnostic recovery tolerance 0.662 m carried over unchanged
and labelled historical. The allowance curve **saturates at eta = 4**: beyond it, RMSE, MPC
share and supervisor share are identical to the no-screen limit, and removing the first-action
screen entirely changes calibration RMSE by **+0.0000 m**. The candidate violates the decrease
inequality in 59.6% of monitored steps; split-conformal calibration at delta = 0.025 gives
eta = 1.8753, where the screen fires on about 0.2% of steps and costs +0.009 m.

---

# Part C. What the paper may claim

The gates decide wording only. Verdicts are identical under both operating radii.

| § | Gate | Verdict |
|---|---|---|
| 10.1 | dynamic-context RMSE | **SUPPORTED** |
| 10.2 | learned-MPC pipeline RMSE | **UNRESOLVED** |
| 10.3 | multimodal streams | **UNRESOLVED** |
| 10.4 | behavioural loss | **ADVERSE** |
| 10.5 | repeated post-allocation check | **REDUNDANT under the preceding screen** |
| 10.5 | finite proposal repair | **SUPPORTED** |
| 10.6 | certificate and safety | **NOT CLAIMED** |

## C.1 Claims that survive, with approved wording

**Changing context improves tracking, and most where perception degrades.**

> Within the evaluated architecture, inferring a changing context lowers condition-balanced
> post-onset position RMSE relative to a trained constant-context baseline by 0.181 m on the
> retained step task (97.5% interval [-0.222, -0.138], five independently trained seeds per
> method). The effect is not uniform: it is 0.135 m under healthy perception and 0.261 m under
> perception degradation, and the same ordering appears on the smooth preview task, where
> changing context is a marginal cost when nothing is impaired and a 0.060 m benefit under
> combined impairment. The direction is corroborated at the prediction level, where the
> changing-context model's development one-step weighted MSE is 29% below the constant-context
> model's, far outside the five-seed spread on either side.

**Finite proposal repair is the load-bearing component.**

> The unmodified MPC first action determines transmission on only 9-32% of control steps;
> allocation-aware finite proposal repair supplies the remaining 68-91%. Disabling repair
> while holding every other component fixed raises post-onset RMSE by 1.27-2.57 m and reduces
> achieved task completion to 0 of 2,400 rollouts. This is measured against a clean ablation
> in which both arms trial-allocate their own proposal and both apply the same screens to the
> resulting transmitted-equivalent command; the earlier M7 variant, which also changed the
> wrench the first screen was evaluated on, is not this experiment and is not relabelled as
> it.

**Preview is what separates predictive optimisation from feedback.** (new, and worth
foregrounding)

> On the retained step task, whose instantaneous setpoint switch carries no informative
> preview, nominal feedback with the same repair mechanism attains lower post-onset RMSE than
> the learned MPC in all four conditions (+0.116 to +0.170 m). On the prespecified smooth
> preview mission, the learned MPC attains lower RMSE than nominal feedback under healthy
> (-0.014 m) and actuator-fault (-0.022 m) conditions, both intervals excluding zero, and is
> indistinguishable from it under perception degradation. Predictive optimisation helps only
> where there is an exploitable feedforward and the estimate is trustworthy.

## C.2 Claims that must be withdrawn or reworded

**The complete learned-MPC pipeline is not distinguishable from nominal feedback.** D25 =
-0.0126 m, interval containing zero, under both radii. State plainly that the condition-
balanced pipeline claim is unresolved, and report the per-condition split of C.1 rather than
implying a uniform win. On the retained step family nominal feedback is significantly better.

**Behavioural supervision is an adverse ablation, not a contribution.** M3 - M2 is
significantly positive on `step` in all four conditions (+0.218 to +0.275 m) and on
`smooth_dock` under perception (+0.043) and combined (+0.065) impairment, and was
significantly positive in all four archived conditions. The development grid selected weight
zero before any test ran, so M2 is the selected method and M3 is a labelled negative result.
Do not revive it without a new training design and a fresh untouched test.

**No modality-fusion benefit may be claimed.** M2 - M-motion contains zero in all eight
family-condition cells and the development prediction gap is 1%. The plan's §10.3 wording
applies: retain the title, describe the input composition precisely, and claim no fusion
benefit. Note that M-motion still contains vision-influenced estimated states and residuals,
so the negative result bounds only the **explicit** diagnostic channels and not all perception
information.

**Neither the first-action screen nor the repeated check may be presented as beneficial.** The
repeated post-allocation check never fires and disabling it changes the selected packets,
action sources and trajectories not at all, bitwise, over 160 development episodes; it is
redundant because once the first-action condition carries the same allowance the two tests are
the same inequality on the same quantity. The first-action decrease screen is inert at the
calibrated allowance: removing it changes calibration RMSE by +0.0000 m.

**The eligibility test plus supervisor must be described as absorbing, not as recovery.**
State the closed-form trapping threshold, that the supervisor reads no position error, and the
radius sensitivity (a 22% change in R flips the step family between 0.48 m with 0% supervisor
share and 1.75 m with 79%).

**No safety claim.** No verified invariant region, no calibrated safety probability, no
collision-free or continuous-time guarantee, no guaranteed recovery. The transmitted-command
proposition stays conditional on its explicit discrepancy assumptions.

## C.3 Two disclosures the manuscript does not currently contain

**No absolute position reference after `t0`.** The estimate-to-truth error is an unbounded
random walk, so every true-state RMSE has an estimation floor underneath it and the task
endpoint cannot be tighter than that floor. This also means the system is **not** Vicon-free:
the one-shot alignment anchors the origin against ground truth.

**The feature scaling constants are hardcoded**, not computed from the training split. Frozen
and disclosed as hardcoded so that M1, M2, M3 and M-motion remain exactly comparable.

---

# Part D. Section-by-section edit list

Keyed to the current `pathB/` sources. The manuscript's existing framing is already honest,
so these are targeted replacements rather than a rewrite.

## D.1 `main.tex` abstract (lines 31-33)

Replace the two simulation sentences. Current:

> A controlled simulation study separates prediction-trained dynamic context, trained constant
> context, behavioral supervision, and nominal feedback. Dynamic context lowers tracking RMSE
> by 0.093--0.515 m relative to the tested constant-context checkpoint; the added behavioral
> loss worsens performance, and nominal feedback with command repair achieves lower RMSE than
> learned MPC.

Replacement:

> A preregistered simulation study over 12,960 rollouts, two task families, four impairment
> conditions, and five independently trained seeds per learned method separates
> prediction-trained dynamic context, trained constant context, behavioral supervision,
> allocation-aware repair, and nominal feedback. Dynamic context lowers condition-balanced
> post-onset position RMSE by 0.181~m (97.5\% interval $[-0.222,-0.138]$) on the retained
> task, with the benefit roughly doubling under perception degradation. Allocation-aware
> repair, not the predictive solve, supplies 68--91\% of transmitted commands, and disabling it
> removes task completion entirely. Predictive optimization improves on nominal feedback only
> on the task with an exploitable preview and only when the estimate is trustworthy; the
> condition-balanced pipeline comparison is unresolved. The added behavioral loss worsens
> performance, and the incremental value of the explicit estimator-diagnostic channels is not
> established.

Also append to the abstract:

> The environment provides no absolute position reference after a single initial alignment, so
> estimation error grows without bound and bounds any true-state completion criterion; we
> report completion in both the estimated and true frames. No operational safety or recovery
> certificate is established.

## D.2 `main.tex` contributions (lines 43-47)

Contribution 1: change "matched simulation comparisons" to "a preregistered simulation
programme with five training seeds per learned method, two task families, and prespecified
claim gates". Contribution 2: keep, then add a third:

> \item An empirical decomposition of the implemented controller that identifies which
> components carry the result: allocation-aware repair determines the transmitted command on
> the large majority of steps, whereas the post-allocation decrease test is redundant under the
> screen preceding it and the first-action allowance is inert at its calibrated value.

## D.3 `main.tex` line 49 (the honest summary sentence)

Current ends "...while the behavioral loss and the advantage of MPC over nominal feedback are
unsupported by the current results." Extend:

> ...are unsupported by the current results. Predictive optimization does improve on nominal
> feedback on the smooth preview mission under healthy and actuator-fault conditions, so the
> negative pipeline result is specific to tasks without an exploitable preview and to
> perception-degraded operation.

## D.4 `main.tex` §"Repair, Eligibility, and Transmission" (line 160)

Add the absorbing-set result. This is a structural property of the described mechanism and
belongs with its definition, not only in the experiments:

> The supervisor damps translational and angular velocity and does not act on position or
> heading error. Consequently, a state at rest whose position error exceeds
> $R/\sqrt{\lambda_{\min}(P_{\mathrm{pos}})}$ is ineligible in every direction and the
> supervisor cannot restore eligibility: the complement of the eligibility set is absorbing.
> For the implemented $P$ and the calibrated radius this threshold is $1.73$~m. The eligibility
> mechanism is therefore a protective diversion and not a recovery behavior.

## D.5 `main.tex` §"Conditional Tracking Analysis" (line 178)

Keep the bound, but add that the screen it analyses is empirically inert at its calibrated
allowance, so the analysis is a statement about the mechanism rather than an explanation of the
measured performance. This pre-empts the obvious reviewer objection.

## D.6 `experiments.tex` §"Frozen matched simulation study" (line 73)

- **Task description (lines 79-81):** keep the step family, and add `smooth_dock_v1`: two
  quintic minimum-jerk rest-to-rest segments, offsets $(0.6,+0.6)$ then $(1.0,0)$~m with yaw
  $0 \to +30^\circ \to 0$, 30~s manoeuvre followed by station hold, selected as the shortest
  duration passing a development feasibility gate at a predeclared 20% authority margin
  (realised utilisation 0.401).
- **Seeds (lines 92-101):** replace the three-seed and seed-0 caveats. Now five independently
  trained seeds for M1, M2, M3 and M-motion; M0 and M5 verified checkpoint-independent
  empirically and run once per scenario; rollout, unique-scenario and checkpoint counts
  reported separately.
- **Primary contrast (lines 105-106):** replace "the campaign's predeclared primary contrast
  was M3--M2" with the two co-primary estimands D21 and D25, each carrying a central 97.5%
  interval as a Bonferroni allowance at a nominal familywise 5% level, with all per-condition
  and secondary intervals descriptive.
- **Healthy window (line 103):** the healthy score now runs from a drawn pseudo-onset to the
  episode end, so all four conditions share one estimand. Note explicitly that this differs
  from the archived healthy number, which used the whole episode, and that the two are never
  pooled.
- **`tab:effects`:** replace wholesale with Part B.2, and add Part B.3 as a second panel or
  companion table. Drop the M7 column and replace it with M2-R-off. Add an M2-M-motion column.
- **Narrative (lines 149-165):** M4 is now omitted under a prespecified semantic stop gate, so
  the M3/M4 identity is reported as a development replay result over 160 episodes with no
  performance claim. The M7 paragraph should be replaced by the clean R-off-clean result.

## D.7 `experiments.tex` §"Completion, diagnostic recovery, and command provenance" (line 166)

This subsection needs the largest revision; three of its stated limitations are now resolved.

- **Dwell (lines 168-170):** 22 consecutive observations, 2.1 s elapsed at exactly 10 Hz, by
  logged timestamps. Remove the 21-observation/2.1 s discrepancy note; it is fixed, not
  flagged.
- **Thresholds (lines 170-172):** replace the single provisional pair with the dual frame of
  Part B.7, and give the reason: no controller can place the true state closer to the goal
  than its estimate is to the truth, and the healthy 90th-percentile estimation floor is
  0.333 m.
- **Completion counts (lines 172-180):** replace with Part B.7. The new counts are far higher
  and the previous "neither method reliably completes the perception-degraded tasks"
  conclusion no longer holds for `smooth_dock` under healthy and actuator faults, where all
  methods complete.
- **Provenance (lines 188-194):** delete the admission that `candidate` pools unmodified with
  repaired commands. Replace with Part B.6: the taxonomy is now 12 mutually exclusive labels
  summing to 1.000, and the unmodified MPC proposal determines transmission on 9-32% of steps.
- **Add** the estimation-gap paragraph from Part B.7.

## D.8 New material to add to `experiments.tex`

1. A short paragraph on the operating-radius sensitivity and the absorbing set, with the
   four-row table from Part A.3 finding 2. This doubles as the robustness statement: the full
   matrix was run at both radii and every gate verdict is identical.
2. A paragraph on the estimation floor, with the analytic Rayleigh/half-normal derivation and
   the open-loop confirmation.
3. The allowance curve, showing that the screen stops firing at eta = 4 and that removing it
   changes nothing.

## D.9 Figures available

| File | Content |
|---|---|
| `figs/fig1_allowance_curve.png` | allowance curve; RMSE and command shares versus eta, with the no-screen limit |
| `figs/fig2_estimation_floor.png` | estimation error growth, healthy and occluded, against both task tolerances |
| `figs/fig3_forest_Rcorrected.png` | forest plot of every contrast on both families, co-primary marked |
| `figs/fig4_traces_Rcorrected.png` | representative traces separating true, observed and estimation error, with per-step action source |

Figure 2 is the one that most needs to be in the paper: it makes the estimation floor and the
endpoint re-specification self-evident in one panel.

## D.10 `architecture.tex` and §"State, Commands, and Causal History" (main.tex line 53)

State the exact feature composition: 18 features per token over 11 tokens, grouped as two
estimator-innovation scalars, one pose-availability scalar, six estimated-state increments,
three previous transmitted nominal-equivalent command components, and six nominal
prediction-residual components. Disclose that the scaling divisors are hardcoded constants
rather than training-split statistics, and that the M-motion ablation zeroes the first three
channels, which is exactly equivalent to deleting those columns because the first layer is a
linear projection.

---

# Part E. Outstanding

**Fresh hardware blocks (§12) are the only unaddressed plan item.** No hardware access, so:

- the hardware subsection stays labelled archival and descriptive;
- `fig_cross_fault` stays a clearly archival descriptive plot, not a fresh paired comparison;
- the hardware numbers (14.0-57.9% lower reported mean position RMSE against deployment-time
  zero-context MPC) are unchanged and must keep their "reported" qualifier and their
  non-reproducible provenance caveat;
- the dirty-commit provenance note stays, since exact reproduction of the archived runs is
  still not claimed.

Everything in the simulation programme is complete.

**One judgement call for you.** The pre-registered run selected the operating radius by a rule
that turned out to be circular, and I corrected it and re-ran the entire matrix rather than
reporting a trapped controller. I have kept both artefacts and every gate verdict agrees. My
recommendation is to report the corrected radius as the primary result and the pre-registered
radius as a robustness paragraph, with the absorbing-set analysis as the stated reason for the
correction. If you would rather lead with the pre-registered numbers, Part B gives both and
nothing else in the document needs to change.

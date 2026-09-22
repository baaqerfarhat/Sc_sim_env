# Path B: what was run, what it found, and what the manuscript may now claim

Reply to `EXPERIMENTS_AND_RESULTS_PLAN.md` (RA-L Path B revision, 2026-09-21).

Everything below was produced by the seven staged scripts `pathb0_freeze.py` through
`pathb7_report.py`. Each stage writes a JSON artefact, each table and figure is generated
from those artefacts and never from a recomputation, and the stages were run in the plan's
order with the blocking gates enforced. Artefact paths are given so every number can be
checked at source.

---

## 0. Headline

Four things happened that change the paper.

1. **The plan's Section 6.4 gate failed at every rung, and the reason was not the task.**
   It exposed a load-bearing property of the simulator that had never been written down:
   the closed loop has **no absolute position reference after the one-shot `t0` alignment**,
   so the estimate-to-truth error is an unbounded random walk. By the 60 s episode end it
   is 0.19 m on average under healthy perception and 0.83 m under occlusion. The archived
   task tolerance of 0.15 m on the **true** state is therefore below the estimation floor
   and is unreachable for *every* method under *every* task. The endpoint had to be
   re-specified before any test could mean anything.

2. **Three of the mechanisms the manuscript presents as contributions are not load-bearing**,
   and this campaign shows it with bitwise evidence rather than with a weak interval: the
   repeated post-allocation check never fires, the first-action decrease screen is inert at
   the calibrated allowance, and the behavioural loss makes tracking significantly worse.

3. **The mechanism that *is* load-bearing is not the one the title emphasises.** The
   eligibility test and its supervisor divert about 40% of all commanded steps, and that
   share is unchanged by removing the decrease screen entirely.

4. The reanalysis of the archive found that the previous report **misdescribed the sign of
   its own result** on the behavioural loss, in the direction unfavourable to the
   manuscript, and inflated its sample size by reporting rollouts as replicates.

Detail, evidence and the resulting claim wording follow.

---

## 1. Priority 0: scope and provenance freeze

`pathb0_freeze.py` -> `results/pathb0_freeze.json`

The plan makes this blocking, so it ran first and nothing downstream started until it
passed. **24 of 24 checks pass.**

| Requirement (plan section) | Result |
|---|---|
| Historical source recoverable (§3.1) | The dirty patch is recoverable; the exact source for the archived runs can be reconstructed |
| v4 artefacts classified by execution contract (§3.2) | Classified **corrected-contract**: the hidden fault is applied in the plant slot only |
| Fault-slot execution invariants (§3.2) | Re-verified: the hidden fault is never visible to any encoder input, the physical successor does change, the true yaw rotates the applied force, the estimate cannot touch physics |
| Feature composition audit (§5.1) | The 18-feature, 11-token causal history is enumerated per group in `scsim/scenarios.py:FEATURE_GROUPS`; the manuscript may not describe a stream the code does not carry |
| Scaling audit (§5.2) | `FEATURE_SCALE` is **hardcoded**, *not* computed from the training split. Disclosed as hardcoded rather than quietly corrected, because changing it would be a new pipeline version requiring every learned method to be retrained |
| Machine-readable scenario population (§6.1) | `scenario_population_v1` exported with every support, unit, draw order and condition override, SHA-256 `b790a993904aa4c0…` |
| Untouched test manifest (§6.1) | Generated and hashed; disjoint key blocks for feasibility, smoke, stop-gate, calibration and test |

Two disclosures matter more than the pass itself.

**The scenario seeding was not reproducible across runs and now is.** The generator was
keyed on Python's builtin `hash()`, which is salted per interpreter, so scenarios matched
*within* a run but differed on a rerun at identical seeds. It is now keyed on
`zlib.crc32`. This is recorded in the population manifest rather than silently fixed.

**The initial state is not random.** `x0 = 0` exactly in the primary study, so it
contributes no variance and must not be described as a draw.

---

## 2. Priority 1: historical reanalysis

`pathb1_reanalysis.py` -> `results/pathb1_reanalysis.json`

Recomputed from the 5,280 archived rollouts. These rows are **historical motivation and are
never pooled with the new campaign.** Two findings are corrections to the previous report,
not refinements of it.

### 2.1 The previous report had the sign of its own result backwards

It stated that the seed-crossed M3-M2 intervals include zero. Recomputed from the saved
intervals, M3-M2 is **strictly positive in all four conditions** (healthy +0.165,
actuator +0.279, perception +0.436, combined +0.510 m), with every crossed interval entirely
above zero. Because the contrast is oriented M3 minus M2, strictly positive means the
behavioural-loss model is significantly **worse**. The true finding is a *stronger* adverse
result than the text claimed, not a weaker one.

### 2.2 The 5,280 figure is a rollout count, not a sample size

| Method | Rollouts | Unique scenario outcomes | Inflation | Bitwise identical across seed labels |
|---|---|---|---|---|
| M5 fallback_only | 720 | 240 | x3.0 | **yes** |
| M3, M4, M7, M2, M8 | 720 each | 240 each | x3.0 | no |
| M0, M1, M6, HW | 240 each | 240 each | x1.0 | — |

M5 is deterministic: three seed labels produced **bitwise identical** outcomes, so it
contributed 240 independent outcomes and not 720. Path B runs deterministic methods once per
scenario and reports rollouts, unique scenarios and checkpoints in separate columns.

### 2.3 The archived M2-M1 comparison carried no M1 training variability

Stage 5 trained constant-context seeds 0, 1, 2 but Stage 6 evaluated only seed 0, so the
headline M2-M1 contrast rested on a **single** M1 checkpoint against three M2 checkpoints.
Path B evaluates five seeds on both sides.

### 2.4 The post-allocation check was never load-bearing

Recomputed M3-M4 post-onset RMSE differences are **exactly zero in all four conditions**,
with an enabled-check rejection rate of 0.0000. The reason is structural rather than
statistical: once the first-action condition carries the same allowance, the two tests are
the same inequality on the same quantity, so a candidate that passes the first cannot fail
the second.

### 2.5 Terminology is now fixed and used consistently

The archive used "first screen", "repeated check", "projection" and "repair"
interchangeably. They are now distinct: **first screen** is the Eq. (15) first-action
decrease condition on the transmitted nominal-equivalent command; **repeated decrease
check** is the Eq. (18) post-allocation test on the same quantity; **finite proposal
repair** is the bounded search over four proposal seeds plus one Newton step on the
allocation map; **continuous projection** and **allocation compensation** are *components*
of repair, not synonyms for it; **operational eligibility** is the pre-action radius and
passing-fallback test; the **supervisor** is a fixed damping controller and *not* a safety
guarantee.

Preserved as stated: lambda_I = 0 was selected on the development split, seed 0, before any
test run.

---

## 3. The estimation floor: the finding that forced a re-specification

`pathb2_diag.py`, `pathb2_floor.py` -> `results/pathb2_diag.json`,
`results/pathb2_floor.json`

### 3.1 How it surfaced

The Section 6.4 feasibility gate for `smooth_dock_v1` failed at 30 s, 40 s and 50 s. The
failure signature ruled out the obvious explanations immediately: the **final position error
was 0.196 m at 30 s and 0.194 m at 50 s**. An error that does not care how long the
manoeuvre took is not a bandwidth limit. Analytic wrench utilisation at the worst rung was
0.40 against the predeclared 0.80 cap, so authority was not binding either.

Decomposing the error settled it. In the tail of a healthy episode:

| Quantity | Position | Heading |
|---|---|---|
| truth to reference | 0.280 m | -9.1 deg |
| **estimate to reference** | **0.031 m** | **+0.9 deg** |
| estimate to truth | 0.280 m | +10.0 deg |

The controller was converging to 3 cm and 0.9 degrees in the only frame it can see. The
truth was 0.28 m away because *the estimate* was 0.28 m away from the truth. The retained
`step` and `smooth` families sat on the same floor when scored by the same rule, so nothing
about this was specific to the new task.

### 3.2 Why it happens, and that it is intended

`scsim/estimator.py` says so in its own docstring: *"This is deliberately NOT a good
estimator"* and *"No absolute reference after initialisation."* The VO surrogate is aligned
to ground truth once at `t0` and never again, and its position and heading biases are then
driftless random walks with no observation to anchor them. There is no absolute position
sensor anywhere in the loop.

The consequence is a floor that can be written down in closed form. Each axis of the
position bias is `N(0, bias_rw^2 t)`, so the error magnitude is Rayleigh with scale
`bias_rw*sqrt(t)`; the heading bias is the same construction in one dimension, so its
magnitude is half-normal.

| Perception | `bias_rw` | sigma per axis at 60 s | mean error | 90th pct | Heading 90th pct |
|---|---|---|---|---|---|
| healthy | 0.020 m/sqrt(s) | 0.155 m | 0.194 m | **0.333 m** | **11.7 deg** |
| occluded | 0.085 m/sqrt(s) | 0.658 m | 0.825 m | 1.413 m | 21.9 deg |

Confirmed **open loop**, with no controller and no policy in the loop and the truth held at
rest, over 400 episodes of the deployed estimator stack: healthy 0.350 m and 13.3 deg at the
same quantile. The measured value exceeds the analytic one because the analytic form
deliberately omits the measurement noise and the monocular scale error, which makes it a
conservative lower bound on the floor.

### 3.3 Why this invalidates the archived endpoint

**A controller cannot place the true state closer to the goal than its estimate is to the
truth.** The archived 0.15 m true-state tolerance is below the healthy floor of 0.333 m.
Applied to the true state it returns zero for every method under every task, so it is not a
discriminator, it is a constant. That, and not the choice of task, is why the Section 6.4
ladder could not be passed.

### 3.4 `task_success_v2`

Plan line 524 permits exactly this remedy: the provisional thresholds may be changed using
development evidence only, before the test manifest is generated, after which the scorer is
versioned and frozen. The replacement keeps both frames rather than choosing one.

| Frame | Scored on | Tolerance | Where the numbers come from |
|---|---|---|---|
| **declared** | the estimate; the onboard assertion | 0.15 m, 5 deg | the archived provisional values, retained **unchanged** |
| **achieved** | the true state; a ground-truth observer | 0.35 m, 15 deg | the healthy analytic floor at the 90th percentile, rounded up |

Both use the 22-observation dwell (21 intervals = 2.1 elapsed seconds at exactly 10 Hz),
which resolves the plan's Section 9.4 complaint that the archived 21-observation
implementation spans 2.0 s and was nonetheless labelled 2.1 s. The endpoint is never
reported under both dwell conventions.

The quantile and the horizon were declared before any number was computed. The `achieved`
thresholds depend only on frozen constants, so they are reproducible without running
anything, and neither pair moves now that test outcomes have been seen.

**This is not a weakening of the endpoint.** The gap between the two frames is itself a
result, and for a paper about perception faults it is the interesting one: it measures how
often a method believes it has docked when it has not. Section 7.4 reports it per condition.

### 3.5 The gate, re-run

With the versioned scorer, `smooth_dock_v1` passes at the **shortest** rung.

| Duration | Continuity at the join | Utilisation (cap 0.80) | Declared completions | Achieved completions |
|---|---|---|---|---|
| **30 s** | 1.8e-09 | 0.401 | **20/20** | **20/20** |

30 s is frozen into `scsim/reference.py` so no later stage can differ from it. 20
development episodes were spent. The task is frozen; no test outcome was inspected at any
point during the ladder.

---

## 4. Training: the full five-seed matrix

`pathb3_train.py` -> `results/pathb3_train.json`

Eleven new jobs completed in 28 minutes, giving 20 checkpoints: five independently trained
seeds for each of M1, M2, M3 and M-motion. Development one-step weighted MSE:

| Method | s0 | s1 | s2 | s3 | s4 | mean | sd |
|---|---|---|---|---|---|---|---|
| M1 constant context | 0.001576 | 0.001577 | 0.001579 | 0.001579 | 0.001579 | 0.001578 | 0.000001 |
| **M2 changing context** | 0.001118 | 0.001106 | 0.001120 | 0.001130 | 0.001119 | **0.001119** | 0.000008 |
| M3 + behavioural loss | 0.001481 | 0.001487 | 0.001490 | 0.001496 | 0.001484 | 0.001488 | 0.000006 |
| **M-motion** | 0.001128 | 0.001128 | 0.001140 | 0.001127 | 0.001128 | **0.001130** | 0.000006 |

Two things are already visible at the prediction level, before any controller runs.

**Changing context is doing real work as a predictor**: M2 is 29% below M1, far outside the
seed spread.

**The explicit estimator-diagnostic channels contribute almost nothing to prediction**:
M-motion is 0.001130 against M2's 0.001119, a 1% gap against a seed standard deviation of
0.000006-0.000008. Removing the two innovation scalars and the pose-validity channel
barely changes one-step prediction. This is the first evidence bearing on the plan's
Section 10.3 modality claim, and it points the wrong way for the title.

The M-motion mask is registered as a **buffer inside the checkpoint**, so a model trained
without the diagnostic channels cannot be silently deployed with them.

---

## 5. Priority 2: calibration and the development gates

`pathb4_gates.py` -> `results/pathb4_gates.json`

1,058 development episodes. All gates pass.

### 5.1 The allowance curve, and the first-action screen being inert

Calibration ran in **monitor** mode on the disjoint `calibration` key block, then froze.
The eligibility radius is the 95th percentile of `||e||_P` over 120,000 transitions,
R = 51.4825. The candidate violates the decrease inequality in **59.6%** of monitored
steps, and split-conformal calibration at delta = 0.025 would give eta = 1.875.

The declared selection rule was "minimise calibration post-onset RMSE on a fixed grid". The
grid initially stopped at the archived eta = 2 and selected it — but that is a **boundary**
solution, which means the rule had not selected anything, it had run out of grid. The ladder
was widened to the no-check limit before any test episode, because a grid too narrow to let
an adverse answer appear is not a test:

| eta | post-onset RMSE (m) | MPC share | supervisor share |
|---|---|---|---|
| 0 | 1.9115 | 0.132 | 0.868 |
| 0.5 | 1.2250 | 0.483 | 0.516 |
| 1 | 1.1968 | 0.543 | 0.456 |
| 1.875 (conformal) | 1.1396 | 0.593 | 0.406 |
| 2 (archived) | 1.1337 | 0.598 | 0.402 |
| **4 (selected)** | **1.1246** | **0.600** | **0.400** |
| 8 | 1.1246 | 0.600 | 0.400 |
| 16 | 1.1246 | 0.600 | 0.400 |
| 64 | 1.1246 | 0.600 | 0.400 |
| infinity (no screen) | 1.1246 | 0.600 | 0.400 |

The curve **saturates at eta = 4**. Beyond it, RMSE, MPC share and supervisor share are
identical to the no-screen limit to four decimal places. **Removing the first-action decrease
screen entirely changes calibration RMSE by +0.0000 m.** At the selected operating point the
screen does not fire.

Two consequences, and they pull in opposite directions for the manuscript.

*Against it:* the Eq. (15) first-action screen is **not load-bearing** at the calibrated
allowance. The manuscript cannot present it as a mechanism that improves anything. At the
conformal eta = 1.875 it fires on roughly 0.2% of steps and costs +0.009 m of RMSE, so even
there its effect is to make tracking slightly worse.

*For it:* the residual **40% supervisor share is not the screen**. It is unchanged at
eta = infinity, so it comes entirely from the pre-action **eligibility** test — the
operating radius and the passing-fallback requirement. That mechanism is load-bearing, and
it is a different mechanism from the one the certificate section emphasises.

The selection rule was **not** changed after seeing the curve: eta = 4 is what the
pre-declared rule returns on the widened grid, and it is reported as such even though
selecting a large allowance is adverse to the manuscript's own claim.

Frozen before any gate or test episode: **R = 51.4825, eta = 4**, diagnostic tolerance
0.662 m (carried over unchanged and labelled historical, never merged with task success).

### 5.2 Instrumentation smoke gate

48 episodes over 3 controllers x 2 families x 4 conditions x 2 scenarios.

| Check | Result |
|---|---|
| 7.2a every declared log channel present | PASS, 25 channels, none missing |
| 7.2b preview is N+1 = 13 at N = 12, with H = 5 recorded separately | PASS |
| 7.2c action taxonomy total, exactly one source per step | PASS, shares sum to 1.0 within 1e-9, all labels inside the declared 12 |
| 7.2d fault-slot execution | PASS, 0 skips healthy, 125-135 per 600 steps faulted, never more than one per step |
| 7.2e full decision latency inside the period | PASS, worst per-episode p95 **19.4 ms** against 100 ms, zero deadline misses |

The taxonomy totality check is the one that matters most, because the first campaign's
reported decomposition omitted the first-action path and left **24-41% of steps
unattributed**. The 12-label taxonomy now accounts for every commanded step.

Latency is **simulation-workstation** timing and is labelled as such, never as flight-computer
timing.

### 5.3 M0 and M5 checkpoint independence, verified rather than asserted

Five different checkpoints loaded into M0 produce **bitwise identical** commanded packets
and a single post-onset RMSE value; likewise M5. They are therefore run once per scenario.
The plan forbids copying one trajectory five times and reporting the copies as seed
replicates, and this is the empirical basis for obeying it rather than a claim about the
code.

### 5.4 The M3/M4 semantic stop gate fired

160 development episodes: 16 scenario units x 5 M3 checkpoints x paired M3/M4 deployments.

| Criterion | Result |
|---|---|
| selected packets identical on every pair | **yes** |
| action sources identical on every pair | **yes** |
| trajectories identical on every pair | **yes**, max state difference 0.000e+00 |
| M3 enabled repeated-check rejections | **0** |
| M3 would-reject count, evaluated but not acted on | **0** |

The prespecified stop rule triggered. **M4 is omitted from the prospective matrix**, 2,400
rollouts are not spent, and the repeated-check **performance** claim is removed from the
manuscript. Only the semantic/replay finding is reported: over 160 development episodes the
repeated post-allocation check never fired, and disabling it changed nothing, bitwise. This
confirms prospectively what Section 2.4 recovered from the archive.

---

## 6. The operating radius is absorbing, and the declared rule mis-set it

`pathb4b_radius.py` -> `results/pathb4b_radius.json`

This was found *after* the first prospective matrix had already run, and it is the second
substantive finding of the campaign. It is reported in full, and both matrices are kept.

### 6.1 The symptom

On the first matrix the retained step family produced post-onset RMSE of 1.67-2.13 m, with
the **supervisor supplying 77-79% of all commanded steps** and achieved completion between
0.3% and 33%. A sensitivity check over R alone, every other constant held fixed, showed that
this is a cliff rather than a gradient:

| R | supervisor share | step-family RMSE | achieved completion |
|---|---|---|---|
| **51.48** (the declared rule's value) | 0.79 | 1.748 m | 0.33 |
| 63.11 (the archived value) | 0.01 | 0.503 m | 1.00 |
| 120 | 0.00 | 0.482 m | 1.00 |
| unbounded | 0.00 | 0.482 m | 1.00 |

A 22% change in one constant flips the controller between working and not working. The
`smooth_dock` family is **completely insensitive** to R: 0.181 m at every value, because it
starts at the vehicle's own pose and its error never approaches the radius.

### 6.2 The mechanism, in closed form

The supervisor is `u = -kp*[vx, vy, r]`, clipped. It reads `x_hat[2]`, `x_hat[3]` and
`x_hat[5]` and **never reads position or heading error at all**. It is pure velocity and
yaw-rate damping, so when eligibility fails it brings the vehicle to rest and leaves the
position error exactly where it was.

The position block of P has eigenvalues 882.94 to 883.37, so at R = 51.4825 a vehicle **at
rest** is ineligible in every direction beyond **1.7326 m** of position error. Inside that
set the supervisor damps a velocity that is already zero and no other command is ever
issued. **The complement of the eligibility set is absorbing.**

The retained step family presents a 2.0 m instantaneous setpoint change at t = 0, which is
1.2x the entry threshold. It therefore *starts inside the absorbing set.* Measured over 64
episodes: on the step family the **longest unbroken supervisor interval is 600 of 600
steps** — whole episodes in which control is taken at the first step and never handed back —
and 19 of 32 episodes end inside a supervisor interval.

This is not a tuning observation. It says the eligibility mechanism paired with this
supervisor is **not a recovery behaviour**: entered from a large position error it is a trap.
The plan already requires the supervisor not be described as a safety guarantee; this is a
stronger statement and the manuscript must make it.

### 6.3 Why the declared rule was wrong independently of any outcome

The rule was "R = 95th percentile of `||e||_P` observed over the monitor pass". It is
circular. The monitor pass observes `||e||_P` under a controller that is *not* being
diverted, so the distribution it produces **is the trajectory the controller needs to fly**.
Taking its 95th percentile and then enforcing it forbids 5% of normal operation by
construction, and the forbidden 5% is not a random 5%: it is the high-error start of every
manoeuvre. An operating envelope that excludes the beginning of the task is not an envelope.

The corrected rule is stated without reference to any outcome:

> R = max( 1.20 x max observed `||e||_P` over the monitor pass, `||e||_P` of a 2 m at-rest
> position error )

The first clause makes the radius an envelope of normal operation instead of a quantile that
excludes its own tail; the second guarantees the retained task's initial condition is
admissible, so the task cannot be forbidden at t = 0. Over 120,000 monitor transitions:
p50 = 11.24, p95 = 51.48, p99 = 63.56, **max = 140.18**, giving R = 1.20 x 140.18 =
**168.2125** (the envelope clause binds; the task clause gives 59.44). The archived R = 63.11
satisfied the task clause by luck rather than by design.

### 6.4 Both matrices are reported

The full 12,960-rollout matrix was re-run at the corrected radius with every other constant
identical, so the comparison isolates R. The pre-registered artefacts are **not discarded**.

| | Pre-registered | Corrected |
|---|---|---|
| R | 51.4825 | 168.2125 |
| artefacts | `pathb5_test.json`, `pathb6_analysis.json` | `pathb5_test_Rcorrected.json`, `pathb6_analysis_Rcorrected.json` |
| step-family supervisor share | 0.70-0.79 | **0.000** |
| M2 achieved completions | 1133 / 2400 | **1885 / 2400** |

**Every claim-gate verdict is identical under both radii.** Only the magnitudes move. That
is the robustness statement the paper should carry, and it is the reason the correction
strengthens rather than rescues the conclusions.

---

## 7. The prospective matrix

`pathb5_test.py` -> `results/pathb5_test{,_Rcorrected}.json`, `results/pathb_rollouts*.csv`

12,960 rollouts per radius, 25,920 in total, over 88 and 107 minutes. M4 is omitted under the
stop rule, which is the reduced route the plan blesses explicitly and which saved 2,400
rollouts.

### 7.1 Counts, kept separate as the plan requires

| Method | Definition | Checkpoints | Unique scenarios | Rollouts | Rollouts/unit |
|---|---|---|---|---|---|
| M0 | nominal, no learned residual or context | 1 | 480 | 480 | 1.0 |
| M1 | trained constant context | 5 | 480 | 2400 | 5.0 |
| M2 | changing context, prediction losses only (**selected**) | 5 | 480 | 2400 | 5.0 |
| M3 | changing context + behavioural loss | 5 | 480 | 2400 | 5.0 |
| M5 | nominal feedback + repair, no MPC optimisation | 1 | 480 | 480 | 1.0 |
| M-motion | M2 without the estimator-diagnostic channels | 5 | 480 | 2400 | 5.0 |
| R-off-clean | M2 with finite proposal repair disabled | 5 | 480 | 2400 | 5.0 |
| **total** | | | **480** | **12960** | |

Seedless methods are at exactly 1.0 rollouts per unit, verified rather than asserted (§5.3).
Nothing was discarded: supervisor intervals, solver failures, repair failures, gate
inactivity, deadline misses and non-completions all remain in the denominators.

### 7.2 Where commands actually come from (corrected radius)

This is the most useful table in the campaign, and it reframes the contribution.

| Family | Condition | Method | `mpc_primary` | `mpc_replacement` | `m5_feedback` | supervisor |
|---|---|---|---|---|---|---|
| step | healthy | M2 | 0.215 | **0.785** | 0.000 | 0.000 |
| step | combined | M2 | 0.239 | **0.759** | 0.000 | 0.000 |
| smooth_dock | healthy | M2 | 0.086 | **0.914** | 0.000 | 0.000 |
| smooth_dock | combined | M2 | 0.158 | **0.841** | 0.000 | 0.000 |
| smooth_dock | healthy | R-off | 0.981 | 0.000 | 0.000 | 0.018 |

**The raw MPC first action is almost never the command that is transmitted.** Finite proposal
repair replaces it on 68-91% of steps. The MPC solves; repair decides what can actually be
flown through the duty law and the allocator. Every share sums to 1.000, over the full
12-label taxonomy, against the first campaign's 24-41% unattributed.

### 7.3 Descriptive outcomes (corrected radius, post-onset position RMSE in m)

| Family | Condition | M0 | M1 | **M2** | M3 | M5 | M-motion | R-off |
|---|---|---|---|---|---|---|---|---|
| step | healthy | 0.538 | 0.565 | **0.431** | 0.649 | *0.264* | 0.421 | 3.004 |
| step | actuator | 0.534 | 0.556 | **0.438** | 0.670 | *0.268* | 0.441 | 2.885 |
| step | perception | 1.101 | 1.196 | **0.935** | 1.176 | *0.807* | 0.970 | 3.005 |
| step | combined | 1.008 | 1.064 | **0.855** | 1.130 | *0.739* | 0.865 | 3.051 |
| smooth_dock | healthy | 0.184 | 0.187 | **0.190** | 0.192 | 0.204 | 0.189 | 2.355 |
| smooth_dock | actuator | 0.190 | 0.194 | **0.202** | 0.201 | 0.224 | 0.201 | 2.092 |
| smooth_dock | perception | 0.766 | 0.775 | **0.742** | 0.786 | 0.749 | 0.744 | 2.162 |
| smooth_dock | combined | 0.796 | 0.815 | **0.755** | 0.820 | 0.763 | 0.770 | 2.023 |

Achieved task completion, same run: on `smooth_dock` every method completes 1.000 under
healthy and actuator faults and drops to 0.54-0.65 under perception degradation; on `step`
M2 is 0.997 healthy and 0.533 combined.

### 7.4 The estimation gap

Zero under healthy perception for every method on both families, and non-zero **only** in the
perception-degraded conditions, where it reaches 0.057-0.067 on `smooth_dock`. Up to about
7% of runs are declared complete by the vehicle and not certified by a ground-truth observer,
and that happens exactly where the plan's perception story predicts it should. R-off is 0.000
everywhere only because it never completes in either frame.

---

## 8. Estimands and claim gates

`pathb6_analysis.py` -> `results/pathb6_analysis{,_Rcorrected}.json`

Analysis seed 260921, 10,000 resamples, crossed scenario-paired bootstrap exactly as
specified in §9.3: scenario IDs resampled within condition with every method's outcome kept
paired; training seeds resampled independently with the same resampled M2 seed vector reused
across every contrast involving M2 in a replicate; M5 paired to one seedless outcome per
scenario; R-off-clean resampled **jointly** with the M2 checkpoint it reuses; M3/M2 resampled
jointly because provenance verifies the matched initialisation and data order. Within-method
seed averaging happens **before** differencing, so M1 and M2 seed labels are never falsely
paired.

### 8.1 The two co-primary estimands

| Estimand | Family | Contrast | Pre-registered R | Corrected R | Gate |
|---|---|---|---|---|---|
| **D21** | step | M2 - M1 | **-0.1103** m, 97.5% [-0.1663, -0.0605] | **-0.1805** m, 97.5% [-0.2215, -0.1381] | **SUPPORTED** under both |
| **D25** | smooth_dock | M2 - M5 | -0.0276 m, 97.5% [-0.0779, +0.0164] | -0.0126 m, 97.5% [-0.0321, +0.0059] | **UNRESOLVED** under both |

Negative favours M2. D21's 97.5% Bonferroni interval excludes zero under both radii, so the
dynamic-context claim survives the multiplicity allowance. D25's contains zero under both.

**D21 breaks down the way the paper's own story predicts**, and this is the strongest
positive result of the campaign (corrected radius):

| Condition | D21 |
|---|---|
| healthy | -0.1345 m |
| actuator | -0.1179 m |
| perception | **-0.2611 m** |
| combined | **-0.2087 m** |

The benefit of inferring a *changing* context roughly doubles when perception degrades. That
is a mechanism-consistent result, not a uniform offset, and it is what makes the
context-learning contribution defensible.

Per-seed M2 means on the step family (corrected): 0.661, 0.645, 0.668, 0.710, 0.640; M1:
0.853, 0.842, 0.840, 0.844, 0.848. The separation is far larger than the seed spread on
either side, which is what makes a five-seed interval credible here.

### 8.2 Secondary contrasts (corrected radius; negative favours the first-named method)

| Contrast | Family | Mean (m) | 95% interval | Reading |
|---|---|---|---|---|
| M3 - M2 | step | **+0.2413** | [+0.1983, +0.2856] | behavioural loss significantly **worse** |
| M3 - M2 | smooth_dock | **+0.0271** | [+0.0132, +0.0417] | significantly **worse** |
| M2 - M-motion | step | -0.0094 | [-0.0404, +0.0236] | diagnostic channels: **no effect** |
| M2 - M-motion | smooth_dock | -0.0037 | [-0.0136, +0.0063] | **no effect** |
| M2 - R-off | step | **-2.3216** | [-2.5696, -2.0720] | repair is **dominant** |
| M2 - R-off | smooth_dock | **-1.6857** | [-1.9078, -1.4912] | repair is **dominant** |
| M2 - M0 | step | -0.1304 | [-0.1656, -0.0945] | learned residual helps |
| M2 - M0 | smooth_dock | -0.0115 | [-0.0305, +0.0074] | no effect |
| M2 - M5 | step | **+0.1453** | [+0.1130, +0.1788] | **M5 is better** |
| M2 - M1 | smooth_dock | -0.0206 | [-0.0405, -0.0028] | changing context helps |

Task completion differences, reported descriptively in both frames and never merged: on the
step family M2 - M1 is **+0.0617** achieved (95% [+0.0217, +0.1017]) and +0.0550 declared,
both favouring M2. On `smooth_dock` M2 - M5 contains zero in both frames.

### 8.3 Gate verdicts

Identical under both radii.

| Section | Gate | Verdict |
|---|---|---|
| 10.1 | dynamic-context RMSE | **SUPPORTED** |
| 10.2 | learned-MPC pipeline RMSE | **UNRESOLVED** |
| 10.3 | multimodal streams | **UNRESOLVED** |
| 10.4 | behavioural loss | **ADVERSE** |
| 10.5 | repeated post-allocation check | **REDUNDANT under the preceding screen** |
| 10.5 | finite proposal repair | **SUPPORTED** |
| 10.6 | certificate and safety | **NOT CLAIMED** |

---

## 9. What the manuscript may now say, and what it must stop saying

### 9.1 Claims that survive

**Changing context beats trained static context, and most where perception degrades.**
D21 = -0.18 m with the Bonferroni interval excluding zero, -0.26 m under perception
degradation against -0.13 m healthy, corroborated at the prediction level (M2's development
one-step MSE is 29% below M1's) and by task completion (+6.2 percentage points, interval
excluding zero). This is the paper's result.

**Finite proposal repair is the load-bearing component of the controller.** M2 - R-off-clean
is -2.32 m on `step` and -1.69 m on `smooth_dock`; R-off-clean achieves **0 of 2,400**
completions. The taxonomy explains why: repair replaces the raw MPC action on 68-91% of
steps, so without it the MPC's first action is mostly untransmittable. This is measured
against a *clean* R-off variant in which both arms trial-allocate their own proposal and both
apply the same screens to the resulting transmitted command; the historical M7 is **not**
this experiment and is not relabelled as it.

### 9.2 Claims that must be withdrawn or reworded

**The complete learned-MPC pipeline is not distinguishable from nominal feedback with
repair.** D25 = -0.013 m with the interval containing zero. Worse for the pitch: on the
retained step family **M5 is significantly better than M2** (+0.145 m). A feedback law with
repair, no MPC and no learned model, beats the full pipeline on one family and ties it on the
other. Say this plainly. It is also mechanically unsurprising: repair is what both share, and
repair is what is doing the work.

**The behavioural-supervision loss is an adverse ablation, not a contribution.** M3 - M2 is
significantly positive on both families (+0.241 and +0.027) and was significantly positive in
all four archived conditions too. The development grid selected weight zero before any test
ran, so M2 is the selected method and M3 is a labelled negative result. It is not revived
without a new training design and a fresh untouched test.

**No modality-fusion benefit may be claimed.** M2 - M-motion contains zero on both families
and the development prediction gap is 1% against a seed spread of under 1%. Removing the two
innovation scalars and the pose-validity channel changes nothing measurable. Retain the title
but describe the input composition precisely, and note that M-motion still contains
vision-influenced estimated states and residuals, so the negative result bounds only the
**explicit** diagnostic channels and not all perception information.

**Neither the first-action screen nor the repeated check may be presented as beneficial.**
The repeated post-allocation check never fires and disabling it changes nothing bitwise over
160 development episodes; it is redundant under the screen that precedes it, for the
structural reason that both are the same inequality on the same quantity. The first-action
decrease screen is inert at the calibrated allowance: removing it entirely changes
calibration RMSE by +0.0000 m.

**The eligibility test plus supervisor must be described as an absorbing mechanism.** It is
the one component that dominates the command stream when it engages, and entered from a
position error beyond `R/sqrt(lambda_min(P_pos))` it never hands control back. The paper
should state the trapping threshold, report that the supervisor reads no position error, and
give the radius sensitivity. Describing it as recovery would be wrong.

**No safety claim.** No verified invariant region, no calibrated safety probability, no
collision-free or continuous-time guarantee, no guaranteed recovery. The transmitted-command
proposition stays conditional on its explicit discrepancy assumptions.

### 9.3 Two disclosures the manuscript did not previously contain

**There is no absolute position reference after the one-shot `t0` alignment**, so the
estimate-to-truth error is an unbounded random walk reaching 0.19 m healthy and 0.83 m
occluded by 60 s. Every true-state RMSE in the paper therefore has an estimation-error floor
underneath it, and the task-success endpoint cannot be tighter than that floor. This also
means the system is **not** Vicon-free: the alignment anchors the origin against ground
truth.

**The feature scaling constants are hardcoded, not computed from the training split.** They
are frozen and disclosed as hardcoded so that M1, M2, M3 and M-motion stay exactly
comparable.

---

## 10. Against the plan's completion checklist

| Plan item | Status |
|---|---|
| Provenance freeze, contract classification, feature/scaling audit (§3, §5) | **done**, 24/24 checks |
| Machine-readable scenario population + hash (§6.1) | **done**, `scenario_population_v1` |
| Historical reanalysis from raw artefacts (§2.2, §3.3, §11.4) | **done**, two sign/count corrections |
| `smooth_dock_v1` frozen with a development feasibility gate (§6.3, §6.4) | **done**, 30 s, 20/20 both frames |
| Provisional task thresholds justified or changed, dwell semantics reconciled (§9.4, line 524) | **done**, `task_success_v2`, 22-observation dwell |
| Five seeds for M1, M2, M3, M-motion (§4.1, §11.1) | **done**, 20 checkpoints |
| Instrumentation smoke gate (§7) | **done**, 5/5 pass |
| M3/M4 semantic stop gate (§7) | **done**, stop rule fired, M4 omitted |
| 12-label action taxonomy, total (§8.4) | **done**, shares sum to 1.000 |
| Full decision-latency measurement (§8) | **done**, p95 19.4 ms, labelled workstation timing |
| Prospective matrix (§11.3) | **done**, 12,960 rollouts x 2 radii |
| Crossed scenario-paired bootstrap, seed 260921 (§9.3) | **done** |
| Claim gates (§10) | **done**, all seven resolved |
| Failure/censoring ledger, orthogonal flags (§9.5) | **done** |
| Hardware re-anchoring (§12) | **not done** — no hardware access; the hardware table stays archival and descriptive |

### Outstanding

Only one plan item is not addressed: **fresh hardware blocks (§12)**. The existing hardware
table must stay labelled archival and descriptive, and the hardware plot must be a clearly
archival descriptive plot rather than a fresh paired comparison. Everything in the simulation
programme is complete.

---

## 11. Artefacts

| Stage | Script | Artefact |
|---|---|---|
| 0 provenance freeze | `pathb0_freeze.py` | `pathb0_freeze.json` |
| 1 historical reanalysis | `pathb1_reanalysis.py` | `pathb1_reanalysis.json` |
| 2 gate diagnostic | `pathb2_diag.py` | `pathb2_diag.json` |
| 2 estimation floor, `task_success_v2` | `pathb2_floor.py` | `pathb2_floor.json` |
| 2 task feasibility gate | `pathb2_taskgate.py` | `pathb2_taskgate.json` |
| 3 training | `pathb3_train.py` | `pathb3_train.json` |
| 4 calibration + development gates | `pathb4_gates.py` | `pathb4_gates.json` |
| 4b operating-radius analysis | `pathb4b_radius.py` | `pathb4b_radius.json` |
| 5 prospective matrix | `pathb5_test.py` | `pathb5_test{,_Rcorrected}.json`, `pathb_rollouts*.csv` |
| 6 estimands + claim gates | `pathb6_analysis.py` | `pathb6_analysis{,_Rcorrected}.json` |
| 7 tables + figures | `pathb7_report.py` | `table1`-`table5*.md`, `figs/fig1`-`fig4*.png` |

Figures: `fig1` the allowance curve and where the screen stops firing; `fig2` the estimation
floor against both task tolerances; `fig3` a forest plot of every contrast on both families;
`fig4` representative traces with the true, observed and estimation errors separated and the
action source per step underneath.

Test manifest SHA-256 `01d416add89f07818ce837a29fbfa07b9d34b0b8703b02d436baf2aa58a0cf2d`;
scenario population SHA-256
`b790a993904aa4c0ac586736c2c9df9ecf0e367731cef1574e8231ededa02634`. Both matrices were run
against the same manifest, so the two radii are compared on identical scenarios.

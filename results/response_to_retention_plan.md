# Response to the RA-L results retention and completion plan

Run `v4-architecture-repair` · commit `81f52657` · config `07f277768a04859a`

Responding to [`RAL_Updated_Results_Retention_and_Completion_Plan.md`](RAL_Updated_Results_Retention_and_Completion_Plan.md), section by section, using that document's numbering. Full evidence is in [`results.md`](results.md).

Every number below is read from the frozen Stage 0-8 artefacts by `stage9_response.py`, not
typed in. Status words are used strictly: **VERIFIED** (the plan asserted something
checkable and we checked it), **IMPLEMENTED** (in the code and evidenced by a gate or a
number), **PARTIAL** (named sub-items done, others named as outstanding), **NOT IMPLEMENTED**
(not done, no credit claimed).

---

## Summary

| Plan section | Requirement | Status |
|---|---|---|
| §3.1-3.5 | Verify the quoted numbers and keep the negative results | VERIFIED — every checkable claim in the plan was correct |
| §4.1 | One physical fault-slot execution contract | IMPLEMENTED |
| §4.2 | Make the no-check variant a single-component ablation | IMPLEMENTED — and it changes the conclusion |
| §4.3 | One canonical learned model throughout the controller | NOT IMPLEMENTED |
| §4.4 | Complete candidate feasibility and source eligibility | PARTIAL |
| §4.5 | Reference, endpoint and action bookkeeping | PARTIAL |
| §5.1 | Define task completion and recovery separately | IMPLEMENTED |
| §5.2 | Diagnose supervisor dominance on a development set | NOT IMPLEMENTED |
| §5.3 | Diagnose transfer before adding transfer trials | NOT IMPLEMENTED |
| §6.1-6.3 | Core comparison matrix, seeds, uncertainty | PARTIAL |
| §7.1 | Preserve the failed certificate search honestly | IMPLEMENTED |
| §7.2-7.5 | One verified and calibration-accepted recovery case | NOT IMPLEMENTED |
| §8.1 | Correct the report now, without new simulations | IMPLEMENTED — all 11 items |
| §8.2 | Resolve the horizon discrepancy; keep hardware central | IMPLEMENTED as a robustness axis |
| §8.3 | Recommended final tables and figures | PARTIAL |

The three outstanding blocks are §4.3 (canonical model and context-conditioned feedforward),
§5.2-5.3 (diagnostics) and §7.2-7.5 (a positive recovery case). They are listed as gaps in
the README rather than glossed. §4.3 in particular blocks the §6.1 M3-M5 comparison from
being the matched test the plan asks for.

---

## §3 What the current numbers support

### §3.1-3.5 the plan's quoted figures — **VERIFIED**

We re-derived every figure the plan quoted from the artefacts before accepting its argument.
All of them matched, including the four behavioural-supervision intervals to four decimals,
the four changing-context differences, the four MPC-minus-fallback differences, the task
success counts, the action-source percentages, and the 0.662 m recovery tolerance. Two
structural claims we could only confirm by writing tests; both were also correct, and they
are answered in §4.1 and §4.2 below.

Those figures have since **moved**, because the corrections in §4-§5 changed the controller and
the physics. The current values are below. The plan's reading of the *previous* campaign was
accurate; it is simply no longer the current campaign.

| Comparison | Plan's framing | Current result | Conclusion |
|---|---|---|---|
| §3.1 behavioural supervision (M3-M2) | adverse, all four point estimates against it | +0.165 to +0.510 m, significantly worse in 4/4 | **kept: no demonstrated benefit** |
| §3.2 changing context (M2-M1) | most promising result | -0.515 to -0.093 m, better in 4/4 | **kept: supported** |
| §3.3 MPC beyond fallback (M3-M5) | preserve the adverse outcome | +0.237 to +0.675 m | **kept: no demonstrated improvement** |
| §3.4 practical performance | low success, fix the endpoint | 910/5280 rollouts now scored at the **final** waypoint | **kept: poor** |
| §3.5 transfer | preserve the failure | learned 0.4-1.0 m vs zero-context 0.37-1.30 m on the held-out family | **kept: fails badly** |

The one comparison whose **conclusion reversed** is the post-allocation check; see §4.2.

---

## §4 Corrections to complete

### §4.1 Unify physical fault-slot execution — **IMPLEMENTED**

The plan was right, and we confirmed it numerically before changing anything: across firing
fractions {0.3, 0.5, 0.7, 0.9} and initial phases {0, 1, 2}, **all 12 configurations produced
different fire/skip sequences** between the two paths, with the policy path equal to the
data-generation path at phase + 1.

The contract is now single-valued, as §4.1 specifies:

1. the policy selects a pre-fault packet from controller-visible information;
2. `CommandChain.commit` performs the **software** allocator-memory update and nothing else;
3. `CommandChain.realize` previews the hidden effect for the designated slot, then
4. advances that slot exactly once;
5. the plant integrates the actual pulses using true state.

Both the data-generation shorthand and the closed-loop runner call `realize`, so the hidden
effect can no longer be reached from a controller-visible path and cannot be applied at two
different counter states.

- Gate `2.4f data-generation and policy paths fire identical physical pulses`: **PASS** — 12/12 (firing fraction, phase) configurations produce identical fire/skip sequences AND identical counter sequences across both execution paths. Both route the hidden effect through realize(), so the software allocator commit and the physical fault slot are consumed at the same point on every path.

- Gate `2.4d software commit updates memory; realize consumes one fault slot`: **PASS** — commit left the fault cycle at 0 (memory-only: True) and committed the selected packet (True); realize then advanced it to 1. Separating the two is what lets both execution paths consume the hidden slot at the same point.

**Completion check requested by the plan**, and the reuse question it raises: the effect is
bounded and attributable. Healthy cells are bit-identical to the previous campaign, because
the fix only touches faulted physics. Across faulted cells the largest shift is **0.027 m**.
That is consistent with what this defect was - a fault *phase* offset, not a severity change,
since the long-run skip rate was never wrong. Training transitions did not need regenerating;
the faulted closed-loop evaluations did, and were.

### §4.2 Make the no-check variant a single-component ablation — **IMPLEMENTED — and it reverses the conclusion**

This was the most consequential item in the plan. It was also correct: `check_mode="off"`
gated three mechanisms at once (supervisor diversion on ineligibility, the first-action
condition, and the post-allocation test), so the M3-M4 gap could not be attributed to the
allocated-command check.

The safeguards are now independent switches. M4 keeps the same checkpoint, eligibility and
supervisor diversion, first-action condition, solver fallback **and** command-admissibility
budget as M3, and disables only the Eq. (18) decrease test. Following the plan's explicit
instruction to either state that admissibility is part of the disabled bundle or retain it in
both arms, we retain it in both arms, so the ablation is precisely "the post-allocation
decrease test is disabled".

**Result: the isolated effect is exactly +0.00000 m in all 4/4 conditions.** The decrease test never rejects a candidate.

The reason is structural rather than numerical. The first-action condition is the *same*
inequality without the eta allowance, hence strictly tighter, so any candidate that survives
it passes the decrease test automatically. In monitor mode, where the first-action condition
is not enforced, the decrease condition is violated by **67.0%** of raw candidates - so the test is not
vacuous in itself, it is **redundant given the screening that precedes it**.

Two further consequences the plan asked us not to paper over:

- What the earlier campaign logged as acceptance-check rejections (~3-4%) was the plain
  **command-admissibility budget**, not Eq. (18). Those are now separate action sources.
- Under the old bundled switch M4 diverged (RMSE 2.6-3.6 m). Most of the change in aggregate
  task-success counts between campaigns comes from M4 no longer diverging, not from any
  method improving. We state that rather than presenting it as progress.

The plan's instruction to "keep the old no-check result as a comparison against multiple
disabled safeguards, remove its claim to isolate the allocated-command check" is followed:
the old contrast is described as a combined-safeguard diagnostic and the isolation claim is
withdrawn.

### §4.3 Use one learned model consistently throughout the controller — **NOT IMPLEMENTED**

No credit claimed. There is still no single canonical evaluation of f_theta(x, u, z) shared by
training targets, feedforward selection, horizon prediction, affine model construction, the
post-allocation check and the derivative analysis.

The specific consequence worth flagging, because it limits a comparison the plan itself asks
for: the fallback's feedforward is still **nominal**, its learned residual is computed and
discarded, and its trajectories are therefore identical across model seeds. As the plan notes,
repeating a checkpoint-independent fallback three times is not three pieces of independent
evidence. So the current M3-M5 result answers "does MPC beat *this* nominal fallback", not
the matched question "does MPC add planning value given the same context-conditioned
feedforward". That comparison is blocked until this item is done, and the report says so.

### §4.4 Complete candidate feasibility and source eligibility — **PARTIAL**

**Done.** The first-action condition of Eq. (15) is enforced as an explicit check on the
returned proposal, and a proposal that fails it is not treated as a feasible candidate but
diverted to the checked fallback. This is declared as an approximate proposal generator
followed by verification, which is the option the plan permits provided it is identified.
Command admissibility (u in U) is enforced on every transmitted command. Eligibility requires
both the state radius and a fallback that passes its own check.

**Diagnosed rather than tuned away.** The plan warns against making the acceptance test
permissive to raise the MPC action share. We did not, and the decomposition now shows why
that would not have worked: the binding mechanism is the first-action condition at
0%-0% of steps, which carries **no eta** and cannot be relaxed by any choice of eta. The MPC
candidate is transmitted on only 81%-99% of samples.

**Outstanding.** Predicted-state region membership (e_i in C, e_N in C) is not independently
verified across the horizon; the verified model/context/reference/allocator domains and the
corridor/chart conditions do not exist, so what is implemented is an **operational supervisor**
and the report labels it that way rather than as theorem eligibility. The componentwise
pseudo-Huber objective of Eq. (16) is not implemented as such.

### §4.5 Complete reference, endpoint and action bookkeeping — **PARTIAL**

**Done.**

- `r_now` and the committed `r_next` are stored separately (`log.ref` and `log.ref_next`), and
  the committed successor is fixed before the next sample can reschedule it.
- Candidate and fallback slacks are separate channels (`slack_cmd`, `slack_fb`), asserted by
  gate 4.6d, so a candidate's slack cannot be read as the transmitted action's.
- `fallback_first_action` is included in the aggregate action-source counts. It had been
  counted in policy stats but omitted from the reported decomposition, which left 24-41% of
  steps unaccounted for.
- Every source is now logged and aggregated, with an **assertion** that the shares sum to one
  and that no unlabelled source appears. Gate 4.6c checks the same property independently.

| Condition | candidate | fb: first-action | fb: decrease | fb: budget | fb: solver | supervisor | sum |
|---|---|---|---|---|---|---|---|
| healthy | 0.987 | 0.000 | 0.000 | 0.000 | 0.000 | 0.013 | 1.000 |
| actuator | 0.986 | 0.000 | 0.000 | 0.000 | 0.000 | 0.014 | 1.000 |
| perception | 0.810 | 0.000 | 0.000 | 0.000 | 0.000 | 0.190 | 1.000 |
| combined | 0.808 | 0.000 | 0.000 | 0.000 | 0.000 | 0.192 | 1.000 |

**Outstanding.** `solve_ms` still records only the QP solver's reported duration, not full
decision latency including context inference, feedforward and the checks, and deadline status
is not logged as a separate flag. H+1 physical states and estimates per H transmitted commands
are not explicitly retained as a checked invariant.

---

## §5 Performance scoring and diagnosis

### §5.1 Define task completion and recovery separately — **IMPLEMENTED**

Task completion now requires the **final** intended waypoint and heading (0.15 m,
5 deg) held for 2 s before the 60 s deadline, via a new `final_target()` on each
reference family. The any-waypoint dwell is retained separately as `dwell_any_waypoint`,
because it is a useful tracking signal but is not completion.

Recovery is scored on its own onset-relative clock: the qualifying dwell must lie entirely at
or after onset, so a pre-onset success can no longer be credited as recovery from the fault.
**Maintenance** (inside tolerance at onset and never leaving) and **reacquisition** (an actual
excursion followed by return) are recorded separately. The 0.662 m recovery
tolerance stays an explicitly labelled baseline-relative diagnostic and is never merged into
the same column as the 0.15 m task tolerance.

The held-out `transfer` family is a closed curve with no rest point, so waypoint completion is
**undefined** there and those episodes are excluded from the denominator rather than counted
as failures.

**Honest note on materiality.** This changed exactly **one cell of 32** (`perception|constant_context`, 4 -> 3). The endpoint concern was real in principle, but for the
hardware-matched `step` family the position-triggered switch means the current setpoint *is*
the final waypoint for almost the whole episode, so the earlier counts were not materially
inflated by it. We report that rather than implying the fix was consequential.

### §5.2 Diagnose supervisor dominance on a small development set — **NOT IMPLEMENTED**

The phenomenon is quantified but not diagnosed. The fixed supervisor issues 1%-19% of
transmitted actions, and the decomposition in §4.5 now separates the reasons candidates are
not used. What does **not** exist is the prescribed per-scenario diagnostic: the five-panel
plots over a few pre-specified development episodes, the identification of where progress
toward the task stops, and the check of whether the velocity-damping supervisor reduces motion
without advancing toward the reference. That remains a hypothesis, not an established
explanation, and the report does not assert it as one.

### §5.3 Diagnose transfer before adding more transfer trials — **NOT IMPLEMENTED**

The failure is preserved and reported. None of the five prescribed diagnostics has been run,
so the attribution remains open; in particular we do **not** claim the neural residual alone
caused it, since reference generation, feedforward, eligibility, supervisor behaviour and
prediction could each contribute.

One relevant piece of existing evidence: model-level prediction error on common held-out
sequences is *worse* for the behaviourally supervised models than for the prediction-only
ones, which is consistent with the in-distribution result and points away from the
behavioural loss as a fix for transfer.

---

## §6 The focused experiment package

### §6.1 Core comparison matrix — **PARTIAL**

All seven variants exist and are run on matched draws: M0 nominal-predictor recovery, M1
trained constant context, M2 prediction-only dynamic context, M3 positive-coefficient
behavioural supervision, M4 the now-correct single-component ablation, M5 fallback-only, and
HW the hardware-matched comparator, plus adaptive MPC.

| Primary pair | Question | Current result |
|---|---|---|
| M2-M1 changing context | | -0.515 to -0.093 m; better 4/4, worse 0/4 |
| M3-M2 behavioural supervision | | +0.165 to +0.510 m; better 0/4, worse 4/4 |
| M3-M4 the allocated-command check | | +0.000 to +0.000 m; better 0/4, worse 0/4 |
| M3-M5 MPC beyond the same fallback | | +0.237 to +0.675 m; better 0/4, worse 4/4 |
| M3-M0 learned prediction | | +0.104 to +0.181 m; better 0/4, worse 2/4 |

**Caveats we are not hiding.** M3-M5 is not yet the matched comparison the plan specifies,
because §4.3 is outstanding and the fallback's feedforward is still nominal and
checkpoint-independent. And on the plan's point that lambda_I = 0 was selected: the
development grid did select **zero**, so M2 is the selected predictor under that rule and M3 is
reported as the positive-weight **ablation**, not as the selected method.

- Grid [0.0, 0.01, 0.1, 1.0], selected **0.0**, on `dev one-step weighted MSE`, dev split, seed 0, before any test run.

### §6.2-6.3 Conditions, seeds, sample size, uncertainty — **PARTIAL**

Four conditions; **60 distinct scenario draws** per condition x **3 training seeds** =
180 rollouts per condition for each learned method. Both counts are reported, as the plan
requires, so 180 rollouts are never presented as 180 independent scenarios. Exogenous random
streams are matched across methods and controller branching cannot change the external
sequence. Two interval levels are reported: episode-level intervals conditional on the
evaluated checkpoints, and seed-crossed intervals where the sampling structure supports them.
Failures stay in the denominators.

**Outstanding.** All three M1 checkpoints are trained, but the constant-context arm is still
broadcast from one seed against the three dynamic-context models (`broadcast_side` is recorded
in the artefact, so this is visible rather than hidden). The final comparison also still runs
on the same scenario seeds used during development; the plan asks for fresh seeds once the
method and tuning rules are frozen, and they are not yet frozen.

---

## §7 The numerical recovery certificate

### §7.1 What is preserved, and what is not claimed — **IMPLEMENTED**

The result stands as stated by the plan: **0 of 2730 swept cells certify**, with a
sound enclosure, and all failed search records are kept. The design code, the nominal
rotation blocks and the allocator-permission-versus-physical-thrust distinction are retained
as development tools.

Every claim the plan lists as unsupported has been removed. Specifically:

- No claim of universal physical impossibility, no necessary +/-5% identification requirement,
  and no rigorous feasibility boundary inferred from a finite unsuccessful sweep.
- The swept certificate used **nominal** matrices, so it is a statement about the nominal
  design budget and **not** a certificate for the learned model.
- Enclosures are upper bounds, so they cannot report attained neural sensitivity.
- Stage 7 emits `residual: {}`. The residual admissibility analysis **did not run**, so the
  "603x nominal" and "four orders of magnitude" statements are removed rather than reworded:
  they were retained strings printed beside their own `n/a` fields. The empty region therefore
  **cannot** be attributed to residual Lipschitz growth on this evidence.

### §7.2-7.5 One useful recovery example, verified and calibrated — **NOT IMPLEMENTED**

No narrow operating case has been frozen and carried through deterministic verification plus
conformal calibration to an accepted certificate. The sampled allocation-error maximum has not
been replaced by a sound bound over the selected region, the uniform fallback-realisation
lemma's premise is unverified, and the floating-point argument is a scaled rounding allowance
rather than verified arithmetic. Accordingly the report keeps the guarantee claim narrow and
treats practical recovery certification as **unvalidated**.

---

## §8 Report and manuscript changes

### §8.1 Correct the report now, without new simulations — **IMPLEMENTED — all 11 items**

| Plan's objection | What it now says |
|---|---|
| "direction and significance replicate everywhere" | Generated from the paired effects. It contradicted the report's own table: 2/4 conditions favour learned context, 2/4 are significantly **worse**. |
| eta described as enforcing the check harder | Corrected: eta is additive on the right-hand side, so a larger eta **relaxes** the inequality. The rise in rejections is explained via eligibility, and the curve is demoted from evidence about the check to a joint eta-sensitivity. |
| 3-4% rejection used to explain fallback dominance | Replaced by the complete six-way decomposition that sums to one. |
| "603x" and "four orders" beside n/a values | Removed; reported as **not evaluated**. |
| "sound certificate" beside unverified rounding | Analytic enclosure, numerical approximation and remaining verification limits stated separately. |
| "the specification is unattainable" | "the evaluated controllers rarely achieve it". |
| behavioural loss "does not help transfer" | Small relative improvement reported together with the large absolute failure. |
| large M3-M4 gap attributed to one check | Re-run as a true single-component ablation; isolated effect is exactly zero. |
| "training data: 360 episodes" | Generated corpus 360; **training split 160**, with the full five-way split manifest. |
| findings blamed on closing the fault leak | Each fix's effect is now separated and quantified. |
| context-conditioned feedforward claimed for nominal code | Corrected; the claim is withdrawn until implemented. |
| "independent hardware replication" | Described as fitted-envelope calibration agreement. |

### §8.2 Resolve the horizon; keep hardware central — **IMPLEMENTED as a robustness axis**

We could not resolve the horizon from the flight configuration, so we stopped asserting it.
`N_HORIZON_HW` is retagged from CONFIRMED to **DISPUTED**: the N=12 claim traces to the build
spec asserting it, the manuscript says N=10, and neither was checked against the configuration
attached to the reported logs.

Rather than pick one, both are now run. The previous grid started at 12 and never evaluated
10, so the manuscript's own value was untested.

| Condition | dRMSE (manuscript - build spec), m | 95% interval | significant? |
|---|---:|---:|---|
| healthy | -0.0068 | [-0.0321, +0.0194] | no |
| combined | +0.0709 | [-0.1917, +0.3537] | no |

Largest difference **0.0709 m**, against the 0.05-0.6 m effects under discussion elsewhere. So
**no conclusion in this study depends on resolving the discrepancy** - though it should still
be resolved before the horizon is quoted as a fact about the hardware. Hardware results remain
the primary physical evidence and simulation repairs do not alter recorded hardware data.

### §8.3 Recommended final tables and figures — **PARTIAL**

Tables 2 and 3 exist in substance (matched comparison; component contributions with matched
checkpoints and uncertainty, unfavourable rows included). Table 4 cannot be produced because
no useful recovery case exists, and the report states that limitation instead. The figure set
is regenerated from the artefacts on every run. A corrected architecture figure showing the
*actual* offline supervision, nominal feedforward, constrained MPC, nominal-transmitted-command
check, fallback and supervisor is **not** yet drawn.

---

## §10 Which decision branch this puts us in

The plan enumerates outcomes; on current evidence this is the **"dynamic context helps but
behavioural supervision does not"** branch, with two aggravating findings.

- Changing context helps: -0.515 to -0.093 m, significant in 4/4.
- Behavioural supervision does not: +0.165 to +0.510 m, worse in 4/4, and the pre-declared grid selected zero.
- The Eq. (18) post-allocation check contributes **exactly nothing** once isolated.
- No useful recovery certificate exists, so practical recovery certification is unvalidated.

Following the plan's own guidance for this branch: the prediction-only model is the selected
one, the unfavourable supervision ablation is retained, and the contribution statement needs
revising. Removing the behavioural objective does leave a less distinctive context-learning
contribution, and the plan is explicit that an unsupported specific claim must not be replaced
by an equally unsupported broad one. The remaining defensible novelty is the coupling of
actuation and perception adaptation together with the hardware demonstration - and the
simulation's own contribution is now partly **negative evidence**: two mechanisms the paper
presents as load-bearing are measurably not.

One framing point that follows from §4.5 and is worth putting in front of a reviewer before
they find it: under M3 the fixed supervisor issues 1%-19% of transmitted actions and the MPC
candidate reaches the actuators on a small minority of samples. What the comparison table
scores is therefore largely a fixed feedback law rather than context-conditioned MPC. That
has to be stated plainly in any claim about the controller.

---

## Stopping criteria (§9)

| Criterion | Met? |
|---|---|
| Implementation and manuscript agree on model, inputs, feedforward, constraints, gate, fallback, reference timing | **no** — §4.3 outstanding, feedforward still nominal |
| The no-check comparison changes only the declared component | **yes** |
| Task success measures the intended final objective and post-fault behaviour | **yes** |
| Core comparisons use matched seeds, scenario counts and uncertainty | **mostly** — constant-context arm still broadcast; final seeds not yet fresh |
| Favourable and unfavourable results both appear with correct interpretations | **yes** |
| Any numerical recovery claim has a verified, calibration-accepted demonstration | **no** — none obtained |
| Hardware and simulation claims accurately distinguished | **yes** |
| No stale values or conclusions contradicted by the report's own tables | **yes** — the README findings block and this document are generated from the artefacts |


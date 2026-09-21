# Response to the RA-L hardware and simulation execution plan

Run `v4-architecture-repair` · responding to [`RAL_Hardware_and_Simulation_Execution_Plan.md`](../RAL_Hardware_and_Simulation_Execution_Plan.md), section by section.

Status words are strict: **IMPLEMENTED** (in the code, evidenced by a gate or a measured
number), **DIAGNOSED** (a cause the plan asked for is identified and quantified), **PARTIAL**
(named sub-items done, others named as outstanding), **NOT IMPLEMENTED** (no credit claimed),
**NOT APPLICABLE** (needs hardware access this work does not have).

---

## The headline: the architecture was not the problem, the implementation was

The plan's §1 judged that the simulation "still evaluates an incomplete implementation". That
was right, and it was the whole story. Three defects, all in the controller rather than in the
method, produced most of the adverse findings in the reviewed campaign.

| Defect | Effect on the reviewed results |
|---|---|
| The command-admissibility budget compared the transmitted wrench against the yaw-INDEPENDENT inner bound (0.96 N). The allocator legitimately delivers up to 1.36 N at off-axis yaw, where four thrusters bear on a force axis instead of two. | The stored fallback was declared inadmissible on **49.6% of all control steps**, which made the source ineligible and handed **52%** of transmitted actions to the fixed supervisor. Not the decrease test, and not the eligible radius: the radius never bound once. |
| The allocation error was modelled as an unknown additive disturbance, absorbed by η. It is neither unknown nor additive-small: holding a fixed request, the per-step error reproduces with ratio **exactly 1.000** over 400 steps, and it is about **6.3%** of the commanded correction against the **0.94%** the decrease inequality admits at λ≈0.99. | A uniform η bound cannot coexist with a nonempty region, which is why the 2,730-cell search returned nothing. |
| Eq. (15)'s first-action decrease condition was checked AFTER allocation and any failing proposal discarded. | The MPC candidate was rejected on **71%** of steps even though a satisfying command demonstrably existed, so the reported "8-13% MPC share" measured the screening, not the planner. |

With those corrected, the MPC candidate now supplies **81%-99%** of transmitted
commands instead of 8-13%, and the fixed supervisor **1%-19%** instead of 42-66%. The
comparisons below are therefore measuring the proposed controller for the first time.

Two consequences are unfavourable and are reported as such: the behavioural loss still does
not help, and MPC planning still does not beat its own matched fallback. Both are now
*meaningful* negative results rather than artefacts of a starved controller.

---

## §2 Evidence the paper needs

| Claim | Verdict on current evidence |
|---|---|
| Recent multimodal history improves adaptation | **supported** — M2−M1 -0.515 to -0.093 m, favourable in 4/4 conditions, matched training losses and controller |
| Behavioural supervision contributes useful information | **not supported** — M3−M2 +0.165 to +0.510 m, worse in 4/4; the development grid selected weight zero |
| Learned prediction improves control | **supported** — M2−M0 -0.376 to -0.061 m, favourable in 4/4 conditions, under the same recovery structure, cost, constraints, allocator and supervisor |
| MPC planning contributes | **not supported** — M2−M5 +0.072 to +0.240 m against the same context-conditioned feedforward, gate, allocator and supervisor. The planning claim must be narrowed. |
| Checking after allocation contributes | **not supported, with a justified explanation** — isolated effect exactly +0.00000 m. With the allowance on both conditions the test is redundant BY CONSTRUCTION, not merely inactive; see §S0.4. |
| The robot completes or recovers the task | **partial** — final-target completion 123/720 for M3 under the 0.15 m / 5° / 2 s specification; ordered reacquisition and maintenance are now scored separately and the specification sits near the actuator quantisation floor (§6.1) |
| The recovery condition is numerically useful | **not supported** — see §11 |
| The implementation operates at 10 Hz | **partial** — complete decision latency p95 21.6-22.8 ms against the 100 ms period, deadline misses 0.0%-0.0%, but on a simulation workstation, NOT the flight computer |

The selected model is **M2** (dynamic context, prediction losses only): the development
grid chose behavioural weight zero. Its own comparisons are therefore the primary ones, rather
than inferred from M3's ablations.

| Comparison | healthy | actuator | perception | combined |
|---|---:|---:|---:|---:|
| M2−M1 changing context | -0.093\* | -0.138\* | -0.515\* | -0.384\* |
| M2−M0 learned residual | -0.061\* | -0.098\* | -0.330\* | -0.376\* |
| M2−HW vs hardware comparator | -0.288\* | -0.447\* | -0.436\* | -0.487\* |
| M2−M6 vs adaptive baseline | -0.442\* | -0.725\* | -0.889\* | -0.880\* |
| M2−M5 MPC beyond fallback | +0.072\* | +0.169\* | +0.240\* | +0.164\* |
| M3−M2 behavioural supervision | +0.165\* | +0.279\* | +0.436\* | +0.510\* |
| M3−M7 allocation-aware selection | -2.070\* | -2.990\* | -1.605\* | -1.911\* |
| M3−M4 post-allocation check | +0.000 | +0.000 | +0.000 | +0.000 |

Differences in metres of post-onset position RMSE on matched scenario draws; negative favours
the first method. `*` marks a 95% episode-bootstrap interval excluding zero.

**Consistency with Table I.** The hardware reported learned-versus-zero-context RMSE
reductions of 14.0% (actuator 70%), 40.6% (actuator 30%) and 57.9% (half-camera occlusion). The
corresponding simulated reductions of M2 over the same zero-context comparator are healthy 27%, actuator 50%, perception 29%, combined 34%.
Same sign in every condition and the same order of magnitude. This is reported as consistency
of direction, **not** as replication: the fault populations, estimator and task differ, and the
hardware trials ran an earlier controller.


---

## §4 Frozen method definitions

**IMPLEMENTED.** Explicit IDs in code, tables and logs. M4 retains source eligibility,
first-action screening, solver-failure handling and command admissibility, and disables only
the post-allocation decrease test. M5 uses the same allocation-aware realisation as M3, so
the MPC comparison differs by the optimisation alone.

Two IDs are **new**, because this campaign departs from the manuscript in exactly two places
and the plan's standard is that each declared change carries its own measured effect:

| ID | Definition | Measured effect vs M3 |
|---|---|---|
| M7 | M3 without allocation-aware command selection: the affine or optimised wrench is requested directly | -2.990 to -1.605 m; M3 better in 4/4 |
| M8 | M3 with the manuscript's allowance-free first-action condition restored | -0.157 to +0.011 m; M3 better in 1/4 |

M8 also shows what the allowance-free condition costs in attribution: the MPC candidate
reaches the actuators on only 20%-39% of steps under it, against 81%-99% for M3.

**Outstanding.** The one-page method-to-equation map for Eqs. (2), (3), (7), (8) and (15)-(19)
is not written, and the M1 arm is still broadcast from a single training seed against three
dynamic-context seeds (recorded as `broadcast_side` in the artefact rather than hidden).

---

## §5 Simulation implementation corrections

### S0.1 One canonical learned model — **NOT IMPLEMENTED**

No credit claimed. There is still no single canonical `f_theta(x_hat, u_nom_tx, z)` shared by
training targets, feedforward, affine prediction, derivative construction and mismatch
evaluation, and the state-ordering permutation between manuscript and repository has not been
implemented and tested. The residual is still evaluated once and held across the horizon, which
the plan correctly says is not Eqs. (7)-(8).

This is now the largest remaining gap, and it is the most likely explanation for the M3−M5
result: MPC planning is the one component whose value depends on the horizon prediction being
right, and the horizon prediction is the part still not implemented as specified.

### S0.2 Implement the stated optimisation — **PARTIAL**

**Done.** The first-action decrease condition of Eq. (15) is now enforced rather than checked
afterwards. Because the feasible set `{u : ||A e + B(u-u_r) + d_r||_P <= rho}` is convex, the
declared architecture is a proposal generator followed by an exact projection onto the verified
set: with `M = P^{1/2}B`, the projection solves `min ||u-u_0||^2` subject to `||M u + c|| <= rho`
by bisection on a scalar dual, each iteration a 3x3 solve. Input admissibility is enforced on
every transmitted command against the true reachable set.

**A decisive negative finding.** The projection also reports when the feasible set is EMPTY, and
on the allowance-free condition it is empty at **66.6%** of the states visited in closed loop.
That is exact infeasibility — no admissible command satisfies the inequality — not a failed
search. Eq. (15) as written is therefore not implementable on this vehicle; see the manuscript
changes below.

**Outstanding.** The componentwise pseudo-Huber objective of Eq. (16) is not implemented as
such; predicted-state region and terminal membership are not enforced across the horizon; and
verifying the first action does not make the whole returned trajectory a feasible solution of
Eq. (15), which the report states rather than glosses.

### S0.3 Causal execution and reference bookkeeping — **PARTIAL**

**Done.** Software-only `commit()` and evaluator-side `realize()` consuming exactly one hidden
fault slot are retained (gates 2.4d/2.4f). The reference bug the plan identified is fixed: the
runner stored `ref_prev[1]` in BOTH `log.ref` and `log.ref_next`, so the "current" reference was
actually the successor and any analysis differencing the two saw an identically zero reference
increment. `log.ref` now stores `r_now`. Only `ref_score` feeds reported metrics, so no scored
quantity moved.

A correction to our own previous reply: it claimed these two fields were already stored
separately. They were not. The plan's reading was right.

**Outstanding.** H+1 physical states and H+1 timestamped estimates are not retained as a checked
invariant, and estimator update timing is not logged per command.

### S0.4 Validate the isolated post-allocation branch — **PARTIAL**

The plan asks first what the allowance bounds, before manufacturing a rejection. Answering
that question resolves the branch:

The sufficient redundancy condition is `sup ||B(u_tx - u*)||_P <= eta` over feasible
candidates. Measured on this vehicle the allocation error is **persistent** (ratio exactly
1.000 over 400 steps at fixed request) and about **6.3%** of the commanded correction, while the
decrease inequality admits **0.94%** at λ≈0.99. So the uniform bound does NOT hold at the
design η, and the additive model is the wrong one.

Under the declared modification — the allowance appears on both the first-action and the
allocated-action right-hand sides, because both are evaluated on the same realised command —
passing the first implies passing the second by construction. The isolated effect is therefore
+0.00000 m, and it is reported as **verified redundancy given the screening that
precedes it**, explicitly distinguished from mere empirical inactivity. We did not shrink an
allowance to obtain a favourable ablation, and no hardware experiment disables this check.

**Outstanding.** The plan's five-row branch table is not yet driven by constructed software
fixtures with an independent evaluator reconstructing gate premises from saved values. Gates
4.6a-4.6e cover parts of it, but they are not that table and the controller's own Boolean
verdicts remain the primary evidence for some rows.

---

## §6 Shared metrics

### 6.1 Endpoints — **IMPLEMENTED**

Physical state scores outcomes; the controller's checks use the estimate. Primary endpoint is
post-onset position RMSE, declared before evaluation, with full-episode RMSE secondary.
Completion requires the **final** intended target held for the declared dwell. The 0.662 m
recovery threshold stays a separately labelled baseline-relative diagnostic.

One physical finding the plan's tolerance discussion invites. The allocator reaches its first
nonzero thrust at **0.288 N** — nearly a third of full authority — with a grid spacing of about
0.093 N above that. A persistent half-cell bias of 0.046 N against a usable proportional gain
of 0.5-2 N/m implies a steady offset of roughly 0.02-0.09 m, so the declared 0.15 m tolerance
sits close to the quantisation floor rather than comfortably above it. We did **not** change the
specification after seeing results; it is retained as declared, and this is recorded as the
physical reason completion is hard.

### 6.2 Recovery ordering — **IMPLEMENTED**

- Gate `5.1a`: **PASS** — 6 constructed traces (always inside; outside then return; leaves and never returns; leave then return; dwell-then-excursion; truncated window) agree with the declared ordering on every asserted field
- Gate `5.1b`: **PASS** — a trace inside tolerance across onset for longer than the dwell and then permanently thrown out is recorded as mode=reacquisition, success=False, reason=no_qualifying_dwell_after_excursion. The reviewed scorer returned reacquired=True with recovery_time=0.0 on this trace, crediting a return before the departure it was recovering from.

The plan's pseudocode is implemented literally in `score_recovery`: membership from the declared
tolerance, clock at onset, maintenance only when inside at onset with a complete window and no
later excursion, otherwise locate the excursion and search for a qualifying dwell strictly
after it. Both clocks (`t_from_onset`, `t_from_excursion`), both dwell endpoints, and
`departed_again` are recorded, and an incomplete window is **censored** rather than credited as
maintenance. The dwell is 21 observations, since 2 s at 10 Hz spans 20 intervals; the previous
20-observation dwell silently asked for 1.9 s.

### 6.3-6.4 Fair horizons and logging schema — **PARTIAL**

Identical task duration, deadline and reference policy across methods; position-triggered
switches are recorded rather than claimed identical; failures stay in the denominators.
Complete decision latency and deadline status are now logged (§12). Vicon validity criteria and
the attempt ledger are hardware items and are not applicable here.

---

## §9 Diagnose before scaling — **DIAGNOSED**

### S1.1 Supervisor dominance

The plan asked which of four causes it was: fallback failing decrease, state outside the
admitted region, solver infeasible, or candidate failing first-action screening. Independent
counters were added for each, which the previous single "ineligible" counter could not separate.
Measured over 4,800 control steps before the fix:

| Cause | Share of steps |
|---|---|
| fallback command judged inadmissible | **49.6%** |
| fallback failed the decrease test | 2.8% |
| state outside the eligible radius | **0.0%** |
| solver failure or deadline | 0.0% |

So it was one cause, and it was a defect: the admissibility budget, not the gate, not the
decrease test, not the solver. Correcting it moved eligibility from 48.2% to 96.2% of steps.
We changed one diagnosed cause at a time and did not enlarge the gate or the allowance to
improve the MPC percentage. The supervisor rule itself is unchanged and identical across methods.

### S1.2 Transfer failure — **PARTIAL**

Transfer is re-evaluated under the corrected controller. Held-out reference-family position RMSE in metres, by fault condition:

| Method | actuator | combined |
|---|---:|---:|
| HW | 0.373 | 1.303 |
| M1 | 0.352 | 0.859 |
| M2 | 0.375 | 0.972 |
| M3 | 0.387 | 0.899 |

The held-out family remains harder for every method, including the hardware-matched
comparator, so this is a property of the reference family and not of the learned residual
alone. That is the reason the attribution below stays open.

Reference feasibility under the actual impulse authority and the action-source changes relative
to in-distribution cases are now inspectable, but the coordinate/wrapping audit, the frozen-
context multistep prediction study and the normalised-input range check are not done. The
attribution therefore remains open, and we do **not** claim the neural residual alone causes it.

---

## §11 One useful recovery-bound demonstration

**NOT IMPLEMENTED — no accepted region survived, and the reason is now identified.**

No accepted region on this domain; the calibrated prediction bound exceeds the frozen budget.

The failure is no longer a bare unsuccessful sweep. Two obstructions are quantified:

- **Reference defect.** b_r is 29.7 on the hardware-matched `step` family against an input
  radius of 1.4, because that family contains a 1.0 m setpoint jump inside one 0.1 s sample.
  No bounded input follows a discontinuous reference, so no (P, K, λ) cell could ever have
  certified it. On a smooth feasible reference the same quantity is 0.096; on a held setpoint,
  exactly 0.
- **Contraction rate.** Deadbeat gains for this plant are ≈2500 N/m and saturate 0.96 N at
  0.4 mm of position error, so per-step contraction faster than λ≈0.99 is physically
  unusable and 1/(1−λ)≈100 amplifies every per-step term.

We report the failed sufficient-condition search under its proper scope. It does not prove
physical impossibility, and it does not establish a necessary mass-identification tolerance.

### Why the guarantee is not useful here, with a mechanism

The plan asks for interpretable physical bounds and nontrivial eligible operation, not just a
positive radius. Converting the verified radii into physical units explains the whole result:

| Design | λ | R_max | position | velocity | yaw |
|---|---:|---:|---:|---:|---:|
| λ₀=0.96, w=1e+06 | 0.9774 | 2.596 | 9.0 cm | 4.45 cm/s | 20° |
| λ₀=0.97, w=1e+06 | 0.9905 | 4.432 | 15.5 cm | 5.69 cm/s | 36° |

These are **pure-axis extremes**; the region is their intersection and so jointly smaller.

Against that, the measured actuator floor: the first reachable thrust above zero is
**0.288 N**, which is 30% of full authority, with a 0.093 N grid above it. A
persistent half-cell bias against a usable proportional gain sustains a steady offset of
2-9 cm.

So the certified ball is **the same size as, or smaller than, the vehicle's own
quantisation-driven limit cycle**. The closed loop cannot remain inside the region it
certifies, which is exactly why recovery-active coverage is ~0% and why a calibration run
over those episodes scores zero active transitions. A nonempty region that the vehicle never
occupies certifies nothing about the vehicle, and we do not report it as a success.

**This is a mechanism, not a shrug, and it is actionable.** The obstruction is actuator
quantisation relative to the achievable per-step contraction — not the theory and not the
search. What would make the guarantee useful is finer thrust granularity: a smaller minimum
impulse bit, a higher PWM rate, or proportional thrusters. Stating that requirement is a more
useful contribution than an empty sweep, and it is a concrete answer to the reviewer question
"is the theoretical construction useful?"

---

## §12 Compute and mechanism measurements — **PARTIAL**

Complete decision latency is now timed across context inference, the residual, feedforward,
fallback allocation, optimisation, allocation-aware selection and every check — not the
solver's reported duration, which omitted everything the learned components add.

| Condition | p50 | p95 | p99 | max | deadline misses |
|---|---:|---:|---:|---:|---:|
| healthy | 14.6 | 22.5 | 33.8 | 53.7 | 0.00% |
| actuator | 14.5 | 21.6 | 29.1 | 50.4 | 0.00% |
| perception | 13.6 | 21.6 | 30.2 | 49.4 | 0.00% |
| combined | 13.6 | 22.8 | 33.8 | 54.7 | 0.00% |

All figures are milliseconds against the 100 ms period, measured on a **simulation
workstation**. The plan is explicit that a real-time claim needs the deployment computer, so
this supports feasibility of the computation, not a flight timing claim. Cold starts are not
separated from steady operation.

Action fractions use a common denominator of all control steps, with first-action rejection,
post-allocation decrease rejection, input-admissibility rejection, solver/deadline fallback and
supervisor kept separate. The earlier 3-4% input-budget rejection is no longer described as the
decrease-check rejection.

---

## Manuscript and theorem changes these measurements force

The plan's §14 asks for contribution statements aligned to observed effects. Four changes are
needed. Two are scope restrictions, one is an equation change, one is a withdrawn claim.

### 1. Eq. (15): the first-action condition needs the implementation allowance

**Change.** Give the first-action decrease condition the same allowance η as the allocated-action
condition, or equivalently state both as one condition on the realised command.

**Why.** The manuscript's allowance-free form presumes the planned first input is applied
exactly. It is not: the command reaches the thrusters through a duty-quantised allocator whose
error is persistent and about 6.3% of the commanded correction. With no allowance the feasible
set is **empty at 66.6% of visited states** by exact projection. An unimplementable constraint
is worse than a weaker one, and a reviewer who tries to implement Eq. (15) as written will find
this immediately.

**Consequence to state plainly.** Eqs. (15) and (18) then become the same test, so the
post-allocation check is redundant *by construction*. Report it as verified redundancy over the
declared domain and drop any claim of a measured performance benefit from it.

### 2. The recovery guarantee holds on smooth/station-keeping references, not on setpoint jumps

**Change.** State the certificate over a domain of feasible references and exclude discontinuous
setpoint changes explicitly.

**Why.** b_r = 29.7 for a 1.0 m jump in one 0.1 s sample versus an input radius of 1.4 — the
condition fails by a factor of 20 for a purely kinematic reason. The same quantity is 0.096 on a
smooth feasible reference and 0 on a held setpoint. This is a scope statement the theory always
needed, not a retreat: no bounded-input controller can contract toward a discontinuous reference.

### 3. Replace the uniform allocation-error allowance with an online reachability premise

**Change.** Where the manuscript assumes a uniform bound `sup ||B(u_tx − u*)||_P <= eta` over all
feasible candidates, substitute the premise that a **reachable** transmitted command satisfying
the decrease inequality exists, verified online each step.

**Why.** The uniform bound is false here (6.3% versus the 0.94% admitted), so any theorem resting
on it is unsound for this vehicle. The replacement is *weaker, checkable, and satisfied*: the
allocation map is deterministic and computed before transmission, so the controller can select
the request whose realisation satisfies the inequality. Measured satisfaction rises from 24-49%
to 92-100%. This is also the campaign's clearest positive engineering contribution, and it has
its own ablation (M7).

### 4. Withdraw the behavioural-supervision benefit claim

**Change.** Present the behavioural loss as an ablation that did not help (+0.165 to
+0.510 m, worse in 4/4 conditions, development weight selected at zero), and rest the
context-learning contribution on dynamic context versus trained constant context, which is
supported. Per the plan, do not replace an unsupported specific claim with an equally
unsupported broad one.

### Also narrow, do not delete

- **Planning.** M3 does not beat M5 under matched everything, so the MPC claim must be narrowed to
  what the architecture actually contributes. Note honestly that S0.1 is outstanding and the
  horizon prediction is exactly the part not yet implemented as specified, so this is a result
  about *this* implementation of planning.
- **Hardware.** Table I stays the primary physical evidence and is untouched. The simulation
  repairs change no recorded hardware datum. The learned-versus-zero-context direction in
  simulation now agrees with the hardware direction, which is worth stating as consistency, not
  as replication.

---

## What is deliberately not claimed

| Plan item | Status |
|---|---|
| §7-8 hardware ledger, provenance, prospective matched campaign | **NOT APPLICABLE** — needs hardware and records this work has no access to. The N=10 vs N=12 horizon must still be resolved from the flight configuration; simulation shows the choice is not load-bearing but that does not establish equivalence. |
| §5/S0.1 canonical model, context-conditioned feedforward, Eqs. (7)-(8) across the horizon | **NOT IMPLEMENTED** — the largest remaining gap, and the most likely cause of the M3−M5 result |
| §5/S0.2 componentwise pseudo-Huber, predicted-state region and terminal membership | **NOT IMPLEMENTED** |
| §5/S0.4 constructed branch fixtures with an independent evaluator | **PARTIAL** |
| §10/S2 five training seeds; balanced seeds for the constant-context arm | **PARTIAL** — three seeds, M1 still broadcast |
| §13 corrected architecture figure; `oracle` relabelled `hand-tuned context`; neural-ODE literature | **NOT IMPLEMENTED** |

---

## §14 Where this leaves the paper

On the plan's own decision table, this is the **"dynamic context helps, behavioural loss does
not"** row, plus **"post-allocation check remains inactive"** and **"MPC does not improve over
matched fallback"**, and **a certificate that remains empty, with its emptiness explained**. The
defensible contribution statement is:

1. Multimodal context inference from recent history improves fault-tolerant tracking over a
   trained constant-context representation and over nominal prediction, under matched controller,
   cost, constraints, allocator, gate and supervisor — in simulation, and consistently with the
   direction of the hardware result.
2. Allocation-aware command selection makes a per-step decrease condition implementable on a
   pulsed, low-authority thruster system, where the uniform additive allowance it replaces is
   provably unattainable. This is new, measured, and ablated.
3. The hardware demonstration remains the primary physical evidence for coupled actuation and
   perception adaptation.
4. Negative, useful results: the behavioural objective does not help; the post-allocation check
   is redundant given the screening ahead of it; MPC planning does not beat its matched
   fallback in this implementation.

That is a coherent RA-L paper. It is a different paper from the one whose abstract advertises a
behavioural loss and a general recovery guarantee, and the honest version is the one that will
survive review — a reviewer who reimplements Eq. (15) as written will find it infeasible at two
thirds of states, and that is much worse to discover in review than to state up front.


# Updated spacecraft results: what to retain and what to complete for RA-L

**Date:** 18 September 2026  
**Reviewed version:** [Sc_sim_env, commit 4f967a40f6477724258b53acf9cf6464edacddcf](https://github.com/baaqerfarhat/Sc_sim_env/tree/4f967a40f6477724258b53acf9cf6464edacddcf)  
**Results:** [results/results.md](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/results/results.md)  
**Purpose:** A detailed retention, correction, and experiment plan following the updated simulation campaign. This updates the priorities in `Spacecraft_Simulation_Corrections_and_RAL_Validation_Plan.md`. Completed repairs should be preserved.

## 1. Recommended direction

Keep the spacecraft hardware experiments as the main physical demonstration. Keep the corrected simulator, training pipeline, checkpoints, and recorded results. Complete the implementation of the method described in the paper, then run a focused comparison and recovery demonstration.

The updated campaign has made the evidence more informative. It has not yet demonstrated the behavioral-supervision benefit, the value of MPC beyond feedback fallback, or a useful numerical recovery certificate. Some remaining implementation differences prevent treating these outcomes as definitive tests of the manuscript’s formulation.

Do not expand the theory or launch another broad sweep yet. The next work should establish that:

1. The simulation executes the same predictor, feedforward, MPC, and acceptance logic that the manuscript describes.
2. The comparisons isolate the claimed contributions.
3. Success means meaningful completion or recovery of the actual task.
4. Any recovery guarantee has verified premises, validated error envelopes, and useful physical scope.

Preserve unfavorable results. If a corrected final experiment still does not support a contribution, revise the claim. A failed validation cannot be repaired by changing only its narrative.

### Use four result categories

- **Retain:** corrected infrastructure, definitions, or evidence that remains valid under its stated scope.
- **Retain as development evidence:** valid observations of the current implementation that should not be presented as final validation of a different controller.
- **Regenerate after a specified change:** quantitative outputs affected by corrected dynamics, controller logic, metrics, or model definitions.
- **Remove or replace the claim:** unsupported interpretation. This never means deleting the underlying unfavorable data.

## 2. What to keep from the new campaign

| Item | Decision | Where it belongs | Required qualification/action |
|---|---|---|---|
| Nominal transmitted command separated from hidden physical actuation | Retain | Implementation; short methods statement | Preserve the repaired information boundary |
| Physical thrust rotated using true attitude | Retain | Simulator implementation and verification | Retain integration/refinement and rotation checks |
| Trial allocation without allocator-memory mutation | Retain | Controller implementation; repository tests | Keep candidate/fallback trial memory identical |
| Failing fallback causes ineligibility in the enforced policy | Retain and complete | Controller logic | Complete the other eligibility conditions and correct the no-check mode |
| Matched physical probe groups and nominal-command response regression | Retain | Learning-method description and code | Document the exact reset/warm-up/noise protocol |
| Genuine training reference-family labels and separate training RNG streams | Retain | Training protocol | Maintain parent-episode splits and an untouched transfer population |
| Stage 0 semantic checks and open-loop verification | Retain and extend narrowly | Repository; concise paper statement | Sample checks are software validation, not continuum certification |
| Hardware parameter provenance and estimator surrogate | Retain | Simulation setup | Distinguish measured, code-derived, fitted, and assumed quantities |
| Current learned checkpoints and normalization objects | Retain | Versioned artifacts; controller development | Retraining is conditional on whether inputs, targets, architecture, or training population change |
| Loss-weight selection choosing zero | Retain | Ablation evidence if supervision remains a contribution | State the selection metric and distinguish the selected model from the positive-weight ablation |
| Full versus no-impact tracking results | Retain as development evidence | Versioned report; replace final table after controller alignment | They describe the current implemented controller |
| No-impact versus trained constant context | Retain the comparison and provisional finding | Main paper after completion | Evaluate the other existing constant-context checkpoints |
| Full versus fallback-only | Retain the comparison and adverse finding | Mechanism analysis after regeneration | Do not infer equivalence from a nonsignificant difference |
| Large full versus no-check performance gap | Retain as a combined-safeguard diagnostic | Development report | Remove the isolated post-allocation-check interpretation until the ablation is repaired |
| Action-source fractions | Retain and complete | Main mechanism table/figure | Account for every action source, including first-action rejection |
| Strict position/yaw tolerances and low success | Retain | Main performance evaluation | Correct final-waypoint and post-fault semantics |
| Held-out-reference failure | Retain | Limitation/diagnostic result | Diagnose its cause; do not hide it or attribute it to the residual without isolation |
| Empty certificate search | Retain as exploratory evidence | Repository; brief paper limitation if relevant | It is not a proof of physical impossibility or a verified boundary |
| Horizon/authority sweeps | Retain in repository | Supporting diagnostics | No need to expand before central comparisons work |
| Existing hardware results | Retain as hardware evidence | Main Experimental Results section | Simulation repairs do not retroactively alter recorded hardware data; verify implementation provenance |
| Old report paragraphs contradicted by new outputs | Replace | Generated report and manuscript | Correct interpretation and source consistency |

The corrected campaign should remain immutable under its commit identifier. Give subsequent campaigns their own code, data, checkpoint, and configuration identifiers. Do not pool results generated by materially different controllers into one mean.

## 3. What the current numbers actually support

These numbers are observations of commit `4f967a4`. They are not a prediction of the final corrected method’s performance.

### 3.1 Behavioral supervision: keep the negative result and its uncertainty

The primary comparison is positive-weight `full` minus prediction-only `no_impact`. Positive values favor `no_impact`.

| Condition | Difference in primary RMSE, m | 95% interval crossed over training seeds and episodes |
|---|---:|---:|
| Healthy | +0.0517 | [−0.0028, +0.1071] |
| Actuator | +0.1153 | [−0.0100, +0.2264] |
| Perception | +0.0453 | [−0.0207, +0.1041] |
| Combined | +0.0513 | [−0.0130, +0.1107] |

The faulty conditions use post-onset position RMSE. Healthy episodes use full-episode RMSE because they have no fault onset.

**Keep this conclusion:** no demonstrated behavioral-supervision benefit under the evaluated settings; all point estimates are adverse, while the broader training-population effect remains uncertain with three seeds.

**Do not say:** the loss has been universally disproved, or all four effects are significant across training randomness. The episode-only intervals answer a narrower question conditional on the evaluated checkpoints.

The development grid `{0, 0.01, 0.1, 1}` selected $\lambda_I=0$ using one-step prediction error for seed 0. The reported `full` model uses $\lambda_I=1$ as a positive-weight ablation.

Keep the complete grid and the selected-zero outcome. Do not label the positive-weight model as the selected method. If the intended objective is control or transfer, use a declared development control/transfer criterion when selecting the coefficient, and evaluate the resulting choice on fresh final test data. The present grid does not settle every possible control tradeoff.

### 3.2 Changing context: preserve the clean comparison

The clean comparison is `no_impact` versus trained constant context: both use prediction losses without behavioral supervision.

| Condition | No-impact minus constant-context primary RMSE, m |
|---|---:|
| Healthy | −0.2150 |
| Actuator | −0.4048 |
| Perception | −0.0649 |
| Combined | −0.1644 |

This is the most promising representation result in the new campaign. However, the constant model is evaluated only for training seed 0 and broadcast against the three dynamic-context models.

**Required addition:** evaluate the already-trained constant-context checkpoints for seeds 1 and 2 under the final controller. No new architecture or large training campaign is needed for this comparison.

Do not use `full` versus constant context as the isolated dynamic-context comparison; it changes both the context representation and the behavioral objective.

### 3.3 MPC beyond fallback: preserve the question and adverse outcome

Current `full − fallback_only` primary RMSE differences are:

| Condition | Difference, m | Interpretation |
|---|---:|---|
| Healthy | −0.0334 | No demonstrated improvement |
| Actuator | +0.0015 | No demonstrated improvement |
| Perception | +0.0662 | Fallback-only performs better in the reported comparison |
| Combined | +0.0217 | No demonstrated improvement |

Retain these observations as a reason to test whether MPC adds useful planning. Do not claim that MPC is inherently unnecessary or that the two methods are equivalent.

The fallback’s current feedforward is nominal. Its learned residual is computed but discarded, and its trajectories are identical across model seeds. Report that honestly. Repeating an identical checkpoint-independent fallback three times is not additional independent evidence.

After implementing context-conditioned feedforward, rerun this comparison with exactly the same feedforward, gain, allocator, gate, and supervisor on both sides. Only MPC candidate selection should differ.

### 3.4 Practical performance: preserve the low success and correct its meaning

For `full`, the recorded current-threshold successes are:

| Condition | Any qualifying dwell during the episode | Within tolerance for the final two seconds |
|---|---:|---:|
| Healthy | 10/180 | 3/180 |
| Actuator | 3/180 | 0/180 |
| Perception | 2/180 | 0/180 |
| Combined | 1/180 | 0/180 |

The thresholds are 0.15 m position, 5 degrees yaw, and two seconds. They are provisional declared study values, not measured spacecraft requirements.

The first column is not final-task completion: the code allows a dwell at the current waypoint, possibly before fault onset. The second column also needs final-waypoint confirmation.

Retain the evidence that practical accuracy is poor. Correct the endpoint definition before presenting task success. Do not summarize all methods and repeated checkpoints as one overall success percentage.

The full controller sends MPC candidates on approximately 8–13% of samples and supervisor commands on approximately 42–65%. These figures explain why the behavior of the supervisor must be inspected directly.

### 3.5 Transfer: preserve the failure and investigate attribution

On the held-out reference family, learned variants have roughly 4.7–5.0 m RMSE, while the hardware comparator has approximately 0.37–1.35 m. The positive behavioral coefficient improves slightly over no-impact within that failing regime, but that is not useful task transfer.

Keep the failure in the development record and eventual limitations/results as appropriate. Do not conclude automatically that the neural residual alone caused it: reference generation, feedforward, eligibility, supervisor behavior, model/input mismatch, and prediction can all contribute.

## 4. Corrections to complete before the next major run

### 4.1 Unify physical fault-slot execution

**Files:** `scsim/plant.py`, `scsim/runner.py`, and policy transmission in `scsim/controllers.py`.

The shorthand path used in data generation applies the hidden fault before advancing its counter. The policy path advances the counter before applying the hidden fault. Identical first packets at a firing fraction of 0.7 therefore fire in one path and skip in the other.

Use one execution contract:

1. The policy selects a pre-fault command packet using controller-visible information.
2. Commit its software allocator-memory update once.
3. The evaluator applies the hidden effect for the designated physical slot.
4. Advance that hidden slot exactly once.
5. Integrate actual pulses using true state.

Separate software allocator commit from hidden fault-schedule advancement. Both training and policy runners must use the same physical execution function. Hidden quantities must remain unavailable during action selection.

**Completion check:** for fixed packets, initial fault state, and onset, both execution paths produce identical physical pulses and counter sequences over several slots. Test nontrivial firing fractions and initial phases. Retain the nominal-versus-physical invariance tests already implemented.

**Reuse implication:** if the chosen physical convention matches existing training generation, those training transitions need not automatically be regenerated. Closed-loop evaluations using the mismatched policy path must be regenerated where the fault occurs.

### 4.2 Make the no-check variant a single-component ablation

**File:** `scsim/controllers.py::LearnedContextPolicy.act`, particularly branches near lines 301, 338, and 346.

Replace the shared `check_mode` control over multiple safeguards with independent internal decisions for:

- Source eligibility and supervisor selection.
- Candidate feasibility, including the first-action condition.
- Solver/deadline failure.
- Post-allocation candidate acceptance.

For the no-post-allocation-check variant, retain the first three mechanisms. Disable only the final candidate acceptance test.

Keep checkpoint, scenario, estimator, horizon, cost, feedforward, gain, design budgets, command budget, allocator, and source gate identical within the paired comparison.

**Completion checks:**

| Forced situation | Full policy | No-post-allocation-check policy |
|---|---|---|
| Source ineligible or fallback fails | Supervisor | Same supervisor |
| Optimizer fails or misses deadline | Stored passing fallback, under the declared rule | Same handling |
| First-action feasibility fails | Stored passing fallback | Same handling |
| Feasible candidate passes post-allocation check | Candidate | Same candidate |
| Otherwise feasible candidate fails only post-allocation check | Stored passing fallback | Candidate, with failure logged |

The final row intentionally bypasses the corresponding guarantee and belongs only in simulation. If command admissibility is also part of the disabled combined check, state that explicitly; alternatively retain it in both arms and label the ablation precisely as disabling the post-allocation decrease test.

Keep the old no-check result as a comparison against multiple disabled safeguards. Remove its claim to isolate the allocated-command check.

### 4.3 Use one learned model consistently throughout the controller

**Files:** `scsim/controllers.py`, `scsim/mpc.py`, `scsim/certificate.py`.

Provide one canonical evaluation of

$$
f_\theta(\hat x,u,z)=f_0(\hat x,u)+d_\theta(\hat x,u,z),
$$

where $u$ is the nominal-equivalent command for the transition being predicted.

Use that evaluator for:

- Training prediction targets.
- Feasible feedforward selection.
- Horizon prediction.
- Affine model construction.
- Post-allocation checking.
- Numerical derivative/envelope analysis.

Passing the previous transmitted input to a frozen residual is still a different prediction model. For the manuscript’s affine controller, construct

$$
\bar f(e,u)=\Phi_{r^+}\!\left(f_\theta(\Phi_r^{-1}(e),u,z)\right),
$$

$$
d^r=\bar f(0,u^r),\qquad
A=\left.\frac{\partial\bar f}{\partial e}\right|_{0,u^r},\qquad
B=\left.\frac{\partial\bar f}{\partial u}\right|_{0,u^r}.
$$

Include the residual and coordinate transforms in the derivatives. Keep an explicit state-order/frame convention: the repository uses [px, py, vx, vy, yaw, yaw rate], which must be mapped consistently to the manuscript’s matrices and weights. Freeze the inferred context over the planning horizon as specified in the paper.

The post-allocation check uses the affine $A,B,d^r$ derived from this canonical model, as in the manuscript; a direct nonlinear-successor norm is not a silent replacement for that check.

The feedforward selector must use this model and return a feasible command with its evaluated defect. The fallback-only variant must use the identical feedforward and feedback construction.

**Completion checks:** compare model evaluations across modules on identical inputs; verify derivative code with directional differences away from nondifferentiable branches; confirm changes in context can affect the feedforward/model where the architecture permits. Numerical derivative spot checks validate implementation, not a continuum bound.

**Reuse implication:** existing checkpoints can be used to implement these interfaces. Retraining is necessary only if the model architecture, input convention, targets, regularization, or training distribution changes.

### 4.4 Complete candidate feasibility and source eligibility

The current postsolve first-action screening is not sufficient to implement all manuscript constraints.

For the latest formulation, enforce or independently verify:

$$
u^r_i+\delta u_i\in\mathcal U,\qquad
e_i\in\mathcal C,\quad e_N\in\mathcal C,
$$

and

$$
\|A_ke_k+B_k\delta u_0+d^r_k\|_P
\le\lambda\|e_k\|_P+\|d^r_k\|_P.
$$

The first-action optimization condition excludes the allocation allowance $\eta$. The later allocated-command decrease test includes it.

Verify the affine prediction-dynamics equalities and numerical solver residuals as well as the inequalities. Either solve the stated constrained problem or clearly identify an approximate proposal generator followed by verification of all required constraints. A failed proposal is not a feasible MPC solution and must trigger the declared fallback.

Source eligibility must include verified model/context/reference/allocator domains and required corridor/chart conditions, as well as the state radius and passing fallback. When those verification objects are absent, describe an operational supervisor; do not label its radius/fallback flag as theorem eligibility.

Implement the stated componentwise pseudo-Huber objective or a derived valid surrogate. Aggregating errors over the horizon and reweighting the inherited quadratic cost does not automatically minimize the manuscript objective. Preserve the distinct terminal cost and remove unproved monotonicity statements.

Do not make the acceptance test permissive merely to increase the MPC action fraction. Diagnose why proposals fail and whether the model, feasible set, reference, and horizon are consistent.

### 4.5 Complete reference, endpoint, and action bookkeeping

- Save `r_now` and the committed `r_next` separately.
- At the next sample, retain the previously committed current reference. A new waypoint decision schedules a future uncommitted reference.
- If reference replacement is allowed, account for it in the transition mismatch.
- For $H$ transmitted commands, retain $H+1$ physical states and estimates.
- Record candidate, fallback, and transmitted-command slacks separately.
- Include `fallback_first_action` in aggregate action-source counts.
- Check that candidate, first-action fallback, post-allocation fallback, solver fallback, and supervisor fractions sum to one.
- Record full decision latency and deadline status, not only the QP solver’s reported duration.

These records are needed to explain performance and to evaluate the theorem’s transition errors.

## 5. Correct performance scoring and diagnose the poor behavior

### 5.1 Define task completion and recovery separately

For the waypoint task, task completion should require the final intended waypoint and heading, held within the declared tolerances for the dwell time before the deadline.

For post-fault recovery, use a separately declared onset-relative criterion. A success before the fault must not count as recovery after it.

Distinguish:

- **Maintenance:** the vehicle was within the required tolerance at onset and remains compliant for the stated assessment period.
- **Reacquisition:** a relevant excursion occurred and the vehicle subsequently returns for a qualifying dwell.
- **Task completion:** the original final objective is achieved, with any ordering requirements.
- **Theoretical entry:** the error enters a smaller region during an uninterrupted eligible interval, using the theorem’s own starting condition and clock.

Keep full-episode RMSE for continuity with hardware tables, and post-onset RMSE/peak for impairment response. State the scoring reference and window for each.

The current secondary recovery threshold is approximately **0.662 m**, distinct from the 0.15 m task tolerance. Retain it only as an explicitly labeled baseline-relative diagnostic. Do not merge the two success definitions in one column.

Where complete traces exist, rescore them without rerunning simulation. Where only aggregates or selected traces were saved, do not reconstruct missing task outcomes from averages; compute the corrected metrics in the next run.

### 5.2 Diagnose supervisor dominance on a small development set

Choose a few prespecified development scenarios from healthy, actuator-only, and combined conditions. Include a typical case and a recorded failure. Plot:

1. Physical position/yaw error against the original task.
2. Estimated error and physical estimation error.
3. Eligibility reasons and action source.
4. Candidate/fallback/transmitted slacks.
5. Nominal transmitted input and physical actuator response.

Identify when progress toward the task stops. A velocity-damping supervisor may reduce motion without advancing toward the reference. That is a possible mechanism to investigate, not an established explanation of every failure.

Separate reasons for low candidate use:

- State outside the admitted region.
- Context/reference outside the verified domain.
- Fallback rejection.
- Solver failure or deadline miss.
- Predicted region/input infeasibility.
- First-action rejection.
- Post-allocation rejection.

Change only the subsystem implicated by the diagnostics. If changing the supervisor or reference rule, freeze and report the new hybrid policy and rerun affected performance/calibration episodes.

### 5.3 Diagnose transfer before adding more transfer trials

Use the existing failed family as development evidence after inspecting it. It is no longer an untouched final test for changes motivated by its failures.

Run these focused checks:

| Diagnostic | Question answered |
|---|---|
| One-step and multistep prediction on the same held-out histories | Does the learned predictor fail before control decisions are involved? |
| Nominal-recovery versus learned-recovery under identical supervision | Does learning worsen transfer when the control framework is matched? |
| Feedforward feasibility and evaluated reference defect | Is the new reference compatible with available actuation and model? |
| Gate/action-source timeline around error growth | Does a supervisor or failed fallback dominate the failure? |
| Translation-only versus changing-heading reference diagnostics | Is the failure associated with heading/frame demand or more general reference shift? |

Keep truth and fault labels out of the online controller during these tests. A diagnostic run with additional information, if used, must be explicitly labeled and cannot become the main deployment result.

If the repair requires additional reference families in training, reserve a genuinely new final transfer family or independently specified held-out regime. Do not continue calling a family unseen after training or tuning on it.

## 6. The focused experiment package to add

### 6.1 Core comparison matrix

| ID | Variant | Purpose |
|---|---|---|
| M0 | Nominal predictor with the same recovery-controller structure | Learned predictor versus nominal model |
| M1 | Trained constant context; prediction losses only | Baseline for whether dynamic context helps |
| M2 | Dynamic context; prediction losses only | Dynamic context without behavioral supervision |
| M3 | Dynamic context with a declared positive behavioral coefficient | Behavioral-supervision ablation |
| M4 | Exact M3 checkpoint; only the specified post-allocation candidate test disabled | Allocated-command check contribution |
| M5 | Same M3 feedforward/fallback/supervisor; no MPC candidate selected | MPC contribution beyond fallback |
| HW | Hardware-matched comparator | Connection to the physical experiments |

Retain the existing adaptive MPC baseline if its tuning and input conventions are documented. It is useful but does not replace the matched component comparisons.

The primary pairs are:

- **M2 − M1:** changing context.
- **M3 − M2:** behavioral supervision.
- **M3 − M4:** the precisely defined allocated-command check.
- **M3 − M5:** MPC beyond the same fallback.
- **M2/M3 − M0:** learned prediction within comparable recovery machinery.

If development selects $\lambda_I=0$, M2 is the selected predictor under that rule. Report M3 as the positive-weight ablation. Use the selected model for a clearly labeled best-method deployment result; do not relabel it as evidence of a positive behavioral objective.

If different methods need different verified designs, use the same design procedure/budget and report the resulting physical regions. Do not claim a single-component intervention if the gain, region, or gate also changes.

### 6.2 Conditions, seeds, and sample size

Use healthy, actuator-only, perception-only, and combined conditions. Retain three matched training seeds and approximately 60 distinct scenario draws per condition as a reasonable initial final design. These numbers are planning choices, not a journal requirement or power guarantee.

Evaluate all three existing M1 checkpoints. Derive M4 and M5 from the corresponding M3 design/checkpoint. If a fallback remains truly checkpoint-independent, run it once per scenario and report that dependence correctly.

For each learned method, 60 scenarios times three checkpoints produces 180 rollouts per condition, but only 60 distinct scenario draws. Report both counts.

Keep exogenous random streams matched across methods, with separate RNGs for perception, disturbance, initial conditions, and scenario generation where needed. Controller-dependent branching must not change the external random sequence.

Use small existing development/regression cases to debug the changes. Once the method and tuning rules are frozen, use fresh final scenario seeds. Baselines in a final paired comparison must use those same fresh scenario draws.

### 6.3 Report uncertainty and practical relevance

Show seed-level means and paired differences. Report both:

- Episode intervals conditional on the evaluated checkpoints.
- Crossed seed/scenario intervals where the sampling structure supports them.

Do not present three training seeds as a precise characterization of all retraining variability. More rollouts with the same checkpoints do not address that limitation.

Specify the primary endpoint and comparison before the final test. If behavioral supervision remains a central claimed contribution, M3–M2 post-onset performance should remain visible even if it is unfavorable.

Compare effect sizes with task tolerances and success rates. A statistically detectable 0.1 m improvement inside a roughly 5 m failure regime is not useful transfer. Conversely, a small improvement can matter near a strict task threshold if task-success evidence supports it.

Keep failures in success denominators. Report recovery/completion times together with non-recovery/non-completion counts. Nonsignificance does not establish equivalence.

## 7. Complete one useful numerical recovery example

### 7.1 What to preserve from the existing analysis

Keep the corrected nominal rotation blocks, LMI/design code, distinction between actuator permission and physical thrust, and all failed search records.

Use them as development tools. The current result is: **no nonempty candidate region was found in the evaluated search with the implemented bounds and budgets**.

Do not claim:

- Universal physical impossibility.
- A necessary ±5% mass/inertia identification requirement.
- A rigorous feasibility boundary from a finite unsuccessful sweep.
- A certificate for the learned model when only nominal matrices were used.
- Attained neural sensitivity from an upper enclosure.
- Current residual inadmissibility numbers when the residual analysis is missing.

The new certificate output has `residual: {}`. Missing checkpoints or a required latent-domain file must generate an explicit unavailable-analysis status. The report must not reuse the old “603×” or “four orders of magnitude” conclusions.

### 7.2 Use one narrow operating case first

Freeze one checkpoint, one physical actuator configuration, one estimator, one held or gently varying feasible reference, and one bounded uncertainty domain.

Start inside a declared eligible region with nonzero but bounded model/plant mismatch. Check a healthy case for implementation consistency, then at least one prespecified unannounced impairment within the declared domain. A healthy-only example cannot establish fault recovery.

A held reference after its commanded jump has settled can avoid requiring one region to contain the jump itself. State that restriction. Do not claim recovery from arbitrary outside states or uninterrupted certification across excluded reference changes.

### 7.3 Establish the deterministic premises for the implemented model

Verify the context-conditioned affine model actually used online. Include residual derivatives, coordinate transformations, supported clipping branches, and the relevant reference/feedforward domain.

Replace the sampled allocation-error maximum with a sound bound over the selected region and admitted allocator memory, or explicitly restrict the claim to the pointwise checked-fallback conditions supported by the theorem. Do not claim the uniform fallback-realization lemma without verifying its premise.

Use justified numerical enclosures. The current first-order rounding estimate and sampled falsification tests are not a complete verified-arithmetic argument.

Find a design satisfying

$$
s_{\rm cert}=\frac{b_r+d_{\rm cert}+\eta}{1-\lambda}
<R\le\min(R_U,R_{\rm corridor},R_{\rm chart}),
$$

with

$$
\Delta_R=(1-\lambda)R-b_r-d_{\rm cert}-\eta>0.
$$

Report position/attitude projections in physical units. A tiny unvisited region or a steady bound larger than the meaningful task tolerance has limited practical value.

If a bound fails, identify the limiting term before changing the design. Do not launch another large Cartesian sweep by default.

### 7.4 Fit and calibrate under the frozen deployed policy

Selecting $\eta$ or $R$ by development performance is tuning. It is not final conformal calibration.

Freeze model, controller, gate, supervisor, reference policy, design budgets, and all deployment settings first. Use independent fitting data for score objects, then complete calibration episodes from the declared population under that same frozen policy.

At active source transitions, evaluate

$$
d_k=e_{k+1}-A_ke_k-B_k(u_k-u_k^r)-d_k^r
$$

with $e_k=\Phi_{r_k}(\hat x_k)$ and $e_{k+1}=\Phi_{r_{k+1}^{\rm committed}}(\hat x_{k+1})$, the actual nominal transmitted command, and the committed successor reference. This is an estimate-space prediction mismatch. Separately evaluate physical estimation errors $\tilde x=x_{\rm true}-\hat x$ at both endpoints using the source context’s score cell.

Use complete-episode maxima for each error channel. Keep inactive periods, zero-active episodes under the specified scoring convention, active exit transitions, and final successor observations. Do not calibrate only negative candidate slacks or individual correlated time samples.

Final acceptance requires

$$
\bar d\le d_{\rm cert},
\qquad
\mathcal E_{\max}\subseteq\mathcal E_{\rm cert}.
$$

Both deterministic verification and final calibration acceptance are necessary.

A suggested initial scale is 200 complete calibration episodes and 100 independent test episodes for one frozen policy/population. At $\delta_D=\delta_E=0.025$, the calibration order-statistic index is 196 for each channel with 200 episodes. This budget is illustrative and does not itself guarantee a useful certificate.

Do not pool different trained controllers into one certificate without a justified population definition. The guarantee’s probability interpretation is marginal over calibration and test randomness; do not silently convert it into a conditional claim given acceptance.

If final acceptance fails, preserve that outcome. Redesign can use it as development information, but the new design requires fresh final calibration.

### 7.5 What the positive example must show

Report:

- Verified domains and model/design identifiers.
- $P,K,\lambda$, budgets, calibrated thresholds, and acceptance.
- $s_{\rm cert}$, $R$, limiting radii, strict margin, and physical projections.
- Eligible fraction, consecutive eligible durations, and zero-active episodes.
- Envelope violations, actual-command violations, region exits, and sampled safety violations.
- Empirical entry into a smaller region compared with the theoretical eligible-start bound.
- Supervisor use and deadline failures.

A high coverage percentage with almost no eligible operation is insufficient. Sampled-state results do not imply intersample safety without an additional argument.

## 8. What to change in the report and manuscript

### 8.1 Correct the report now, without new simulations

| Current statement/problem | Required revision |
|---|---|
| “The direction and significance replicate everywhere” | State that performance is condition-dependent and healthy/actuator-only comparisons worsen for the current full controller |
| Increasing $\eta$ described as enforcing the check harder | Increasing $\eta$ relaxes the decrease inequality; eligibility and trajectory changes can also affect rejection counts |
| 3–4% rejection used to explain most actions being fallback | Report the complete candidate/first-action-fallback/post-allocation-fallback/solver-fallback/supervisor decomposition |
| “603× sensitivity” and “four orders” with n/a values | Remove until current residual-analysis outputs support a correctly qualified statement |
| “Sound certificate” alongside unverified numerical rounding | Describe the analytic enclosure, numerical approximation, and remaining verification limits separately |
| “The specification is unattainable” | State that the evaluated controllers rarely achieve it |
| Behavioral loss “does not help transfer” despite new relative improvements | Report the small relative improvement together with the large absolute failure |
| Large M3–M4 gap attributed to only one check | Describe the current combined-safeguard comparison; replace after isolated rerun |
| “Training data: 360 episodes” | Distinguish 360 total generated parent episodes from 160 training episodes |
| Broad findings blamed specifically on closing the fault leak | Several physics/controller/training changes occurred together; do not isolate their causal contribution without a comparison |
| Context-conditioned feedforward claimed for nominal code | Correct the description now; restore the claim only when implemented |
| “Independent hardware replication” | Use fitted-envelope consistency and controlled simulation comparison |

Generate narrative conclusions from current structured outputs where possible. Missing fields must produce “not evaluated,” not an old hardcoded numerical assertion.

### 8.2 Keep hardware central and explain implementation differences

Preserve the hardware results as the main physical evidence. Add a compact implementation comparison covering:

- Hardware controller associated with the reported logs.
- Simulated hardware-matched comparator.
- Final proposed simulation controller.

List actual horizon, objective, active learned components, estimator, allocator, and recovery checks. Resolve the manuscript’s horizon 10 versus the repository’s claimed hardware horizon 12 using the configuration linked to those runs.

Do not imply that a newly simulated allocated-command check was present on hardware unless it actually ran there. Simulation faults can motivate different outcomes from hardware; investigate those differences rather than treating either dataset as automatically invalidating the other.

### 8.3 Recommended final tables and figures

**Table 1 — Hardware experiments.** Retain the existing physical comparisons and clarify run counts, metrics, fault mechanism, and implementation provenance.

**Table 2 — Focused simulation comparison.** Include M1, M2, M3, and essential reference methods across the four conditions. Report distinct scenarios, checkpoint seeds, total rollouts, primary tracking error, final-task success, and recovery/completion failures.

**Table 3 — Component contributions.** Report M2–M1, M3–M2, M3–M4, and M3–M5 with matched design/checkpoint details and uncertainty. Do not hide unfavorable rows.

**Table 4 — One numerical recovery case.** Include design/calibrated quantities, strict margin, physical sizes, activity/duration, and violation counts. If no useful case is obtained, report that limitation and reconsider the practical recovery claim.

**Figure 1 — Corrected architecture.** Keep the manuscript’s visual style but show the actual offline supervision, context-conditioned predictor/feedforward, constrained MPC, nominal transmitted-command check, fallback, and supervisor.

**Figure 2 — Control behavior.** Align physical tracking, estimation error, command/check quantities, and action source. This should explain whether MPC is operating and when recovery occurs.

**Figure 3 — Recovery bound or transfer failure.** Choose the figure that supports the final contribution most directly; keep the other in the reproducibility package. A failure should remain visible if it materially limits a generalization claim.

Use the existing plotting/report infrastructure and layouts. Regenerate the curves and tables when the controller or scoring changes. Avoid filling the letter with every horizon and authority sweep.

## 9. Efficient work order and reuse rules

| Order | Work | Reuse | Regenerate |
|---|---|---|---|
| 1 | Archive current campaign and correct stale report claims | All data and artifacts | Report prose and mislabeled tables |
| 2 | Fix fault-slot execution and reference/endpoint bookkeeping | Corrected command/plant interfaces and applicable training data | Affected execution traces and faulted policy evaluations |
| 3 | Separate M4 switches; complete action-source metrics | Checkpoints and scenario definitions | M3/M4 matched deployment comparisons |
| 4 | Implement common learned predictor/feedforward/affine controller and feasibility checks | Existing checkpoints where input/target semantics remain valid | Every policy outcome affected by the new controller |
| 5 | Correct final-task/post-fault metrics | Complete saved traces, if available | Metrics; missing traces collected in the next run |
| 6 | Run small development diagnostics for task failure and transfer | Existing failure cases | Only focused diagnostic runs |
| 7 | Freeze training/controller choices | Existing models or corrected retraining outputs | Training only if architecture, targets, coverage, or regularization changes |
| 8 | Run final matched comparisons | Method definitions and infrastructure | Fresh matched scenario draws for the final frozen policies |
| 9 | Complete one recovery verification/calibration/test case | Design tools and valid analytic pieces | Verification/calibration outputs tied to the final policy |
| 10 | Regenerate publication tables/figures and revise claims | Hardware evidence and document structure | Final simulation results and interpretations |

Do not automatically restart all training because the controller code changes. Conversely, do not reuse a checkpoint whose training inputs or prediction targets no longer match the deployed model.

The published repository does not track all generated training data/checkpoints. Retain them from the training environment or provide retrievable versioned artifacts; if unavailable, regenerate them under the recorded corrected configuration. Do not silently substitute a newly trained seed for an old checkpoint while retaining old evaluation labels.

Existing scenarios remain useful regression cases. Once used to tune the method, they are development cases. The final test should be new and untouched until the policy and selection rules are frozen.

## 10. Decisions after the completed experiments

### If behavioral supervision improves a meaningful endpoint

Keep it as a central contribution. Show the matched M3–M2 effect, training-seed variation, practical relevance, and at least one supporting representation/prediction result. Restrict the claim to the tested population and transfer conditions.

### If dynamic context helps but behavioral supervision does not

Use the selected prediction-only model when warranted. Retain the unfavorable supervision ablation. Revise the contribution statement accordingly.

Removing the behavioral objective leaves a less distinctive context-learning contribution. The paper then needs its novelty to come from the actual coupling of actuation/perception adaptation, allocated-command recovery design, and convincing physical/controlled validation. Do not replace an unsupported specific claim with an equally unsupported broad claim.

### If MPC adds no demonstrated benefit beyond fallback

Report that outcome. Check whether model/feasibility defects still explain it. If the fully corrected implementation still behaves this way, reconsider the emphasis on MPC planning. Do not claim equivalence from wide intervals, and do not select only the cases where MPC looks better.

### If no useful recovery certificate is obtained

The conditional theorem is not automatically false. However, practical recovery certification remains unvalidated. Keep the failed search as a limitation, narrow the guarantee claims, and assess whether the remaining empirical/method contribution is strong enough for RA-L.

### If transfer remains poor

Restrict generalization claims and show the failure. Improvements on the nominal task do not establish transfer. Adding the failed reference to training requires a new untouched transfer test if a transfer claim is retained.

### Final stopping criteria

The remaining work is sufficiently complete when:

- The implementation and manuscript agree on the learned model, inputs, feedforward, optimization constraints, gate, fallback, and reference timing.
- The no-check comparison changes only the declared component.
- Task success measures the intended final objective and post-fault behavior.
- The core comparisons use appropriate matched seeds, scenario counts, and uncertainty.
- Favorable and unfavorable results both appear with correct interpretations.
- Any numerical recovery claim has a useful verified and calibration-accepted demonstration.
- Hardware and simulation claims are accurately distinguished.
- The report contains no stale values or conclusions contradicted by its own tables.

The purpose of this plan is to complete the missing evidence efficiently. Preserve the work that is now correct, rerun the comparisons whose meaning changes, and let the final contribution statements follow the results.

## Source references

All references below identify the reviewed snapshot.

- [Updated report](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/results/results.md)
- [Controller policies](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/scsim/controllers.py)
- [Plant and command chain](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/scsim/plant.py)
- [Episode runner](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/scsim/runner.py)
- [MPC implementation](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/scsim/mpc.py)
- [Training and probe generation](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/stage5_data_train.py)
- [Training results and selection grid](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/results/stage5_training.json)
- [Comparisons and metrics](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/stage6_methods.py)
- [Stored performance results](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/results/stage6_methods.json)
- [Certificate functions](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/scsim/certificate.py)
- [Certificate evaluation](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/stage7_certificate.py)
- [Stored certificate results](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/results/stage7_certificate.json)
- [Transfer and retrieval evaluation](https://github.com/baaqerfarhat/Sc_sim_env/blob/4f967a40f6477724258b53acf9cf6464edacddcf/stage8_horizon.py)


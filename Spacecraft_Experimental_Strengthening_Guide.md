# Spacecraft experimental strengthening guide

Prepared 15 September 2026. Suggested trial counts and decision criteria in this guide are study-design recommendations, not IEEE requirements or additional measured results.

This guide concerns **Multimodal_Context_Learning_for_Actuation_and_Perception_Fault_Tolerant_Model_Predictive_Control (1).pdf**, the current nine-page manuscript. Page numbers below refer to PDF pages. The spacecraft should remain the main experimental platform. The goal is to connect its measurements to the submitted method through a small number of decisive comparisons, reproducible implementation details, and physically meaningful recovery measurements.

The companion [Simulation_Validation_Protocol.md](Simulation_Validation_Protocol.md) addresses controlled validation of behavioral learning and the recovery certificate. Simulation can establish those mechanisms under its declared conditions; it cannot establish which controller generated an existing hardware result or certify an unmeasured hardware implementation.

## 1. What the spacecraft experiments need to establish

The manuscript makes two contributions on page 1: behavioral supervision of the context and a constructive recovery condition. The existing hardware measurements support a narrower result: learned context improves aggregate position tracking relative to deployment-time zero context in the recorded conditions. Preserve that evidence, but distinguish it from validation of the full method.

| Claim or reviewer question | Evidence that would be convincing | Priority |
|---|---|---|
| Does context help beyond ordinary model fitting? | A trained constant-context controller compared with the full controller under matched tasks, limits, and observations. | Essential |
| Does the proposed behavioral loss matter? | Full versus independently retrained no-behavioral-loss models, with identical prediction data and training budgets; physical recovery and held-out transfer improve. | Essential to the learning contribution; extensive testing can be in simulation |
| Is this actuation and perception fault tolerance? | Precisely defined physical/observation interventions, verified estimator degradation, and a combined-impairment condition. | Essential |
| Does lower RMSE mean useful recovery? | Original-task trajectories, prespecified physical tolerances, dwell-based success, onset-relative recovery time, and all attempted trials. | Essential |
| Was the proposed controller actually deployed? | Run-to-build and checkpoint identities, active-component records, and the actual transmitted commands. | Essential |
| Does the theorem describe hardware operation? | A numerical certificate for the deployed implementation, physical estimation-error measurements, and valid execution records over eligible intervals. | Required only for a hardware-certificate claim |
| Can the controller run at its stated frequency? | Full-loop timing, deadline misses, and what command is transmitted when computation fails. | Essential for real-time claims |

Improved latent retrieval alone would not demonstrate better control. Conversely, better tracking without a behavioral-loss comparison would not identify the source of the improvement.

## 2. Preserve the current evidence accurately

Section V and Table I, pages 6–7, currently report the following. All errors are in meters; values are means ± sample standard deviations over complete saved metric records.

| Condition | Context | Records | Position RMSE | Position MAE | Peak error |
|---|---|---:|---:|---:|---:|
| Healthy | Zero | 5 | 1.034 ± 0.043 | 0.874 ± 0.098 | 2.013 ± 0.025 |
| Actuator 70% | Zero | 5 | 1.105 ± 0.108 | 0.982 ± 0.110 | 2.015 ± 0.078 |
| Actuator 70% | Fixed | 5 | 1.028 ± 0.142 | 0.863 ± 0.178 | 1.992 ± 0.022 |
| Actuator 70% | Learned | 5 | 0.950 ± 0.022 | 0.831 ± 0.023 | 1.686 ± 0.149 |
| Actuator 50% | Zero | 3 | 1.089 ± 0.023 | 0.939 ± 0.022 | 3.047 ± 1.761 |
| Actuator 30% | Zero | 3 | 1.315 ± 0.187 | 1.204 ± 0.246 | 2.047 ± 0.076 |
| Actuator 30% | Learned | 5 | 0.781 ± 0.020 | 0.701 ± 0.012 | 1.344 ± 0.066 |
| Half-camera | Zero | 5 | 1.895 ± 0.087 | 1.739 ± 0.085 | 2.881 ± 0.237 |
| Half-camera | Fixed | 3 | 1.352 ± 0.157 | 1.267 ± 0.185 | 2.006 ± 0.002 |
| Half-camera | Learned | 5 | 0.798 ± 0.249 | 0.645 ± 0.201 | 1.513 ± 0.480 |

The reported 14.0%, 40.6%, and 57.9% mean-RMSE reductions are descriptive comparisons. They do not establish matched-treatment effects or demonstrate either new contribution. The current distinction between complete-record count and all-attempt count is correct and should remain.

The fixed-context actuator row uses the **selected final five stable trials**. Recover the selection rule and earlier attempts. If selection was retrospective, retain this row only as descriptive supporting evidence; do not treat it as an unbiased baseline comparison. Never infer that five saved records mean five total attempts.

Current Eq. (30) averages each record over its own length. Report those lengths and starting conditions. Different lengths, warmup periods, or initial transients can alter RMSE without changing recovery capability. If comparable onset windows can be reconstructed, add that analysis without silently replacing the original metric definition.

## 3. First recover information; then collect only what is missing

### Essential: establish what actually ran

Create a run manifest joining each metric record to the raw log, reference, impairment schedule, software commit or archived source hash, model checkpoint hash, configuration file, and scoring-script version. Record whether the behavioral loss, context-conditioned residual, feedforward, fixed cost, allocation check, fallback, and supervisor were active. If identity cannot be recovered, label that measurement as a legacy context-adaptation result.

Resolve the present implementation discrepancy explicitly. Section III, Eq. (16), uses a fixed pseudo-Huber state cost; Section V mentions a cost-head MLP, nominal weights, and weight floors. The proposed loss in Appendix I, Eq. (32), combines one-step, multistep, and behavioral terms; “MSE/AdamW defaults” does not identify this objective. State whether these differences describe older hardware code or the submitted implementation. Recover the actual pseudo-Huber scales, state weights, input penalty, terminal penalty, and any context-dependent outputs. Six nominal weights alone do not specify that optimization problem.

Likewise, verify the residual's actual inputs, output units, coordinate frame, normalization, and clipping. A six-state output clipped to ±0.5 requires a per-coordinate interpretation; position, angle, and velocity have different units. Explain how the implementation realizes the body-frame structure in Appendix II. Do not assert equivariance merely because it is assumed in the analysis.

### Essential: recover the physical and sensing specification

Most of the following should come from build documentation, calibration records, configurations, or existing logs rather than new comparative trials.

| Information | What to recover and why it matters |
|---|---|
| Spacecraft and workspace | Mass, planar inertia, body frame, usable table dimensions, corridor boundaries, air-bearing setup, and reference size/speed. These make 0.8 m RMSE and 1–3 m peaks interpretable. |
| Thrusters and allocation | Locations/directions of all eight thrusters, wrench map, maximum thrust, duty limits, valve/pulse constraints, allocation algorithm, saturation, quantization, and any memory state. |
| Actuator interventions | Which thrusters were changed, physical versus commanded change, exact meaning of 70/50/30%, onset/ramp/duration, and independent verification if available. “70% setting” must not silently become “70% remaining thrust.” |
| Perception intervention | Which camera, physical obstruction versus image masking, region/fraction, onset/duration, and observed feature/innovation/estimation effects. |
| Estimation and Vicon | Raw sensors and rates, estimator version, measurement fusion, resets, timestamps, Vicon accuracy/alignment, and every route through which Vicon could enter feedback. |
| Control and compute | Actual sample period, horizon, solver/tolerances, compute hardware, thread/process arrangement, control deadline, and deadline-failure behavior. |
| Learning | History construction, feature ordering, units, missing-data masks, normalization, training data/splits, architecture, objective coefficients, optimizer settings, and checkpoint-selection rule. |

The reported $T_s=0.1$ s, $N=10$, history length 10, latent dimension 32, three layers, four heads, and width 128 are useful starting points. Confirm their correspondence to each checkpoint. Ten-hertz controller diagnostics do not establish raw camera or IMU rates. Document the exact history indices: equation (2) uses eleven innovation/availability timestamps and ten previous commands when $L=10$.

If Vicon served only scoring, say so and verify the data path. If it entered the recorded controller, disclose that role and narrow the perception claim. For new trials intended to demonstrate onboard perception robustness, keep physical ground truth out of controller inputs; use it for scoring and evaluation of estimation error.

### Strongly recommended: targeted measurements before new comparisons

Measure time alignment, realized thrust response, pulse behavior, and observation degradation if existing records cannot establish them. A short calibration run may resolve an uncertainty that otherwise undermines every comparative run. Separately record estimator error against Vicon during occlusion: demonstrate that the intervention affects the information used for control, rather than only an unused image stream.

## 4. A compact matched hardware study

Use three primary controllers: **trained constant-context MPC**, **without behavioral loss**, and **full method**. Deployment-time $z=0$ is a useful diagnostic but is not a substitute for retraining a constant-context predictor. The no-behavioral-loss model must be independently trained with the same data, prediction losses, architecture, optimizer budget, and checkpoint rule, setting only the behavioral coefficient to zero.

The no-behavioral-loss controller still uses multimodal histories. It is not a “no multimodal” ablation. An optional innovation-feature ablation removes the specified innovation/availability features while retaining the estimator; fused measurements may still carry information from those sensors. Describe exactly what information is removed.

Use healthy, actuator-only, perception-only, and combined conditions. Choose one actuator setting and one occlusion intervention that produce informative, physically executable tasks, then apply those same interventions together for the combined condition. More severity levels belong primarily in simulation. Include healthy learned operation so gains from ordinary model correction can be distinguished from impairment robustness. Learned-context RMSE under a fault being lower than healthy zero-context RMSE does not show that the fault improves performance; those rows change both the condition and controller.

A compact planning example is **five matched blocks per condition with three controllers: 60 trials**. This is a practical starting design, not an RA-L requirement or a guarantee of precision. Use separate pilot variability and a scientifically meaningful effect to choose the final count before the confirmatory collection. If five blocks are all that is feasible, report the resulting uncertainty honestly rather than declaring small differences established.

Within each block, match reference, initial-state tolerance, impairment timing, duration, sensor configuration, command limits, and environmental conditions. Randomize controller order; block by collection day and relevant battery/supply-pressure state, and record resets. Keep the same estimator and available measurements. Freeze the evaluation protocol before collecting comparison trials.

A tuned adaptive MPC baseline is strongly recommended, at least in the companion simulation study. If included on hardware, describe the adapted quantities and constraints; a deliberately restricted correction should not be presented as representative of all adaptive MPC.

Where variants require different verified regions, report the regions, eligibility, and supervisor activity. If performance differences primarily follow different supervisory restrictions, add a common-region comparison where feasible. This prevents attributing every benefit to representation learning.

## 5. Define measurements before scoring new trials

Let $p^{\mathrm{task}}_{a,k}$ be the original task reference and $p_{a,k}$ the synchronized physical position for trial $a$. Define the position error in meters as

$$
e^p_{a,k}=\|p_{a,k}-p^{\mathrm{task}}_{a,k}\|_2.
$$

For a prespecified $T$-sample evaluation window $W_a$, report

$$
\mathrm{RMSE}_{p,a}=\sqrt{\frac{1}{T}\sum_{k\in W_a}(e^p_{a,k})^2},\qquad
\mathrm{MAE}_{p,a}=\frac{1}{T}\sum_{k\in W_a}e^p_{a,k},\qquad
E^{\max}_{p,a}=\max_{k\in W_a}e^p_{a,k}.
$$

Here MAE means mean Euclidean position-error magnitude. Inspect the legacy scoring code: coordinatewise absolute error, a mean across axes, and Euclidean magnitude are different quantities. Do not relabel the existing MAE values without confirming their definition. State the frame, units, angle wrapping, and synchronization/interpolation convention.

For new impaired trials, use a common onset-relative window with fixed duration; record a separate prefault baseline window. Whole-task metrics can remain useful secondary outcomes, but mixing variable warmup lengths with postfault behavior weakens causal interpretation. Healthy trials need a comparable scheduled scoring start. Retain the original task reference even if the supervisor changes its internal reference; report that change separately.

Define success using both position and attitude tolerances, unless the task explicitly requires only position:

$$
e^p_{a,k}\le h_p,\qquad
|\operatorname{wrap}(\psi_{a,k}-\psi^{\mathrm{task}}_{a,k})|\le h_\psi.
$$

Both conditions must hold for a prespecified dwell duration and finish before an onset-relative deadline. Select tolerances from the task and workspace, not from observed successes. Specify sampling cadence and missing-sample treatment. Sampled compliance does not establish intersample safety.

Define recovery time as onset to the first entry that subsequently completes the dwell, and specify this convention. Safety aborts and timeouts count as unsuccessful attempts. A failed recovery has no finite successful-recovery time; report success rate alongside time among successful trials to avoid rewarding controllers that recover only on easy cases.

Maintain separate counts for attempts, complete evaluation records, successes, aborts, timeouts, and justified technical exclusions. Never substitute a shortened successful-looking record for a missing full-duration RMSE. For incomplete records, report the missingness and failure category; do not invent an error trajectory.

Aggregate per-trial metrics, not time samples pooled across runs. Report RMSE mean ± SD and success $s/n$; peak error and successful-recovery time can use median [IQR] when distributions are skewed. The existing mean ± SD peak convention is also acceptable if explicitly retained. Add uncertainty intervals for the main controller differences and for success proportions. Use paired block differences only for genuinely matched blocks; old unpaired runs cannot become paired because they share a condition label. Resample whole blocks or trials, not correlated samples or overlapping history windows. Choose a minimum practically meaningful tracking or recovery improvement before the final study; statistical significance alone is not a sufficient success criterion.

## 6. Log enough to explain a result

Use a compact metadata file per trial plus a timestamped sample table. Preserve raw observations or references to them when feasible.

| Record group | Minimum contents |
|---|---|
| Identity | Trial/block IDs; software and checkpoint hashes; configuration/scoring versions; controller variant. |
| Scenario | Reference ID; initial state; condition; intervention commands, timestamps, and verified settings; planned duration. |
| Physical and estimated motion | Ground-truth pose, estimate, relevant velocities, confidence/availability, coordinate frames, timestamps, and synchronization quality. |
| Controller inputs | Exact history features or reconstructible inputs, masks, modality innovations, context, and normalization identity. |
| Commands | Proposed wrench, transmitted duties, nominal-equivalent wrench, allocation status and memory, saturation/pulse information. |
| Recovery logic | Eligibility and rejection reason, candidate/fallback choice, supervisor action, original and online references, computed check quantities. |
| Execution | Acquisition, estimation, encoding, model/feedforward, optimization, allocation/check, and transmission timestamps; solver status and deadline misses. |
| Outcome | Completion/abort/timeout reason, missing intervals, hardware intervention, and prespecified exclusion reason if applicable. |

Full-loop latency includes more than neural inference or solver time. At the stated 10 Hz, assess the entire computation/transmission path against its declared deadline. Report median, p95, observed maximum, and misses; an observed maximum is not a formal worst-case execution bound.

## 7. Decide whether to claim hardware certification

This is a scope decision, not an obligation to collect hundreds of hardware episodes merely to support adaptation. If certification is demonstrated only in simulation, say so. The spacecraft can still establish physical adaptation, provided the hardware implementation is identified accurately.

A hardware-certificate claim requires the actual deployed model, metric, feedback, reference domain, allocator, supervisor, and uncertainty budgets to satisfy Sections III–IV. Instantiate $\lambda,b_r,d_{\mathrm{cert}},\eta,R,s_{\mathrm{cert}}$ and the upper radii, establishing a useful strict margin. Verify the command check using transmitted-equivalent commands as in Eq. (17), not a pre-allocation proposal.

Freeze the policy and design before independent fitting/calibration/test collection; use complete episodes from the declared population. Include inactive periods, zero-active episodes, and the required successor errors of active transitions. A policy change requires appropriate fresh calibration. At the manuscript's example error allocations of 0.025 per channel, 39 calibration episodes merely allow finite thresholds; they do not establish useful bounds, acceptance, or frequent recovery activity.

Report acceptance separately from empirical joint coverage. Eq. (29) is a marginal joint statement, not a guarantee conditional on an accepted certificate or on every individual fault type. Simulation calibration does not transfer automatically to hardware. Physical-estimation envelopes also require credible ground truth and synchronization, with reference-measurement uncertainty addressed.

Show consecutive eligible durations, actual versus bounded entry time, fallback frequency, and whole-episode and eligible-transition violations. The recovery clock starts inside the admitted region with eligibility, not necessarily at fault onset. High coverage achieved through almost no active control is not evidence of useful recovery. A sampled-state result must remain labeled sampled-state safety.

## 8. Present the evidence economically and apply a decision rule

Use one main hardware comparison table with columns:

**Condition | Controller | Attempts/complete records | RMSE | Peak | Success | Recovery time.**

Put missing-record accounting and exact metric conventions in its caption. Preserve the legacy table only if its additional descriptive value warrants the space. A compact implementation table can give the exact model, learning, cost, allocator, and compute settings. If hardware certification is claimed, add a small numerical certificate/operation table rather than pages of protocol prose.

Use two informative visual elements: physical reference/trajectory plus onset-aligned error traces, and a representative execution trace showing the controller's response. If certified recovery is evaluated on hardware, include the bound, eligibility, and transmitted-command checks in the latter. Select representative trials by a prespecified rule and retain failures in aggregates. Figs. 2–4 currently repeat much of Table I; reclaim that space for trajectories and mechanism evidence. Replace Fig. 1 with the actual submitted architecture and change Fig. 3's plotted “oracle” label to “hand-tuned.”

Before submission, resolve these essential decisions:

- **Full improves over no behavioral loss:** claim supervision improves control only if the effect is meaningful and uncertainty supports it. If only retrieval improves, limit that claim accordingly.
- **Full improves over a trained constant-context model:** this supports adaptive contextual inference. A gain only against deployment-time zero context is weaker evidence.
- **Combined and healthy behavior are credible:** demonstrate useful recovery without unacceptable nominal degradation; report adverse cases rather than removing them.
- **The exact full method runs on hardware:** if only an earlier controller was deployed, separate that evidence explicitly from full-method simulation validation.
- **Certificate bounds are useful:** claim hardware certification only with an accepted, operationally meaningful certificate; otherwise keep the theoretical result and its simulation validation distinct.
- **Results are reproducible:** all main runs have recoverable build identities, definitions, timing, fault specifications, and transparent denominators.

If those conditions are met, the manuscript can make a coherent case with one spacecraft platform. If they are not met, adding plots or filling numerical fields should not substitute for narrowing the corresponding claims.

## 9. Recommended order of work

1. Recover the build/checkpoint identities, fault definitions, Vicon data path, scoring code, and per-run durations before interpreting new comparisons.
2. Re-score existing raw logs on comparable windows where possible; otherwise preserve their descriptive status and report the limitations.
3. Complete the simulation study to check the behavioral-loss effect and numerical feasibility of the proposed recovery controller before committing to extensive hardware collection.
4. Run the focused matched hardware blocks with the frozen implementation and complete logging. Add extra severities only if a specific unresolved reviewer question requires them.
5. Replace repeated bar charts with the matched comparison and physical recovery traces. Align abstract and contribution statements with the evidence actually obtained.

The current PDF is nine pages. RA-L permits at most eight pages, including references and appendices; supplemental text cannot bypass that limit. Plan the combined hardware/simulation presentation around the decisive tables and figures above, retaining essential theorem assumptions and proof arguments in the allowed paper. [RA-L author instructions](https://www.ieee-ras.org/publications/ra-l/ra-l-information-for-authors/)

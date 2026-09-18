# Spacecraft simulation: corrections and validation plan for IEEE RA-L

**Prepared:** 17 September 2026  
**Purpose:** Instructions for correcting the simulation, rerunning the necessary comparisons, and deciding which claims the resulting evidence supports.  
**Reviewed repository:** [baaqerfarhat/Sc_sim_env](https://github.com/baaqerfarhat/Sc_sim_env/tree/0d0088e474c7b5460651e486eb6ea84760132941)  
**Reviewed commit:** `0d0088e474c7b5460651e486eb6ea84760132941`  
**Reviewed report:** [results/results.md](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/results/results.md)  
**Manuscript basis:** The nine-page version of *Multimodal Context Learning for Actuation and Perception Fault-Tolerant Model Predictive Control*, uploaded as `Multimodal_Context_Learning_for_Actuation_and_Perception_Fault_Tolerant_Model_Predictive_Control (1).pdf`.

These instructions apply to the reviewed commit. Line numbers and function names below identify that snapshot; subsequent changes should be compared against these requirements. This document proposes work. It does not claim that the corrections or new experiments have already been completed.

## 1. Decision and priorities

The current simulation is useful development evidence, but it cannot yet provide decisive validation of the manuscript. Its positive controller comparisons and negative behavioral-supervision results are affected by implementation differences and defects. Correct those first. More episodes under the current implementation will not resolve them.

Preserve the present results, configuration, and commit as an earlier development campaign. Generate corrected results under a new run identifier. Do not mix old and corrected trials in a paper table.

The objective is to answer three questions:

1. **Representation:** Does the specified behavioral supervision improve a practically relevant result beyond prediction-only context learning?
2. **Control:** Does the implemented context-conditioned MPC contribute beyond a simple feedback fallback and fair MPC comparators?
3. **Recovery analysis:** Can the exact implemented controller demonstrate a nonempty, physically useful recovery region under its stated conditions?

A favorable answer is not guaranteed. If corrected experiments do not support a contribution, narrow the claim or revise the method. Do not select test conditions or seeds solely to produce favorable results.

| Priority | Required work | Why it precedes further experiments |
|---|---|---|
| P0 | Separate controller-visible transmitted commands from hidden physical fault effects | Current inputs and checks contain fault information unavailable under the manuscript’s assumptions |
| P0 | Integrate physical thrust using true spacecraft orientation | Current plant dynamics depend incorrectly on estimator yaw |
| P0 | Implement the specified prediction model, MPC constraints, gate, and fallback selection | Current code does not implement the analyzed controller |
| P0 | Correct matched probe construction and command definitions in supervision | The present loss comparison does not faithfully test the proposed behavioral objective |
| P1 | Correct numerical verification and freeze a candidate recovery design | Sampled maxima and incomplete enclosures cannot establish the theorem’s premises |
| P1 | Define meaningful task metrics and matched comparisons | Current recovery tolerance and baseline differences obscure practical interpretation |
| P1 | Regenerate data, train, tune, calibrate where applicable, and test in that order | Old data and checkpoints inherit the earlier information-flow and physics problems |
| P2 | Rewrite results, figures, and manuscript claims from the corrected evidence | Presentation must follow what the experiments actually establish |

## 2. Correct the command interface and hidden-fault boundary

**Source locations:** `scsim/plant.py::CommandChain.trial`, approximately lines 311–367; `scsim/controllers.py::LearnedContextPolicy.act`, lines 275–319; `scsim/runner.py::run_policy_episode`, lines 217–242; `scsim/scenarios.py::build_history`.

### 2.1 What is wrong

The current trial allocation previews the hidden pulse-skipping fault and computes `u_applied` from the resulting post-fault pulses. It also includes hidden smooth effectiveness when that intervention is enabled. The candidate check, fallback check, and context history consume this quantity.

The manuscript defines $u_k$ as the **nominal-equivalent wrench of the transmitted command**. It is not the unknown fault-affected physical wrench.

A diagnostic on the reviewed code confirmed that identical proposed commands and identical pre-fault pulses produced controller-visible wrenches `[0, 0.96, 0]` and `[0, 0, 0]` solely because the hidden fault differed. That reveals current fault effects before the controller should know them.

### 2.2 Implement distinct quantities

Use explicit names and units throughout the code and saved logs.

| Quantity | Suggested name | Available to controller? | Definition |
|---|---|---:|---|
| Desired wrench before allocation | `u_proposed` | Yes | The optimizer or fallback output |
| Selected pre-fault pulse durations | `pulse_command_s` | Yes | Exact durations committed for transmission |
| Nominal-equivalent transmitted wrench | `u_nominal_transmitted` | Yes | Nominal geometry and nominal valve thrust applied to selected commanded pulses |
| Actual post-fault pulse durations | `pulse_actual_s` | No | Evaluator/plant output after pulse skipping or other hidden actuation faults |
| Actual valve effectiveness/bias | `effectiveness_true`, `bias_true` | No | Hidden plant parameters |
| Physical body wrench | `wrench_physical_body` | No | Physical force/torque from actual valve operation |
| Physical state | `x_true` | No, except declared initialization | Scoring, offline supervision, and envelope fitting/calibration only |

For body-frame wrench coordinates, one possible pulse representation is

$$
c_{k,i}=F^{\rm nominal}_{i}\frac{\tau^{\rm command}_{k,i}}{T_s},
\qquad
u_k=G c_k.
$$

Here $c_k$ has units of average nominal thruster force, and $G$ maps these forces to body wrench. If the manuscript instead uses dimensionless duty $c_k$, include nominal thrust in $G$. Choose one convention and state it.

The physical plant separately applies the hidden pulse-skipping schedule or effectiveness to obtain actual forces. Do not apply the same effectiveness once in the transmitted command and again in the physical plant.

### 2.3 Required execution order

1. Trial-allocate candidate and fallback using the same frozen allocator memory.
2. Construct each trial’s controller-visible nominal-equivalent wrench from pre-fault commands.
3. Evaluate the acceptance conditions without calling the hidden fault model.
4. Select and commit exactly one stored command packet and allocator-memory update.
5. Apply hidden faults on the plant side to that selected packet.
6. Integrate the physical plant and produce the next observation.
7. Log nominal transmitted commands and hidden physical effects in distinct fields.

Remove the hidden fault object from the allocator interface exposed to the policy where practical. Offline physical scoring may access hidden fields; the online policy, its acceptance check, and its feature builder must not.

### 2.4 Checks that must pass

- Hold the estimate, history, nominal allocator state, reference, and proposed command fixed. Changing only hidden fault severity, phase, or onset must not change trial allocation, nominal transmitted wrench, pre-action acceptance, or selected policy action.
- The physical successor must still change when a hidden actuation fault changes the actual thrust.
- Repeated trial allocations must not advance allocator memory or the fault schedule.
- Exactly one selected command commits allocator memory, and exactly one physical control slot advances the fault schedule.
- Reconstruct $u_k$ from the saved selected pulses and nominal parameters and compare it with the input used by the predictor and encoder.

After this correction, regenerate all affected parent episodes, probe branches, features, prediction targets, checkpoints, and downstream results.

## 3. Correct physical dynamics, coordinates, and actuator authority

**Source locations:** `scsim/runner.py`, particularly lines 151–154 and 237–242; `scsim/plant.py::plant_step`; `stage7_certificate.py::achievable_set` and `_chain_factory`.

### 3.1 Use true orientation in the physical plant

The current runner passes estimated yaw to `plant_step`. The plant then rotates physical forces using that estimate.

For body-mounted thrusters, integrate

$$
\dot p=v,\qquad
m\dot v=R(\psi_{\rm true})F_{\rm body}+F_{\rm external},
$$

$$
\dot\psi_{\rm true}=\omega,\qquad
J\dot\omega=\tau_{\rm body}+\tau_{\rm external}.
$$

Include the declared drag and damping terms consistently. The allocator can use estimated yaw when converting a requested world wrench to body commands. The physical plant must use true yaw when converting actual body force to world acceleration.

Update true yaw within numerical integration. Resolve pulse start and stop times accurately, rather than assuming that choosing a small integration step automatically reproduces every pulse duration.

### 3.2 Fix and document the coordinate convention

The repository orders the state as

$$
x_{\rm code}=[p_x,p_y,v_x,v_y,\psi,\omega]^\top.
$$

The manuscript’s stated ordering differs. Either align the implementation with the manuscript or supply an explicit permutation and apply it to every matrix, weight, projection, Jacobian, and logged state.

Also declare:

- Which wrench vectors are in body coordinates and which are in world coordinates.
- The frame of the residual output and clipping operation.
- How error coordinates are formed from the reference.
- The yaw chart and angle-unwrapping convention.
- Units and scaling of every prediction-loss component and every entry of $P$.

A body-frame nominal transmitted wrench is a convenient consistent choice. If retaining the current world-frame input interface, document the estimated-yaw transformation explicitly and include its consequences in the predictor and mismatch analysis.

### 3.3 Make authority changes physically consistent

The current authority sweep changes `fmax` and the assumed achievable box, while delivered valve thrust can remain fixed at `C.VALVE_THRUST`. Changing an optimizer’s allowed force does not necessarily change physical authority.

For each sweep parameter, specify exactly which subsystem changes:

- Maximum nominal allocation variable.
- Actual valve-open thrust.
- PWM period and maximum commanded duration.
- Minimum pulse duration.
- Command deadbands and caps.
- Known actuator design versus hidden actuator degradation.

If a sweep represents larger thrusters, update nominal mapping, actual physical thrust, feedforward limits, and verification consistently. If it only changes the allocator’s permitted request, label it that way.

Do not call a box formed from separate axis maxima the exact jointly achievable wrench set. Simultaneous force and torque requests share thrusters. In the manuscript, the convex command budget $\mathcal U$ and actual allocator realizability have different roles. Check admissibility and allocated fallback realization separately.

### 3.4 Checks that must pass

| Check | Required observation |
|---|---|
| True yaw $90^\circ$, estimated yaw $0^\circ$, body-forward pulse | Physical acceleration rotates with true yaw |
| Change estimated yaw while holding true state and actual pulse vector fixed | Physical integration is unchanged |
| Zero fault and perfect state estimate | Nominal/physical differences match the explicitly modeled pulse, integration, and plant mismatch terms |
| Integrate identical pulses at successively finer steps | Trajectory differences fall below a declared numerical tolerance |
| Increase actual valve thrust with pulse duration fixed | Physical impulse increases consistently |
| Rotate a complete state/reference/command scenario | Results transform according to the claimed coordinate symmetry, where that symmetry is asserted |

Do not retune perception noise merely to hide a physical-model correction. Reassess hardware agreement and report what changes.

## 4. Implement the controller that the manuscript analyzes

**Source locations:** `scsim/controllers.py::LearnedContextPolicy`; `scsim/mpc.py::ProposedMPC`; `scsim/certificate.py::feedforward` and `error_jacobians`.

### 4.1 Use the same learned model in training, feedforward, prediction, and checking

The manuscript’s model predicts the next estimate:

$$
f_\theta(\hat x,u,z)=f_0(\hat x,u)+d_\theta(\hat x,u,z).
$$

Train with the nominal-equivalent command actually transmitted at that transition. At deployment, evaluate the model consistently at the relevant state, input, and current context.

The reviewed code trains using the current transmitted input but evaluates the residual at the previous proposed command. Under severe allocation saturation, those inputs can differ substantially. It then holds that residual constant through MPC.

Implement the manuscript’s affine construction:

$$
\bar f(e,u;z,r,r^+)=
\Phi_{r^+}\!\left(f_\theta(\Phi_r^{-1}(e),u,z)\right),
$$

$$
d^r=\bar f(0,u^r),\qquad
A=\left.\frac{\partial\bar f}{\partial e}\right|_{0,u^r},
\qquad
B=\left.\frac{\partial\bar f}{\partial u}\right|_{0,u^r}.
$$

The feedforward selector must use the same learned predictor and declared feasible command budget. A feasible returned input and its evaluated defect are required; exact global minimization is not necessary if the manuscript’s selector permits a deterministic feasible approximation.

Freeze the context over the prediction horizon as specified. Recompute context and scheduled models at the next control sample.

### 4.2 Implement the actual optimization constraints

For the latest manuscript’s equation (15), implement

$$
e_{i+1}=A_{i|k}e_i+B_{i|k}\delta u_i+d^r_{i|k},
\qquad
\delta u_i=a_i+Ke_i,
$$

with

$$
u^r_{i|k}+\delta u_i\in\mathcal U,
\qquad
e_i\in\mathcal C,\quad e_N\in\mathcal C,
$$

and the first-action condition

$$
\|A_ke_k+B_k\delta u_0+d^r_k\|_P
\le \lambda\|e_k\|_P+\|d^r_k\|_P.
$$

The first-action optimization condition above does **not** include the post-allocation allowance $\eta$. That allowance appears in the subsequent transmitted-command check.

The current OSQP problem does not gain these norm constraints by changing its weights. Use an appropriate conic/nonlinear solver or a justified conservative formulation. If approximating the optimization, identify the approximation and independently verify the resulting constraints before declaring a feasible candidate.

### 4.3 Implement the stated cost accurately

The manuscript uses fixed componentwise pseudo-Huber stage costs, quadratic input cost, and a separate quadratic terminal cost.

The reviewed implementation aggregates predicted errors across channels/horizon and reweights the inherited quadratic cost. This is not automatically a correct majorization method for the stated componentwise objective.

Either implement the stated convex objective directly or derive the actual majorizer. If using iteratively reweighted optimization, preserve the component/time dependence and the terminal cost, and verify feasibility independently. Do not claim monotonic decrease of the manuscript’s objective solely because a different quadratic surrogate decreases.

Report the actual $w_j$, $s_j$, $R_u$, $Q_N$, horizon, solver tolerances, and termination rule.

### 4.4 Enforce eligibility, checked fallback, and deadline semantics

The post-allocation test is

$$
u_k\in\mathcal U,\qquad
\|A_ke_k+B_k(u_k-u^r_k)+d^r_k\|_P
\le \lambda\|e_k\|_P+\|d^r_k\|_P+\eta.
$$

Use the nominal-equivalent transmitted wrench. The fallback must pass this test before it can be used as the eligible checked fallback.

The reviewed implementation stores a failing fallback’s check result but still transmits that fallback after candidate rejection. Correct that behavior. Its radius-only flag must also be replaced by the full pre-action eligibility conditions if Algorithm 1 is claimed.

A suitable implementation sequence is:

```text
observe and update estimate
build causal history from estimates and earlier nominal transmitted commands
infer context
retain the previously committed current reference; commit the next reference sample
freeze allocator memory
check verified domains and construct feedforward, affine model, and fallback
trial-allocate fallback; check its nominal transmitted command

if any required eligibility condition fails:
    select the fixed supervisor command
else:
    solve the constrained MPC within the reserved computation budget
    if a timely feasible candidate exists:
        trial-allocate candidate from the same frozen allocator memory
        check candidate's nominal transmitted command
    select accepted candidate, otherwise the stored passing fallback

commit only the selected command packet and its allocator update
apply hidden faults on the plant side
integrate physical dynamics and record the outcome
```

The fixed supervisor is not automatically safe. Record its use and evaluate physical outcomes separately. An eligible control deadline failure must not be relabeled retrospectively as an inactive sample.

### 4.5 Commit the successor reference consistently

The recurrence at time $k$ uses a particular $r_{k+1}$ chosen before the command. Save that reference and use it to compute $e_{k+1}$ and the transition mismatch.

For a position-triggered waypoint task, a new decision based on $\hat x_{k+1}$ can schedule a later reference. It must not silently replace the already committed $r_{k+1}$. If a replacement is permitted, include its contribution explicitly in the mismatch term and its envelope.

Log both the control reference and the task reference used for performance scoring.

### 4.6 Checks that must pass before training/evaluation

- Perturb state/input and check derivative implementation against numerical directional differences away from clipping boundaries; this is a software check, not continuum verification.
- Compare optimizer residuals with independently evaluated dynamics, command, region, and first-action constraints.
- Force candidate rejection; verify the exact stored passing fallback packet is transmitted.
- Force fallback rejection; verify eligibility is false and the fixed supervisor is used.
- Force optimizer failure and a deadline overrun; verify the declared handling and logs.
- Confirm trial allocations do not mutate memory.
- Record separate candidate, fallback, and transmitted-command slacks. The candidate’s slack must not be relabeled as the transmitted action’s slack.
- Save the terminal observation so the final transmitted transition can be evaluated.

## 5. Rebuild behavioral supervision faithfully

**Source locations:** `stage5_data_train.py::collect_one`, `run_probe_branch`, `build_windows`, and `train_one`; `scsim/context.py::probe_signature`; `stage8_horizon.py` retrieval evaluation.

### 5.1 Construct matched probe groups

Create a documented set of probe initial-condition groups. Within each group, match physical position/orientation and initial linear/angular velocity, or apply a justified common rigid transformation where the model is equivariant.

For each stable parent-history sample:

1. Retain its persistent impairment condition in an offline branch.
2. Reset physical state to the group’s specified state.
3. Initialize and warm up the estimator through the same declared procedure.
4. Apply the same bounded excitation and probe reference.
5. Repeat with the prescribed noise draws or repetitions.
6. Record the physical response, estimator innovations, availability, and physical probe cost.
7. Keep the branch in the parent episode’s data split.

Use physical ground truth for the offline physical-response signature; this is allowed by the manuscript. Regress physical body-frame response against the **nominal-equivalent transmitted wrench**, not against the already fault-reduced physical wrench. Otherwise the regression can remove the actuation impairment that the signature should describe.

Do not pair arbitrary branches that start at different physical states and call them matched.

### 5.2 Restore the intended reference-family structure

Include multiple declared ordinary-history reference families in training when claiming cross-reference supervision. Pair histories from different reference families within matched probe groups.

Do not substitute “different impairment condition” for “different reference family.” Keep those identifiers separate.

A reference family used for cross-reference training cannot simultaneously be presented as an entirely unseen test family. Reserve an additional family, or a clearly specified disjoint parameter regime, for transfer evaluation.

### 5.3 Control optimization and loss comparisons

For `full` and `no_impact`, keep fixed:

- Architecture, initialization for each matched seed, and ordinary transition data.
- Prediction-loss definitions, multistep sampling, optimizer, training budget, and checkpoint-selection rule.
- Probe target normalization, where relevant, fitted using training data only.
- Controller design and tuning rules.

Use separate random-number streams for minibatch ordering, multistep sampling, and behavioral pair sampling. Activating the extra loss should not unintentionally change all subsequent prediction minibatches by consuming the same random stream.

The behavioral objective is the intended difference. The extra offline probe cost is real and must be reported.

For loss-weight selection, use a small declared development grid, for example $\lambda_I\in\{0,0.01,0.1,1\}$. This is a suggested diagnostic grid, not a required optimum. Freeze the selected rule before the final test. Do not select $\lambda_I$ using the final comparison table. If development selection chooses zero, report that outcome; the selected model does not demonstrate a behavioral-supervision benefit. A separately identified positive-weight model can remain an ablation.

Record loss scales and training/development curves. A decreasing behavioral loss does not rule out poor targets, inappropriate weighting, underfitting, or a conflict with prediction accuracy.

### 5.4 Evaluate prediction and retrieval properly

Use the same held-out ordinary histories for model-level prediction comparisons. Closed-loop tracking remains evaluated on each controller’s own resulting trajectory.

Report one-step and frozen-context multistep errors with explicit units/scaling. The current `prediction error` is a weighted MSE; do not label it RMSE without taking the appropriate square root and explaining the mixed state units.

For behavioral retrieval:

- Restrict candidates to different parent episodes and matched probe groups.
- Report cross-reference retrieval separately where claimed.
- Use a random-neighbor baseline drawn from the same eligible candidate pool.
- Specify the number of neighbors and aggregation.
- Report constant-context retrieval as N/A because identical latents provide no meaningful ranking; arbitrary tie-breaking is not behavioral information.

Evaluate whether behavioral geometry predicts control-relevant response, not just whether a training loss decreases.

### 5.5 Report the actual data budget

At the reviewed commit, 360 parent episodes is the total across all five splits. The training portion is 40 episodes per condition across four conditions: 160 episodes, approximately 96,000 simulated control steps before valid-transition/window filtering.

Produce a split table directly from dataset metadata with parent episodes, valid transitions, windows, probe branches, and extra probe transitions. Keep “all generated data” and “data used for training” distinct.

## 6. Build a sound numerical recovery demonstration

**Source locations:** `scsim/certificate.py` and `stage7_certificate.py`.

### 6.1 Correct the Jacobian enclosures

The reviewed `interval_jacobian_bounds` leaves yaw-dependent off-diagonal entries of $E_B$ equal to zero. For example, with $m=25$, current reference yaw zero, and successor yaw $0.01$ radians, the velocity cross-term changes by approximately $4.0\times10^{-5}$ while its returned bound is zero.

Derive and enclose all relevant entries over the declared domain:

- Current and successor reference orientation.
- State/input transformations.
- Learned residual derivatives at fixed context.
- Feedforward selector outputs.
- Every supported context and clipping branch.

A sampled derivative check can detect an incorrect enclosure but cannot certify the continuum. Use analytic bounds and/or validated interval calculations. A blanket factor of $1+10^{-9}$ is not, by itself, a justified bound on floating-point errors in matrix factorization, inversion, products, and norms.

If the verified model excludes the learned residual, label that result as a nominal-model result. To validate the proposed learned controller, include its residual in the same model and domain used by the proof.

### 6.2 Bound allocator error over the actual admitted domain

For a proposed fallback $u^r+Ke$, verify the allocation contribution

$$
\eta_q\ge
\sup\|P^{1/2}B\,\delta u_q\|_2,
\qquad
\delta u_q=u_{\rm nominal,allocated}-(u^r+Ke).
$$

The supremum must cover the declared state region, reference/feedforward domain, allocator memory, pulse branches, and schedules. Hidden actuator effects belong in the plant/prediction mismatch, not in the known allocation error.

The current maximum over 200 random points at `R_probe=1` is exploratory evidence, not a uniform upper bound. Sampling can miss the worst point, especially for discontinuous pulse rules. Clipping the fallback before measuring its allocation error also changes the quantity being bounded.

Use a justified analytic bound, verified branch enumeration, interval subdivision, or another sound enclosure. A conservative bound based on known command-set limits is acceptable if it still yields a useful region.

If only pointwise fallback checks are available, state that limitation and retain the exact runtime check. Do not claim a uniform fallback-realization lemma without establishing its premise.

### 6.3 Separate design budgets from statistical calibration

Choose candidate design budgets $d_{\rm cert}$ and $\mathcal E_{\rm cert}$ before final calibration. They may be informed by independent development evidence, but they are not automatically valid envelopes.

The current $d_{\rm cert}=0.08$ and healthy pointwise position p95 of 0.65 m do not establish the paper’s episode-level prediction and estimation guarantees.

Also, the current percentile of negative candidate slacks is not the manuscript’s conformal procedure. Selecting $\eta$ by development RMSE is controller tuning. Label it as tuning and freeze it before final calibration/test.

### 6.4 Use the manuscript’s frozen-policy episode procedure

A valid order is:

1. Train models and develop the controller.
2. Freeze the deployed hybrid policy: model, reference rule, allocator, supervisor, gate, $P,K,R,\lambda$, and design budgets.
3. Use an independent fitting population to fix context cells and score normalization/covariance objects.
4. Run complete final calibration episodes under that same frozen policy.
5. Compute one score per complete episode and error channel.
6. Accept or reject the candidate certificate by comparing calibrated envelopes with fixed budgets.
7. Evaluate on untouched test episodes from the declared population.

The policy uses fixed design budgets; final calibrated thresholds test those budgets. They must not silently retune the policy that generated the calibration episodes.

For an active source transition, evaluate

$$
d_k=e_{k+1}-A_ke_k-B_k(u_k-u^r_k)-d^r_k,
\qquad
\tilde x_k=x_k-\hat x_k.
$$

Use the actual selected nominal transmitted command and committed successor reference. The prediction error includes approximation and physical/estimator mismatch, not merely neural one-step training error.

With $I_a$ the source-eligible transitions in episode $a$, form

$$
S_a^D=\max_{k\in I_a}M_{D,c(z_k)}(d_k),
$$

$$
S_a^E=\max_{k\in I_a}
\max\{M_{E,c(z_k)}(\tilde x_k),M_{E,c(z_k)}(\tilde x_{k+1})\}.
$$

Both endpoint estimation errors use the **source context’s** cell. Keep onset transitions, exit-causing transitions, and the final successor observation. Episodes with no active transitions receive zero scores under the manuscript’s convention and remain in the dataset.

For channel error probability $\delta$,

$$
j_\delta=\left\lceil(n_{\rm cal}+1)(1-\delta)\right\rceil.
$$

Use the corresponding order statistic, or $+\infty$ when $j_\delta>n_{\rm cal}$. At $\delta_D=\delta_E=0.025$, 200 calibration episodes give index 196 for each channel. At least 39 are needed for a finite threshold under this convention; 39 is not a recommendation for statistical precision.

Calibrate each frozen policy/checkpoint for which a separate certificate claim is made. Do not pool scores from different trained controllers and assign the resulting threshold to each one without a justified population definition.

A balanced performance matrix is not automatically an exchangeable sample from an independently sampled condition mixture. State the calibration/test population and generate the certificate-test episodes accordingly.

The paper’s $\Pr(A\cap B_H)\le\delta_D+\delta_E$ is a marginal statement over calibration and test randomness. Do not report it as a conditional guarantee given certificate acceptance, or as a separate per-fault guarantee without additional justification.

### 6.5 Start with one useful, narrow certificate case

Attempt a small, explicitly declared population first:

- A held reference after any commanded jump has settled, or a feasible smooth trajectory.
- Consistent physical authority and nominal command mapping.
- A bounded context/reference domain.
- A realistic, clearly stated plant/estimator uncertainty range.
- A residual whose verified sensitivity fits the candidate design, if claiming the learned controller.
- An initial eligible state inside the proposed region.

Use a healthy case first to check the implementation, then test at least one prespecified unannounced impairment with nonzero plant/predictor mismatch inside the declared population. A healthy-only example does not demonstrate fault recovery.

This initial-state restriction is permissible, but report it. It does not establish entry into the region from an arbitrary fault state.

Aim to demonstrate

$$
s_{\rm cert}=\frac{b_r+d_{\rm cert}+\eta}{1-\lambda}
<R\le\min(R_U,R_{\rm corridor},R_{\rm chart}),
$$

and

$$
\Delta_R=(1-\lambda)R-b_r-d_{\rm cert}-\eta>0.
$$

A positive certificate claim also requires final calibration acceptance:

$$
\bar d\le d_{\rm cert},\qquad
\mathcal E_{\max}\subseteq\mathcal E_{\rm cert}.
$$

Both deterministic verification and final calibration acceptance are necessary. A positive radius calculated using unvalidated candidate design budgets is insufficient.

Report physical position/attitude projections of the region and error envelope. A numerically nonempty region that is too small to be visited, or an asymptotic bound larger than the task tolerance, is weak practical evidence.

For any $s_{\rm cert}<h<R$, compare the predicted entry time

$$
n_h=
\left\lceil
\frac{\log((h-s_{\rm cert})/(R-s_{\rm cert}))}{\log\lambda}
\right\rceil
$$

with uninterrupted eligible runs. The clock starts at an eligible state inside the region, not automatically at fault onset.

Do not obtain an apparently positive result by excluding active failures, changing the controller after calibration, or increasing an assumed force limit without increasing the corresponding physical authority.

### 6.6 Required certificate outputs

Report $P,K,\lambda$, verified domains, $b_r,d_{\rm cert},\eta_q,\eta$, estimation budgets, calibrated thresholds, certificate acceptance, $s_{\rm cert}$, each limiting radius, $\Delta_R$, and physical projections.

For each tested episode, retain:

- Active fraction and consecutive active durations.
- Number of episodes with zero active transitions.
- Prediction/estimation envelope violations.
- Command admissibility and transmitted-command decrease violations.
- Region exits and sampled physical safety violations.
- Supervisor/fallback counts and deadlines.
- Empirical entry times with non-entry and interrupted-run counts.

A high empirical coverage rate from almost entirely inactive operation does not demonstrate useful recovery. The theorem concerns sampled states; an intersample safety claim needs an additional bound.

## 7. Define the experiment matrix and fair comparisons

Run the central comparisons only after the corrections above pass. A large horizon or authority sweep is optional until these questions are answered.

### 7.1 Core methods

| ID | Method | What it isolates |
|---|---|---|
| M0 | Nominal model, no learned residual, same recovery controller structure | Benefit of a learned predictor with cost/check/fallback held comparable |
| M1 | Trained constant context, prediction losses only | Generic learned residual without changing context |
| M2 | Changing context, prediction losses only (`no_impact`) | Added value of inferring context, compared with M1 |
| M3 | Changing context with behavioral supervision (`full`) | Added value of behavioral supervision, compared with M2 |
| M4 | Same M3 checkpoint, only post-allocation candidate acceptance bypassed | Operational effect of that check |
| M5 | Fallback feedback only, using the same feedforward/gain/allocator and eligibility/supervisor rules | Whether MPC improves beyond repeated fallback feedback |
| M6 | Adaptive MPC comparator with documented estimator/update law and development tuning | Comparison with an independently defined adaptation baseline |

Retain the hardware-matched controller as an additional diagnostic comparator when useful. Its different objective and lack of recovery machinery must be stated.

For the clean **changing-context** comparison, use M2 versus M1: both have no behavioral loss. M3 versus M1 changes both context variation and supervision, so it does not isolate either mechanism.

For M5, retain the same context-conditioned feedforward if that is part of M3, so that the difference tests MPC planning. A separate nominal feedback-only baseline can answer whether learning itself is necessary.

For M4, retain the first-action optimization constraint, source eligibility rules, allocator, and solver-failure handling. Disable only the post-allocation candidate acceptance decision. Its safety guarantee is intentionally absent; evaluate it only in simulation.

Where each method requires its own verified design, use the same design objective, search budget, and constraints. Do not silently force an unfavorable common metric. Report the design differences and physical sizes. For a strict component ablation, retain the same design whenever feasible or explain why the comparison is no longer a single-component change.

### 7.2 Conditions and budget

Use four main conditions: healthy, actuator fault, perception degradation, and combined faults.

Retain the current suggested scale of three matched training seeds and 60 evaluation episodes per condition as a starting design, subject to a development pilot. This is not an IEEE requirement or a power guarantee.

For M1–M3, three seeds times four conditions times 60 episodes gives 720 evaluations per method, or 2,160 across those three methods. M4 should reuse the matching M3 checkpoint for each seed. Methods genuinely independent of training need not be duplicated merely to inflate the trial count. For a learned method, 60 scenario seeds times three checkpoint seeds produce 180 rollouts per condition but only 60 distinct matched scenario draws. Preserve that distinction in uncertainty calculations and table denominators.

Run M0, M4–M6 on the main conditions when affordable. A smaller predeclared subset focused on healthy and combined faults is acceptable for diagnostic baselines, with explicit limits on resulting claims.

Use matched episode identities for external randomness, plant mismatch, onset, and reference parameters. Keep random streams separate so controller-specific branching cannot change the exogenous disturbance/noise schedule.

### 7.3 Reference/task choices

For time-indexed tracking claims, use an externally specified reference common to the compared methods.

For the hardware-style position-triggered waypoint task, state that all methods share the waypoint task and switching rule, but may switch at different times. Report completion time, final-waypoint attainment, and errors for each stage. Do not claim identical temporal references.

The smooth reference’s speed/acceleration should be feasible under the declared nominal authority. An additional held-out reference family can test transfer, provided it was not used for training or tuning.

### 7.4 Evaluation fairness

Tune the adaptive comparator on development data and check its update timing and input convention. Its identification regressor must use the known nominal transmitted command associated with the observed state increment. Use comparable objective/constraint machinery when attributing improvements specifically to learning.

Record the additional probe-generation cost of M3. Giving M2 access to the same ordinary prediction data is required. A secondary equal-total-data/computation comparison can assess whether extra probe data would be more useful as additional ordinary training data.

Do not select the best-performing training seed for the main table. Preserve failed training runs and report the predeclared handling.

## 8. Use practical metrics and correct uncertainty estimates

### 8.1 Define task success before the final test

The reviewed `recovery_tolerance_m` is 0.983663 m. It was selected from healthy zero-context terminal error. That is a baseline-relative threshold, not an independently justified task tolerance.

Choose a position tolerance, yaw tolerance, dwell time, and completion deadline justified by the spacecraft task. If no task specification exists, declare provisional values and explain them. For example, 0.15 m, 5 degrees, and 2 seconds could be a development starting point, but they are not measured requirements or guaranteed feasible targets.

Keep the chosen metric fixed across methods. If it is unattainable under the modeled estimator/authority, report the failure and its cause instead of broadening it after viewing test results.

### 8.2 Required metrics

For each episode, compute physical position error against the declared scoring reference.

| Metric | Definition/interpretation |
|---|---|
| Full-episode position RMSE | Includes initial transit; useful for continuity with hardware tables |
| Fixed-window post-onset RMSE | Same window relative to onset for every compared method |
| Post-onset peak error | Avoids an initial setpoint jump dominating every peak |
| Yaw error | Use the same declared angle convention |
| Final-waypoint task success | Position and yaw tolerances maintained for the dwell time before deadline |
| Completion time | Include failures/non-completions explicitly |
| Post-fault time to tolerance | Time from onset to the start of a qualifying dwell interval |
| Maintenance versus reacquisition | Separate episodes already within tolerance and remaining there from episodes requiring recovery |
| Candidate rejection/fallback/supervisor rates | Identify which controller actually generated the actions |
| Computation | Full-loop latency, solver failures, and deadline misses on the stated machine |

If a trajectory leaves tolerance after an early two-second dwell, task-completion/sustained-performance metrics must reveal it. A transient return is not equivalent to persistent successful tracking.

When episodes are incomplete or terminated, report the reason and count them in task-success denominators. Explain how continuous metrics handle truncated records. Do not report successful-run averages as unconditional method performance.

### 8.3 Estimate uncertainty at the correct levels

Use paired episode differences for matched controller comparisons. Do not bootstrap time samples or overlapping history windows as independent experiments.

For learned methods, distinguish:

- Episode uncertainty conditional on the evaluated checkpoints.
- Training-seed variation.
- Uncertainty for a broader training-and-deployment population.

The current bootstrap keeps the three checkpoints fixed within each sampled episode block. Its intervals must be labeled accordingly.

For broader uncertainty, use a suitable crossed resampling procedure over matched training seeds and episode identities, preserving seed pairing. With only three training seeds, report the seed-level means and acknowledge limited precision. More episodes cannot replace missing training-seed diversity.

Do not broadcast `full_no_check_s0` against `full_s1` and `full_s2` and call it a same-checkpoint ablation. Compare each checkpoint with its own check-disabled deployment.

Select one primary endpoint and primary comparison in advance: recommended, post-onset RMSE for M3 versus M2, with task success as a practical outcome. Interpret the size of an effect against the task tolerance as well as its confidence interval. Qualify exploratory comparisons and multiple-condition significance claims.

## 9. Hardware consistency and deployment evidence

The simulator can complement the spacecraft hardware experiments, but it cannot retroactively establish that the hardware ran the new controller.

Create a short implementation table for the actual hardware run, corrected simulated hardware comparator, and proposed simulated controller. Include horizon, cost, active learned components, residual input, state estimator, command chain, and recovery checks.

The repository labels the hardware horizon as 12, whereas the manuscript lists 10. Verify against the configuration/checkpoint tied to the reported hardware logs and correct the paper accordingly. A parameter marked “CONFIRMED” in this repository is provenance information from its authors, not an independently inspected hardware source in this review.

For mass, inertia, valve thrust, pulse timing, and estimator settings, identify which values were measured, read from deployment code, fitted, or assumed. Provide source/run identifiers where available.

Fit the perception surrogate on designated hardware data and validate its behavior on separate hardware records where possible. Agreement with the same envelopes used for fitting is calibration agreement, not independent replication. Report time-series behavior and transient/error statistics in addition to broad p95 bands.

Call the perception experiment a measurement/estimator degradation surrogate unless actual image corruption and the visual estimator are simulated. Do not equate a dropout probability with a percentage of taped camera area.

The hardware remains the main physical demonstration. The corrected simulation should supply controlled ablations and theory evidence that the existing hardware records cannot provide.

## 10. Logging and reproducibility deliverables

Extend the logs enough to reproduce the important claims.

| Group | Required contents |
|---|---|
| Run identity | Code commit, configuration hash, checkpoint hash, dataset/split version, training seed, episode seed, scenario ID |
| State/reference | Estimate, physical state, current/committed-next control references, task scoring reference, estimator masks/innovations |
| Learned model | Context, input convention, feedforward, affine $A,B,d^r$, model/version reference |
| Commands | Candidate and fallback proposals; pre-fault selected pulses; nominal transmitted wrench; evaluator-only physical actuation |
| Allocation | Memory before trial, selected packet, committed memory update |
| Decisions | Pre-action eligibility and reason, candidate feasibility, candidate/fallback/transmitted slacks, selected action source |
| Timing | Full control-loop time, solver time, allocation/check time, deadline status |
| Certificate | Mismatch, both endpoint estimation errors, score cells, envelope membership, region and physical safety checks |
| Outcomes | Task metrics, completion/failure status, termination reason, post-onset and eligible-run clocks |

Large constant matrices can be stored once per design and referenced by ID. Time-varying quantities needed to reconstruct the recurrence must remain recoverable.

The corrected campaign should produce:

- A configuration/dependency manifest and an installation command verified in a clean environment.
- A split manifest with counts and parent/branch identities.
- Checkpoints with architecture and normalization metadata.
- Per-episode metrics and seed-level summaries.
- Enough transition records to reproduce the primary figures and every claimed bound violation count.
- Certificate design/calibration/verification artifacts.
- Scripts that regenerate the tables from the stored episode metrics.
- A report that distinguishes fitted parameters, simulator assumptions, and measured hardware quantities.

Treat original results as an immutable development snapshot. Regenerated files must identify the corrected commit and data version. Do not rely on a configuration hash alone when controller source or checkpoint weights changed.

## 11. Execute the work in this order

| Milestone | Work | Completion criterion |
|---|---|---|
| A | Preserve prior campaign; write command/frame/state conventions | Every module uses an unambiguous interface |
| B | Correct hidden-fault separation, physical rotation, pulse/authority handling | Section 2–3 checks pass |
| C | Implement predictor/feedforward/MPC/check/gate/fallback/reference semantics | Section 4 checks pass, including intentionally failed candidates and fallbacks |
| D | Correct probe groups, training splits, metrics, and comparison definitions | Supervision pairs and metrics can be traced to their specified physical quantities |
| E | Run a small development pilot | No information-flow, physics, alignment, or solver-feasibility failures; baselines behave as designed |
| F | Regenerate training data and train matched seeds; tune on development data | Model/checkpoint/controller selection rules are frozen |
| G | Verify a candidate recovery design and fit score objects | Correct continuum/allocator bounds and fixed design budgets are available |
| H | Run fresh final calibration and evaluate certificate acceptance | Acceptance or rejection recorded without retuning on those episodes |
| I | Run untouched main comparisons and certificate-population test episodes | Complete episode metrics, failures, and seed-level results retained |
| J | Generate paper tables/figures and revise claims | Every claim maps to an implemented mechanism and a reproducible result |

The current `run_all.py` order is not itself proof that these dependencies hold. Update the pipeline so stages verify the versions of the models, data, estimator fit, and design objects they consume. Development tuning and final statistical calibration should be separately named stages.

A suggested small pilot is 5–10 episodes per main condition for a subset of controllers, plus the targeted semantic checks above. Pilot episodes are development data and must not enter the final test set. Increase pilot size only to resolve a concrete remaining implementation risk.

If a candidate certificate fails final acceptance, retain that outcome. A redesign can use the failure as development information, but its next acceptance assessment requires fresh independent final calibration. Do not repeatedly tune against the same calibration set until it passes.

## 12. What to put in the paper

Use compact results that answer the contribution questions directly.

### Table A: corrected main controller comparison

Rows: conditions and selected core methods. Columns: number of distinct scenario draws, training seeds and total rollouts, post-onset RMSE with uncertainty, task success, recovery/completion time with failures, and post-onset peak error. Do not label all reused-scenario rollouts as independent scenario draws.

Keep full-episode RMSE available for comparison with existing hardware results. Do not obscure the different scoring windows.

### Table B: causal comparisons between components

Report M3–M2 for behavioral supervision, M2–M1 for changing context, M3–M4 for the post-allocation candidate check, and M3–M5 for MPC beyond fallback. State exactly which design components/checkpoints are shared.

If only a subset of conditions is used for a comparison, name it and restrict the claim accordingly.

### Table C: numerical recovery case

Report the frozen design and calibrated quantities, strict margin, physical region/error sizes, eligible activity and durations, and violation counts. Include a failing stress case to illustrate the declared limit if space permits. A failing case does not substitute for a positive useful case when practical recovery certification is a central contribution.

### Figure A: representative closed-loop behavior

Use aligned panels for physical tracking error, estimator error, nominal versus physical actuation, and action source/eligibility. Mark fault onset and reference changes. Choose the representative episode by a declared rule and retain aggregate evidence in the tables.

### Figure B: bound and recovery behavior

Plot the verified error bound and measured error on eligible intervals, source/successor envelope membership or slacks, and physical projections. Distinguish empirical onset recovery from the theorem’s eligible-start clock.

### Figure C: behavioral supervision

Show the held-out M3–M2 effect with seed-level variation and one directly relevant model-level result, such as cross-reference retrieval or multistep prediction. A latent visualization alone does not establish control benefit.

Update the architecture figure to depict the implemented offline supervision, context-conditioned predictor/feedforward, constrained MPC, allocation check, and fallback/supervisor. Replace “oracle” with “hand-tuned context” wherever that is the actual hardware comparator.

## 13. Claim decisions after the corrected campaign

| Corrected evidence | Defensible conclusion | What to avoid |
|---|---|---|
| M3 meaningfully improves over M2 with supported uncertainty | Behavioral supervision helps on the tested task/population | General claims across unseen faults/robots |
| M3 and M2 are indistinguishable | No demonstrated supervision benefit at the tested settings | Treating a reduced training loss as performance validation |
| M3 is worse than M2 | Report the adverse result; revise/remove the unsupported benefit claim | Concealing the ablation or selecting a favorable seed |
| M2 improves over M1 | Changing context helps beyond a constant learned residual | Attributing M3–M1 entirely to changing context |
| M3 improves over M5 | MPC planning contributes beyond the chosen fallback | Assuming the rejection-rate result alone proves this |
| M3–M5 differences are practically small with sufficiently precise uncertainty, and fallback usage is high | Evidence that fallback accounts for much of the measured performance | Treating a nonsignificant difference alone as equivalence; otherwise report only that added MPC benefit was not demonstrated |
| A useful region is verified and final calibration accepts | A conditional recovery demonstration for the specified population/domain | Hardware certification or global recovery claims |
| No candidate region passes | No certificate found under the tested designs and bounds | Claiming a universal impossibility theorem from a finite search |

Revise these current report statements specifically:

- Replace “mass and inertia must be known within ±5%” with the actual outcome for the tested design grid and sufficient bounds.
- Replace “step references are structurally uncertifiable” with the outcome when the sampled reference jump is included in the tested domain. Recovery after a held reference settles is a different case.
- Replace “the residual is physically nonsensical” with a statement about the particular sensitivity enclosure and design budget. A large upper bound is not an attained derivative.
- Replace “the loss decreased, so this is not a training failure” with the measured optimization result and the remaining target/weighting/generalization questions.
- Correct “double the training mismatch”: the reviewed code uses ±15% stress versus ±10% training.
- Correct total-data counts, prediction MSE labels, constant-latent retrieval, and same-checkpoint ablation descriptions.
- Correct the reported duty conversion: the reviewed implementation uses `4.829 * F / 25 - 0.07686` seconds before clipping, not `4.829 * F - 0.07686`. State the units and the calibration source.
- Do not call the simulated gain an independent replication of hardware solely because the simulator was fitted to hardware error envelopes.
- Do not state that new allocated-command checks were validated on hardware unless they actually ran in the scored hardware experiments.

## 14. Submission readiness criteria

The experimental package is ready to support the manuscript when all applicable items below hold:

- [ ] Hidden fault information and physical ground truth are excluded from online policy inputs and pre-action checks.
- [ ] Physical thrust follows true spacecraft orientation and actuator authority is represented consistently.
- [ ] The implemented prediction, feedforward, optimization, gate, and fallback agree with the paper.
- [ ] The behavioral-loss experiment uses matched probes and the specified training objective.
- [ ] Main comparisons isolate the stated mechanisms with matched checkpoints/episodes where required.
- [ ] Recovery/task metrics use explicit, meaningful thresholds and include failures.
- [ ] Results report training-seed variation and the correct interpretation of confidence intervals.
- [ ] Numerical verification is sound for the implemented model and domain.
- [ ] Any statistical certificate uses complete episodes from the stated frozen-policy population.
- [ ] A practical certificate claim has a useful positive demonstration, not only failed searches.
- [ ] Hardware and simulation implementations and claims are distinguished accurately.
- [ ] Figures, tables, and prose can be regenerated from versioned artifacts.

These are evidence requirements for the claims, not a promise of acceptance. A corrected study with an honest negative result can still be scientifically valuable. For the present paper, the strongest path is a faithful implementation, focused component comparisons, and one useful recovery demonstration before expanding the experiment count or theoretical scope.

## Source index

All links below are pinned to the reviewed commit.

- [Results report](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/results/results.md)
- [Plant, allocator, and fault implementation](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/plant.py)
- [Episode runner](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/runner.py)
- [Controller policies](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/controllers.py)
- [MPC implementation](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/mpc.py)
- [Training and probe generation](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/stage5_data_train.py)
- [Context model and signatures](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/context.py)
- [Scenarios and history features](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/scenarios.py)
- [Reference generators](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/reference.py)
- [Comparison and metrics](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/stage6_methods.py)
- [Stored comparison results](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/results/stage6_methods.json)
- [Numerical certificate functions](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/scsim/certificate.py)
- [Certificate evaluation](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/stage7_certificate.py)
- [Transfer and retrieval evaluation](https://github.com/baaqerfarhat/Sc_sim_env/blob/0d0088e474c7b5460651e486eb6ea84760132941/stage8_horizon.py)


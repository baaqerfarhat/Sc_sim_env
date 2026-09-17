# Simulation validation protocol for the RA-L manuscript

Prepared 15 September 2026. This document specifies experiments to implement; it contains no newly generated simulation results.

**Purpose.** Add one integrated planar-spacecraft simulation study that tests the two contributions currently missing direct evidence: behavioral supervision of the context and useful operation of the recovery certificate. Keep spacecraft hardware as the primary experimental contribution. Simulation should explain when the method works, why its learning objective matters, and where its guarantees cease to apply.

**Manuscript reviewed:** Multimodal_Context_Learning_for_Actuation_and_Perception_Fault_Tolerant_Model_Predictive_Control (1).pdf, nine-page revision. References below use its numbering: causal history (2); behavioral signature/loss (4)–(5); affine error dynamics (8); recovery conditions (9)–(14); optimization and transmitted-command check (15)–(19); guarantees/calibration (20)–(29); training objective (32); and metric verification (34)–(35).

This protocol complements [Spacecraft_Experimental_Strengthening_Guide.md](Spacecraft_Experimental_Strengthening_Guide.md). Numerical settings below are proposed simulation choices, not recovered hardware specifications or measured results.

## 1. Questions the study must answer

1. **Does behavioral supervision help?** Does adding the probe-based loss improve held-out behavioral retrieval, prediction, and physical tracking over the identical architecture trained without that loss?
2. **Does context help beyond a weak zero-context comparator?** Does the method outperform a separately trained constant-context predictor and a credible adaptive MPC baseline?
3. **Is certified recovery useful?** Can the implemented predictor, command allocator, and uncertainty budgets produce a nonempty recovery region, with enough actual activity to make the entry-time result relevant?
4. **Why check commands after allocation?** Can quantization or pulse realization invalidate a feasible proposed command, and does the checked fallback handle such cases?
5. **What limits recovery?** How do combined perception and actuation degradation affect tracking, eligibility, command authority, and uncertainty margins?

Do not add a new robot platform or another theoretical framework. The strongest package is one matched comparison table, one certificate table, and one synchronized recovery figure. A severity map is a useful fourth item if space permits.

## 2. Phase A — Freeze the implementation being evaluated

Create a configuration and checkpoint manifest before collecting final results. Identify the encoder, residual, estimator, allocator, feedforward solver, MPC, fallback, supervisor, training objective, and reference library. Each run must identify its exact manifest.

Resolve these manuscript ambiguities first:

- Equation (16) specifies fixed pseudo-Huber state costs, but Section V-A also mentions a cost-head MLP and weight floors. For this study, use the stated fixed-cost design unless the manuscript is deliberately revised to match another implementation. Disable unused heads and record that choice.
- The six nominal weights do not fully specify (16). Record state ordering and scaling, every \(w_j,s_j\), \(R_u,Q_N\), and feedforward regularization.
- Train the full model with the complete objective (32). MSE pretraining alone does not implement the proposed behavioral-supervision contribution.
- Specify the coordinate frame and units of the residual's clipping. Componentwise clipping in a world frame is generally not rotation equivariant. Canonical/body-frame prediction followed by rotation can preserve the Appendix II construction.
- Specify solver deadlines, tolerances, deterministic tie handling, and warm-start memory. Include any solver state affecting feedforward selection in the verification domain or eliminate that dependence.

Reuse the stated settings where supported: \(T_s=0.1\) s, horizon \(N=10\), latent dimension 32, three transformer layers, four heads, and width 128. Implement the indices of (2) literally: with \(L=10\), the innovation/availability history \(k-L:k\) has eleven timestamps, whereas the command and nominal-residual histories have ten. State any alternate indexing explicitly.

**Completion criterion:** every experiment can be reconstructed from a manifest, and the algorithm described in the paper matches the algorithm executed.

## 3. Phase B — Build a plant that is distinct from the predictor

### 3.1 Physical plant and frames

Use the six-state planar spacecraft

\[
x=[p_x,p_y,\psi,v_x,v_y,\omega]^\top,
\]

with world-frame position and velocity, unwrapped yaw on the declared chart, and body-frame commanded wrench. Use the actual eight-thruster geometry if available. Otherwise define and publish a plausible eight-thruster simulation fixture; do not describe its geometry, mass, or inertia as measured hardware values.

A suitable continuous-time plant is

\[
\dot p=v,\qquad \dot\psi=\omega,
\]
\[
\dot v=m^{-1}R(\psi)F^b-D_vv+a_{\rm ext},\qquad
\dot\omega=J^{-1}\tau-d_\omega\omega+\alpha_{\rm ext}.
\]

Let \(G\in\mathbb R^{3\times8}\) map nominal unit duties to body wrench, including the chosen thruster ratings. The allocator produces the transmitted duty vector \(c_k\). The controller's command history must contain

\[
u_k=Gc_k,
\]

not the unallocated proposal and not the unknown fault-affected wrench.

One higher-fidelity actuator model is

\[
\dot a_i=\{\operatorname{sat}_{[0,1]}(\eta_i c_i+b_i)-a_i\}/\tau_i,
\qquad [F^{b\top},\tau]^\top=Ga.
\]

Here effectiveness \(\eta_i\), bias \(b_i\), and actuator state \(a_i\) are hidden plant quantities. If the real interface executes pulses within a control slot, resolve those pulses rather than replacing them silently by continuous duties. Retain the allocator's memory and minimum-pulse rules.

The plant may have additional actuator states although the controller tracks six spacecraft states. The aggregate discrepancy in (8) then includes the consequences of those unmodeled dynamics.

### 3.2 Nominal model and mismatch

Use a nominal predictor with the same physical interfaces but fewer effects: nominal mass/inertia, idealized thrust response, and the selected discrete integration. The learned residual corrects this model in estimate space.

The evaluation plant should integrate continuous dynamics more finely than the MPC sample period—for example at \(T_s/10\), refined if pulse timing or actuator lag requires it. Check integration refinement on representative healthy and impaired trajectories.

Start with a limited, interpretable mismatch set:

| Quantity | Example development choice | Held-out evaluation |
|---|---|---|
| Mass and yaw inertia | Independent perturbations within \(\pm10\%\) of fixture values | Interior draws for the calibrated population; separately labeled \(\pm15\%\) stress cases |
| Actuator lag | \(\tau_i/T_s\in[0.1,0.5]\) | New draws; larger lags only in the stress suite |
| Duty realization | Actual quantizer, saturation, and pulse logic | Same implementation; separately designated coarser-resolution stress test |
| External disturbance | Bounded force/torque process | Independent realizations under the declared law |

These are examples to adjust during development. Freeze them before final calibration. Do not generate the test plant by directly rolling out the same learned affine predictor used by MPC: that would make small prediction errors and certificate compliance largely built in.

## 4. Phase C — Separate observations, estimation, and scoring

Generate noisy sensor observations from the physical plant and run a causal estimator. Prefer the same estimator interface and sensor channels as the hardware. A measurement-level surrogate may combine intermittent pose observations with gyro and acceleration observations; describe it accurately as such.

For pose observations, define translation/yaw noise, bias dynamics, update timing, dropout blocks, and availability flags. A missing observation must cause the estimator's prescribed missing-data behavior. Do not inject ground truth as a replacement measurement.

Perception degradation can vary pose noise, bias, and dropout duration. If no camera renderer or recorded-image pipeline is used, call this a **measurement-level perception-degradation experiment**, not a reproduction of half-camera visual occlusion.

At sample \(k\):

1. Deliver only observations available by the control timestamp.
2. Update the estimator and modality innovations/masks.
3. Construct (2), using the previous transmitted command and the newly available estimate.
4. Infer \(z_k\), commit the next reference, compute feedforward, and execute the controller/allocator checks.
5. Advance the plant and collect the next observations.

The encoder, feedforward, controller, and gate must not receive true state, impairment identity/effectiveness, onset time, probe outcomes, or future innovations. Ground truth is allowed for offline probe signatures, calibration of estimation error, and physical scoring.

Train \(f_\theta\) to predict the **next estimate**, as stated in (3), rather than switching its target to physical truth. Log both \(\hat x\) and \(x\) so prediction mismatch and physical estimation error remain distinguishable.

**Completion criterion:** a timestamp/field audit confirms that changing a hidden fault label without changing available observations cannot directly alter controller inputs.

## 5. Phase D — Generate data and behavioral targets without leakage

Use five separate data stages. Split by parent episode before constructing overlapping windows or branching probes.

| Stage | Permitted use | Not permitted |
|---|---|---|
| Training | Normalizers, probe signatures, network fitting | Using final test responses |
| Development | Hyperparameters, references, budgets, domains, controller decisions | Treating resulting choices as independent calibration |
| Independent fitting | Context cells, score means/covariances, fixed fallback for sparse cells | Redesigning the already frozen policy |
| Final calibration | Episode-max thresholds and one-time certificate acceptance | Tuning a rejected certificate using these outcomes |
| Test | Declared metrics under the frozen design | Checkpoint, region, threshold, or scenario selection |

All windows and probe branches inherit their parent split. Test scenarios may share prescribed reference families with training where appropriate, but must not duplicate parent trajectories or probe branches.

### 5.1 Ordinary histories and probes

Collect ordinary closed-loop histories under a documented behavior policy and varied persistent impairments. Preserve onset transitions in one-step prediction data. Use impairment-stable windows for the multistep objective and probe pairing, consistent with the paper.

For a qualifying history, create a separate simulator branch retaining its persistent impairment. Reset to a matched physical probe initialization, warm up the estimator under a fixed protocol, and apply the same bounded exciting command/reference sequence for all parent conditions within that group of probe initializations.

Build the signature (4) using the regularized response fit, innovation statistics, availability, and physical probe tracking cost. Enforce the excitation test; discard under-excited branches from the signature loss while retaining eligible ordinary transitions for prediction.

Fit normalization and component scales using training data. Specify masks, common-valid-entry distances, pair weights, groups of matched probe initializations, and cross-reference pairing. Do not allow future probe outcomes to become encoder inputs. Report the extra simulator branches, total transitions, and training compute used to construct supervision; this offline cost is part of the method.

### 5.2 Train and evaluate the representation

Use at least three independent training seeds. Match initial weights where architectures allow, data, optimizer budget, checkpoint selection, and prediction-loss weights for the full and no-behavioral-loss variants. The intentional difference is \(\lambda_I\).

Evaluate one-step and frozen-context multistep prediction on a **common held-out sequence set**, with identical recorded commands for all predictors. Keep this open-loop prediction evaluation distinct from each controller's closed-loop trajectories.

For retrieval, use nearest latent neighbors from other parent episodes and other reference families within the same group of probe initializations. Fix the neighbor count (for example five), the handling of queries with too few valid candidates, and tie handling before testing. Report the average prescribed behavioral distance. A constant-context model has no informative latent ranking, so mark retrieval N/A rather than assigning an arbitrary favorable result. Compare this score with a random-neighbor reference so that an apparently small distance is interpretable.

## 6. Phase E — Run a small, credible baseline set

| Variant | Implementation | Question answered |
|---|---|---|
| Trained constant-context MPC | Retrain the residual with one constant context | Is inference of changing context useful? |
| Adaptive MPC | Bounded, regularized RLS correction to velocity/angular-rate increments, updated from available estimates and transmitted commands | Does the representation beat a simple online adaptation mechanism? |
| No behavioral loss | Full architecture and prediction objectives, \(\lambda_I=0\) | What does behavioral supervision add? |
| Full method | Complete objective and Algorithm 1 | Main method |
| Full method without post-allocation acceptance check | Same trained model and proposal optimization; bypass only the candidate check after allocation | Why verify the transmitted command? |

Document RLS regressors, parameter bounds, forgetting factor, initialization, update timing, and tuning budget. Give it the same permitted sensor/estimator information. RLS must not receive actual effectiveness or fault-onset labels.

For the targeted no-check variant, retain the MPC first-action constraint, source eligibility logic, allocator, and handling of optimization failure. In particular, when optimization succeeds, send the trial-allocated candidate without rejecting it through (17); retain the stored fallback behavior for solver failure. This isolates candidate acceptance after allocation. Removing the entire gate, first-action condition, and fallback together would answer a different question.

Run that diagnostic chiefly on prespecified near-boundary states and pulse/quantization-sensitive commands. Do not require it to fail. If the chosen implementation rarely changes feasible proposals enough to matter, report that result.

All primary methods use the same task references, physical limits, estimator, timing, and scenario draws. Share exogenous initial conditions, fault schedules, and indexed noise/disturbance streams; let each closed loop generate its own state trajectory.

Use the same certificate construction rules for full versus no-impact models. A common verified certificate is helpful if feasible, but should not be forced. When regions differ, report region and activity changes as part of the method effect. Do not compare raw radii across different \(P\) scalings; compare physical projections and realized performance. No baseline inherits the full model's verification automatically.

Conventional and adaptive MPC baselines may retain their documented constraint-handling methods as performance comparators. They do not need the proposed certificate unless a corresponding guarantee is claimed. Report their handling of infeasibility and limits, then compare actual physical outcomes and failures under matched conditions.

The five variants establish mechanism and baseline utility; they do not by themselves establish superiority over all current context-learning methods. For a state-of-the-art performance claim, add a faithful, well-tuned representative published context-conditioned dynamics/MPC comparator with its documented training protocol. Otherwise keep the claim comparative to the evaluated methods. Do not rename the no-behavioral-loss ablation as another published algorithm unless that algorithm is actually implemented.

## 7. Phase F — Freeze a compact scenario matrix

Use four main conditions: healthy, actuator degradation, perception degradation, and combined degradation. Include station keeping and at least one moving reference; use a held-out reference family or parameter range to test transfer.

| Factor | Proposed example |
|---|---|
| Episode length | 60 s, extended during development if entry/dwell times require it |
| Impairment onset | Draw uniformly from 15–20 s |
| Actuator effectiveness | \(\eta\in\{1.0,0.7,0.4,0.2\}\) on a declared thruster or group |
| Pose-observation noise | Nominal standard deviation multiplied by \(1,2,4\) |
| Missing pose updates | Block durations \(0,0.2,0.5,1.0\) s |
| Combined conditions | Prespecified selected actuator/perception pairs |
| Limiting cases | Complete loss of an essential authority direction or extended observation loss |

Here \(\eta=0.7\) means 70% remaining modeled effectiveness. It is **not** an interpretation of the hardware's ambiguous “70%” setting. Label simulator effectiveness explicitly.

Do not run the full Cartesian product initially. Select moderate main conditions, then a small severity grid around the observed transition from effective tracking to degraded operation. Use independent held-out parameter draws within the declared evaluation distribution. Reserve beyond-training or beyond-calibration extremes for a clearly separated stress test.

For performance comparisons, target three training seeds and 50–100 matched episodes per main condition, adjusting to observed variability and available compute. Choose the final count before inspecting final effects.

Define physical recovery before testing. For example, select position tolerance relative to a stated task length scale \(L_{\rm task}\), such as \(0.05L_{\rm task}\), yaw tolerance such as \(5^\circ\), and a two-second dwell. These are proposed choices, not hardware requirements. Report their actual physical values and justify their task relevance.

Measure onset-to-recovery from impairment onset to the first entry completing the dwell before a fixed deadline. Preserve the original task reference for comparison if the supervisor changes the online reference. Healthy trials use a prespecified tracking interval. Aborts and timeouts count as failures.

## 8. Phase G — Construct and test the recovery certificate

### 8.1 Deterministic verification

Implement the reference descriptor, feasible feedforward selector, actual clipped residual, Jacobians, and affine predictor described in Sections III and Appendix II.

1. Define compact reference/context/allocator-state domains and corridor/chart conditions.
2. Solve the representative LMIs (34) for candidate \(P,K\).
3. Verify the continuum using outward-rounded derivative/matrix bounds and (35). Include clipping branches or exclude them explicitly; random Jacobian sampling is only a diagnostic.
4. Bound reference defects, allocator error, and command/corridor/chart radii for the admitted domain.
5. Select \(R,d_{\rm cert},E_{\rm cert},\eta\) using development data and deterministic calculations; freeze them with the policy.

Establish the numerical inequalities

\[
s_{\rm cert}=\frac{b_r+d_{\rm cert}+\eta}{1-\lambda}
<R\le\min(R_U,R_{\rm corridor},R_{\rm chart}).
\]

Uniform allocator verification supports Lemma 1. If only pointwise allocated fallback checks are available, state that limitation and retain the runtime check; do not claim the unverified uniform premise.

Run trial allocations of candidate and fallback from the same frozen memory and intended slot. Transmit the stored selected duties and commit only their associated memory update. A second allocation after memory mutation is not equivalent.

### 8.2 Freeze first; calibrate once

There is no need to claim certification while collecting calibration trajectories. Freeze the design and run its implemented gate/controller in the simulator as a **candidate policy**. Its activity depends on fixed design budgets and pre-action checks, not on final conformal thresholds.

Use an independent fitting set to define a modest number of context cells and regularized score statistics. Use the fixed global fallback for sparse cells.

As a practical starting target, collect **200 calibration and 100 separate test episodes per frozen policy receiving a certificate claim**. Different training seeds or redesigned controllers are different policies; do not pool them to manufacture a larger calibration sample.

Draw calibration and certificate-test episodes from the same declared distribution—for example an independently sampled mixture of the four main conditions with fixed probabilities and duration. A separately balanced performance matrix or OOD stress set is not automatically this exchangeable population.

With \(\delta_D=\delta_E=0.025\), each channel uses order statistic

\[
j=\lceil(n_{\rm cal}+1)(1-0.025)\rceil.
\]

For 200 episodes, \(j=196\); 39 is only the minimum permitting a finite threshold, not a recommendation or a usefulness guarantee.

Compute episode maxima over all recovery-active source transitions, retaining both endpoint estimation errors under the source context. Include onset transitions, exits, inactive periods, and zero-active episodes exactly as specified in (25). Do not truncate runs after lost authority.

Evaluate the one-time acceptance event

\[
A=\{\bar d\le d_{\rm cert},\ E_{\max}\subseteq E_{\rm cert}\}.
\]

If it fails, report rejection. A redesign using those outcomes requires fresh independent final calibration/test data. Selecting a seed, region, or policy after looking at calibration results also changes the procedure; preserve the rejected attempts in the experiment record.

The statistical statement is marginal over calibration and test episodes, conditional on earlier fixed objects. It is not a 95% guarantee conditional on accepting this particular calibration sample. Simulation calibration supports the simulated population only. Update Section IV-B's “hardware fitting split” wording to identify the actual population being calibrated.

### 8.3 Show usefulness, not merely acceptance

Report physical region projections, active-transition fraction, episodes with any activity, zero-active episodes, and consecutive activity durations.

For a chosen \(s_{\rm cert}<h<R\), calculate

\[
n_h=\left\lceil
\frac{\log[(h-s_{\rm cert})/(R-s_{\rm cert})]}{\log\lambda}
\right\rceil.
\]

Count how many eligible intervals last at least \(n_hT_s\). Check the applicable geometric bound from the eligible start. Keep this separate from empirical onset-to-recovery time.

Compute the errors from the actual closed-loop records, with $e_k=\Phi_{r_k}(\hat x_k)$ and the transmitted-equivalent $u_k=Gc_k$:

$$
d_k=e_{k+1}-A_ke_k-B_k(u_k-u_k^r)-d_k^r,
\qquad \tilde x_k=x_k-\hat x_k.
$$

This $d_k$ includes affine approximation error and estimator-transition mismatch. It is not merely the nonlinear network's one-step prediction residual. For an active source $k$, evaluate both $\tilde x_k$ and $\tilde x_{k+1}$ using the envelope associated with the source context $z_k$.

Let $D_k=\sup_{d\in\mathcal D(z_k)}\|d\|_P$. Log the two distinct slacks:

$$
a_k^{\rm cmd}=\lambda\|e_k\|_P+\|d_k^r\|_P+\eta
-\|A_ke_k+B_k(u_k-u_k^r)+d_k^r\|_P,
$$

$$
a_k^{\rm env}=\lambda\|e_k\|_P+\|d_k^r\|_P+D_k+\eta-\|e_{k+1}\|_P.
$$

Check input feasibility separately; nonnegative command slack alone does not establish $u_k\in\mathcal U$. A rejected candidate is not a transmitted-command violation when a passing stored fallback is sent. Nonnegative observed one-step slack alone does not demonstrate that both error envelopes hold; report their membership separately.

For an eligible interval starting at $s$, one convenient design-budget bound to plot is

$$
B_e(j)=\lambda^j\|e_s\|_P+(1-\lambda^j)s_{\rm cert}.
$$

Plot it only over the consecutive interval where its premises hold. Obtain a physical position bound using Eq. (23), including the estimation envelope; $h$ in the $P$ norm is not itself a position tolerance in meters.

Report sampled physical violations over whole episodes and active endpoints separately. Do not infer intersample safety, supervisor safety, or safe operation after eligibility loss. Failure at an extreme severity also does not locate a universally sharp capability boundary.

## 9. Metrics and figures to deliver

### 9.1 Main comparison table

Use rows for condition and method, with:

| Metric | Definition/reporting |
|---|---|
| Position RMSE | Per-trial physical error against original reference over a fixed window; mean and uncertainty |
| Peak position error | Per-trial maximum; median and IQR, with tail information if material |
| Recovery success | Successful/all attempted trials |
| Recovery time | Median/IQR among successes, accompanied by success rate |
| Prediction error | Common held-out estimated-state sequences with fixed training-derived scaling |
| Retrieval error | Cross-reference behavioral distance for latent neighbors |
| Recovery activity | Active transitions/all transitions; full interval-duration statistics separately |

Report paired full-minus-no-impact effects and intervals. Resample matched episode blocks and account for training seeds; do not treat time samples or overlapping windows as independent replicates. With only three seeds, show seed-level results as well as pooled uncertainty.

### 9.2 Certificate table and synchronized figure

The certificate table should contain \(\lambda,b_r,d_{\rm cert},\bar d,\eta_q,\eta\), estimation containment margin, all upper radii, selected \(R\), strict margin, physical projections, \(h,n_hT_s\), acceptance, coverage, activity, transmitted-command violations, and full-loop latency/deadline misses.

Use a prespecified representative combined-fault trial, such as nearest median RMSE among complete full-method trials. Preserve failures in aggregates and show a prespecified failure example if needed to explain a limiting case.

Use four aligned panels:

1. Physical position/yaw error, task tolerances, and applicable projected bounds.
2. \(\|e_k\|_P\), \(R,h,s_{\rm cert}\), eligible start, and predicted entry endpoint.
3. Actual transmitted-command and observed one-step slacks.
4. Duties/wrench, eligibility, fallback, supervisor, and deadline events.

If the supervisor changes the online reference, a bound plotted against the original task must also include the online-to-original reference offset. Do not compare an online-reference bound directly to original-task tracking error.

An optional severity map can show RMSE or success next to recovery-active fraction over actuator effectiveness and perception severity. Label calibrated-population cells and OOD stress cells separately. Gate inactivity must not be displayed as proof of physical unsafety or safety.

## 10. Engineering milestones and reproducibility

Before the final sweep, perform a few meaningful semantic checks:

- Verify frame changes and clipping behavior with rotated physical configurations.
- Confirm logged \(u_k\) equals the wrench of the duties actually transmitted.
- Force a solver deadline and a quantization-sensitive proposal to inspect stored-fallback behavior.
- Inject an onset near a context-domain exit and confirm its active source transition remains in envelope scoring.
- Reproduce one episode from its manifest and verify physical/estimated states and action timestamps align.

These checks establish interface correctness; they do not replace uniform mathematical verification or experimental results.

Save scenario manifests, parent/split identifiers, model and configuration hashes, raw per-step logs, episode metrics CSVs, fitting/calibration thresholds, certificate enclosures, and plotting/table scripts. Include full-loop runtime and compute platform; accelerated simulation wall time is not a real-time controller latency measurement.

A run log should preserve true and estimated states, original/online references, observations/masks, context, proposals, transmitted duties/wrench, allocator memory, model terms, gate reasons, fallbacks, solver status, and timing. Restrict hidden simulator fields to evaluator logs rather than controller-facing inputs.

## 11. Completion and interpretation

The strongest favorable result would combine improved full-versus-no-impact physical performance, improved behavioral retrieval or prediction, a useful accepted certificate, and meaningful eligible recovery intervals. No particular numerical improvement is predetermined.

If retrieval improves but control does not, report a representation benefit without claiming stronger fault recovery. If the certificate is rejected or rarely active, explain which bound limits it and narrow the practical claim. If no-check behavior matches full behavior, report that the tested allocator did not expose a material difference. Preserve these outcomes.

Simulation cannot establish that the recorded hardware checkpoint used the proposed training objective, that hardware obeys the simulated envelopes, or that existing actuator labels correspond to measured effectiveness. Close the remaining bridge with the focused implementation audit and matched spacecraft trials specified in the companion hardware guide.

For the paper, add a concise simulation subsection and combine repetitive existing hardware charts to create room. Keep the narrative centered on one question: whether behavioral context improves fault-tolerant tracking while the implemented recovery check provides a useful, explicitly bounded operating region.

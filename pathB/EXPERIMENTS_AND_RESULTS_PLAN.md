# Path B experiments and results plan

## Document purpose

This document defines a claim-aligned experimental program for the paper titled exactly:

**Multimodal Context Learning for Actuation and Perception Fault-Tolerant Model Predictive Control**

It is an execution and reporting specification, not a record of completed new experiments. It separates:

1. evidence already present in the archived hardware records and frozen simulation artifacts;
2. reconciliation work required before any archived simulation number can be treated as final;
3. prospective experiments that have not yet been run; and
4. optional extensions that are not required for the core Path B paper.

No result should be inserted into the manuscript merely because this plan predicts or desires it. Claim gates below control wording after the data are frozen; they are not guarantees of favorable results, statistical power, or journal acceptance.

## 1. Scope freeze

### 1.1 Central paper question

The paper tests whether a context inferred causally from estimator diagnostics, estimated motion, and transmitted commands lowers tracking RMSE within a spacecraft predictive controller under healthy operation and actuation, perception, and combined degradation.

The selected learned controller is **M2**, which uses a changing context and prediction losses only. Development selection already chose behavioral-loss weight lambda_I = 0. The behavioral-loss controller **M3** remains in the paper as a negative ablation and must not be described as the selected method.

### 1.2 Co-primary empirical questions

The prospective study answers two questions using condition-balanced post-onset position RMSE:

1. **Dynamic-context RMSE comparison:** M2 versus M1, where M1 is a separately trained constant-context predictor.
2. **Learned-MPC pipeline RMSE comparison:** M2 versus M5, where M5 is the nominal feedback/repair controller without MPC planning or a learned-residual action.

The second comparison is essential. Existing results favor M5. A new smooth, preview-bearing mission task is therefore required to determine whether the complete learned-MPC pipeline attains lower post-onset position RMSE in a task for which preview can matter. The task must be fixed for mission relevance and feasibility before the new test set is opened; it must not be tailored after viewing M2-versus-M5 test outcomes.

The two co-primary estimands are Delta21 on the retained step family and Delta25 on the smooth family. The complementary family contrasts remain secondary. M2-M5 changes both learned prediction and predictive optimization; it tests a pipeline-level RMSE difference against a simpler controller, not the isolated causal effect of planning. A planning-only claim would require another comparator preserving the learned prediction and changing only use of future preview.

### 1.3 Supporting questions

- Does the optional behavioral loss help or hurt: M3 versus M2?
- Does the estimator-diagnostic part of the multimodal history add value beyond motion and command history?
- Is the repeated post-allocation check operationally distinct: M3 versus M4?
- Does finite command repair add value when repair-on and repair-off use the same transmitted-command screen?
- What are the task-success, effort, action-source, and real decision-latency tradeoffs, especially when RMSE and the learned-MPC pipeline comparison disagree?

### 1.4 Explicitly out of scope

The core Path B study does not require:

- a nonempty certified invariant region;
- split-conformal safety calibration;
- physical-state, collision-free, intersample, or recursive-feasibility guarantees;
- a full certificate campaign;
- a new context-dependent metric;
- a new learned architecture;
- an image encoder;
- a new temporal/simple-encoder comparison unless architectural novelty is claimed;
- fault-specific controller tuning after the test set is opened.

The conditional transmitted-command analysis may remain in the paper, but the experiments evaluate control performance and implementation behavior, not a prospective safety certificate.

## 2. Evidence ledger at plan freeze

### 2.1 Existing evidence that may be reported only with its present scope

The current hardware table is archival, descriptive evidence from saved metric records:

- learned context versus deployment-time zero context at recorded actuator settings;
- learned context versus zero and hand-tuned context under half-camera occlusion;
- complete-record Vicon position RMSE, MAE, and peak error;
- small, unequal cell counts of three to five records.

These data do not yet establish which exact checkpoint, training loss, software commit, reference protocol, or controller/checking implementation produced every row. The fixed-context actuator row also reports selected stable trials. Until the hardware archive audit in Section 12 is complete, use the phrase **reported archival hardware result**, not **verified implementation result**.

The frozen simulation artifacts contain useful historical evidence:

- the development grid selected lambda_I = 0;
- M2 outperformed M1 in the archived step-family comparison, which evaluated only the M1 seed-0 checkpoint even though Stage 5 trained M1 seeds 0, 1, and 2;
- M3 was worse than M2 on post-onset RMSE in all four archived conditions;
- M5 was better than M2 in all four archived conditions;
- the historical M3-versus-M4 repeated-check effect was exactly zero;
- the archived JSON declares a provisional development task-success definition of 0.15 m position, 5 degrees yaw, and 2.1 s dwell; these values are not measured mission requirements and their discrete-time semantics remain to be reconciled before prospective testing;
- the older diagnostic recovery tolerance is approximately 0.662 m and is not the task-success threshold.

These simulation results are historical baselines, not prospective Path B tests.

### 2.2 Why the archived simulation campaign requires artifact-level reconciliation

The archived run identity reports:

- run id v4-architecture-repair;
- commit 81f52657c7d16d8377ac0812d13295410de377a7;
- a dirty working tree;
- manifest hash 07f277768a04859a.

The audit guide instead references commit 9e2af1607dfe5f90a76bf796b293436d71fab7ad. The frozen narrative is internally inconsistent about the hidden pulse-fault slot: Section 0.1 appears stale and says the mismatch remained unresolved, while the report header says v2 was superseded and Section 3.-1 says the unified-fault-slot correction was already applied, with a maximum reported shift of 0.027 m. This does **not** establish that the saved Stage 6 artifact used either contract. Map each saved artifact to the corrected or uncorrected execution contract from its source/config/log evidence; label it `unknown` when that mapping cannot be proved. Do not blanket-label v4 or every faulted cell as known-faulted because of the stale prose.

The narrative report also contains internal inconsistencies that must be resolved from raw artifacts rather than prose, including:

- text saying seed-crossed intervals include zero while the displayed M3-minus-M2 intervals are strictly positive;
- text calling a post-allocation acceptance check load-bearing while M3 and M4 are identical and the repeated check records zero rejections;
- changing use of the terms first-action screen, repeated decrease check, allocation-aware selection, and repair.

No prospective claim may pool the dirty campaign with new results. Historical tables remain clearly labeled as historical.

### 2.3 Evidence that does not yet exist

The following are prospective:

- a clean-commit prospective run under one verified unified fault-execution contract;
- five trained seeds for the required trained methods;
- a motion-command-only trained ablation;
- a clean repair-on versus repair-off comparison with identical screening semantics;
- a prespecified smooth preview mission task;
- 60 new matched scenarios per condition and family;
- balanced fresh hardware runs;
- real-host or onboard latency for the final frozen implementation;
- any full numerical certificate.

## 3. Provenance and dirty-run reconciliation

This stage is blocking. Do not launch the prospective test until every item passes.

### 3.1 Recover the exact historical source

1. Recover and archive the complete dirty-tree patch associated with commit 81f52657c7d16d8377ac0812d13295410de377a7.
2. Diff that snapshot against 9e2af1607dfe5f90a76bf796b293436d71fab7ad.
3. Map every frozen JSON artifact and checkpoint to:
   - source commit;
   - dirty patch hash;
   - configuration-manifest hash;
   - Python and dependency lock;
   - training-data manifest;
   - checkpoint SHA-256;
   - scenario-manifest SHA-256;
   - corrected, uncorrected, or unknown fault-slot execution contract, with the evidence supporting that classification.
4. If the dirty patch cannot be recovered exactly, retain the old outputs only as non-reproducible historical evidence and do not reuse their checkpoints in the prospective study.

### 3.2 Establish one clean execution contract

The clean frozen code must pass, at minimum:

- hidden fault severity, phase, and onset do not enter controller-visible history;
- data generation and policy execution consume the identical fault slot for the same command;
- trial allocation mutates neither allocator state nor fault phase;
- `commit` is called only for the selected packet and updates allocator memory only; it does not consume or advance the physical fault slot;
- plant `realize` owns the physical fault state and consumes/advances that slot exactly once for the selected transmitted packet, matching the corrected pinned public source;
- physical force rotates with true physical yaw, not estimated yaw;
- fallback acceptance is actually enforced;
- each transmitted command has exactly one mutually exclusive source;
- current and successor references are stored separately;
- task success is evaluated at the final intended goal;
- all command checks use the nominal-equivalent command corresponding to the packet actually selected for transmission.

Create a clean signed tag or immutable archive after these checks. Any later code change creates a new experiment version and a new untouched test manifest.

### 3.3 Recompute historical summaries

Before using the archived study for motivation:

- regenerate all tables directly from stage6_methods.json or lower-level logs;
- verify the signs and confidence intervals for M2-M1, M3-M2, M2-M5, and M3-M4;
- report unique scenario counts separately from checkpoint rollouts;
- remove duplicate pseudo-replicates of deterministic methods;
- reconcile first-action, repeated-check, admissibility, repair, fallback, and supervisor counters;
- preserve the finding that lambda_I = 0 was selected on development data.

This reanalysis does not turn the old test into the new test.

## 4. Exact method matrix

All methods use the same physical plant, estimator, reference, scenario draw, actuator model, command allocator, operational gate, supervisor, admissibility definition, and scoring code unless a row explicitly names the changed component.

| ID | Frozen name | Training/deployment definition | Training seeds in prospective study | Purpose |
|---|---|---|---:|---|
| M0 | nominal_recovery | No learned residual and no learned context. Same MPC proposal structure, nominal model, repair, allocator, command screen, gate, and supervisor as M2. | Seedless; one rollout per unique scenario | Isolates the learned predictor/context from the remaining controller |
| M1 | constant_context | Separately trained residual with one learned constant context, prediction losses only. It must not be produced by setting a dynamic encoder output to zero. | 5 | Fair static learned-model baseline |
| M2 | no_impact | Selected method: changing context, prediction losses only, lambda_I = 0 | 5 | Main learned method |
| M3 | behavior | Same architecture, data, initialization schedule, minibatch order, and prediction losses as M2, with the previously declared positive behavioral-loss weight | 5 | Behavioral-supervision ablation; not the selected method |
| M4 | repeatedcheck | Reuses each corresponding M3 checkpoint and differs only by disabling the repeated post-allocation decrease check. The earlier first screen, repair, admissibility test, fallback, gate, and supervisor remain identical. | 5 inherited M3 checkpoints | Tests whether the repeated check changes behavior |
| M5 | nominal_feedback_repair | No MPC optimization and no learned-residual action. Uses nominal reference feedforward, fixed feedback, the same finite repair, allocator, transmitted-command screen, gate, and supervisor. Verify empirically that its output is checkpoint-independent, then run it once per scenario. | Seedless | Simpler pipeline baseline; M2--M5 does not isolate planning |
| M-motion | motion_command_only | Same residual head, temporal architecture, prediction loss, training data, optimizer, and controller as M2, but encoder input removes the two innovation scalars and one validity channel. It retains state increments, previous transmitted command, and nominal residual. | 5 | Tests the incremental value of estimator-diagnostic channels |

### 4.1 Seed policy

The target is five independent trained seeds, numbered 0 through 4.

- Existing M1, M2, and M3 seeds 0, 1, and 2 may be retained only if checkpoint provenance passes Section 3. Stage 5 trained all three M1 seeds, although Stage 6 evaluated only M1 seed 0.
- Add M2 and M3 seeds 3 and 4.
- Add M1 seeds 3 and 4; do not mistake the Stage 6 evaluation subset for the Stage 5 training inventory.
- Train M-motion seeds 0 through 4.
- M4 reuses M3 checkpoints and is not retrained.
- M0 and M5 are deterministic controller baselines. Do not copy their one trajectory five times and call those copies seed replicates.

Five seeds are a design target for training-variability coverage, not a power guarantee. Freeze separate method-specific training RNG streams for M1 and M-motion versus M2; do not introduce a shared initialization/data-order coupling and then analyze it as independent. Reuse archived checkpoints only when their source/RNG provenance satisfies the chosen design. M3--M2 may use the separately declared common-random-number pairing, which must be verified before joint seed resampling.

### 4.2 Clean repair contrast

The historical M7 comparison is not an acceptable repair ablation because it changes the command on which an earlier screen is evaluated.

Create one new deployment-only variant, **R-off-clean**, from each M2 checkpoint:

- R-on is ordinary M2.
- R-off-clean disables finite proposal repair only.
- Both variants trial-allocate their respective proposed command.
- Both apply the same first and final acceptance rules to the resulting nominal-equivalent transmitted command.
- Both use the same allowance, command budget, gate, fallback, allocator state, solver result, and supervisor.
- Search failure is recorded as search failure, not proof that no passing reachable command exists.

The clean repair effect is M2 minus R-off-clean on identical scenarios. Do not rename the historical M7 result as this experiment.

## 5. What multimodal means in this paper

The title remains unchanged, but the manuscript and experiment must describe the implemented streams precisely.

### 5.1 Current feature audit

The current simulation history is an 18-feature vector over 11 causal tokens for L = 10:

- 2 estimator-innovation diagnostic scalars;
- 1 validity scalar;
- 6 estimated-state increments;
- 3 previous transmitted nominal-equivalent command components;
- 6 nominal prediction-residual components.

These features enter a shared linear projection. The current attention mask handles startup padding only; it does not implement per-modality masking of unavailable sensor channels. The current model is not an image encoder. Its streams are primarily estimator diagnostics, estimated motion, and commands.

The frozen MPC prediction horizon is N = 12, so an MPC preview contains N+1 reference/state indices. The symbol H = 5 denotes the training rollout depth and must not be used as the MPC preview length. Record both values separately in manifests and method descriptions.

The paper must not claim that raw images or independently tokenized sensor encoders were evaluated.

### 5.2 Scaling audit

The current pipeline uses a hardcoded FEATURE_SCALE even though a source comment describes training-computed scaling. The core Path B experiment should freeze and disclose the actual hardcoded scaling so that M1, M2, M3, M4, and M-motion remain comparable.

If the team changes to train-set-only normalization:

- treat it as a new pipeline version;
- recompute scaling using training data only;
- retrain every learned method;
- reselect only on development data;
- create another untouched test manifest;
- do not pool it with the hardcoded-scaling experiment.

### 5.3 Interpretation of M-motion

M-motion removes the explicit innovation and validity channels. Its remaining estimated-state increments and nominal residuals still reflect the vision-based estimator. Therefore it tests the incremental value of estimator-diagnostic channels; it is not a vision-free controller.

### 5.4 Optional architecture ablation

A temporal transformer versus simple encoder comparison is optional. Run it only if the paper claims that transformer attention or temporal architecture is itself novel or necessary. Otherwise describe the transformer as an implementation choice.

If run, use a parameter-matched pooled MLP or causal one-step encoder trained with the same M2 objective for five seeds on the same splits. This optional experiment adds 2,400 test rollouts and five training jobs.

## 6. Scenario families and population

### 6.1 Shared episode population

Both task families use:

- 60 s episodes with a 0.1 s control period and 600 command intervals;
- four primary conditions: healthy, actuator, perception, and combined;
- impairment onset sampled uniformly from 15 to 20 s for all scenario keys, including a pseudo-onset defining the healthy scoring window;
- the same versioned impairment, plant-mismatch, estimator-noise, allocator, and initial-state draw for every matched method;
- matched scenario keys so every method sees the same exogenous draw;
- new Path B test keys that were never used for training, development, historical testing, task design, or debugging.

Before generating development or test keys, export a machine-readable `scenario_population_v1.json` (or equivalent immutable manifest) directly from the frozen configuration and record its SHA-256 in every run. It must give the exact probability law, support, units, dependence/correlation, draw order, seed-to-draw mapping, and condition-specific overrides for every random variable. A prose statement such as "same frozen distribution" is insufficient. At minimum, reconcile and encode the following values already exposed by the frozen records:

- primary-study mass and inertia perturbation supports of plus or minus 10%; keep the separate plus or minus 15% stress setting out of the primary four-condition estimand unless explicitly prespecified as a secondary study, and copy the exact density and dependence structure from the frozen config;
- impairment onset distributed uniformly over [15, 20] s, including the exact endpoint and time-grid convention;
- the exact initial-state, actuator-fault, perception/noise, drag, and yaw-damping distributions copied from the frozen config, including numerical bounds that the current extracted report describes only as small and bounded;
- the allocator conversion recorded as `t_on = 4.829 F/25 - 0.07686 s`, with its exact units and operation order, clipped to at most 40 ms in a 100 ms slot (duty ceiling 0.40);
- the 12 ms minimum-pulse rule for commands above 0.001 N, the below-threshold drop rule, and the exact ordering of thresholding, minimum-pulse promotion, and clipping;
- the 1.2 N open-valve level and the exact actuator-fault counter law on T7/T8 (zero-based indices 6 and 7): `should_fire = (nxt * 0.70 - fired) >= 0.5`, with the counter initialization/update order copied from source. Here `fault_fraction = 0.70` is a retained firing-cycle fraction, so approximately 70% of otherwise eligible cycles fire and 30% are skipped; it is **not** a continuous 70% thrust-amplitude scale.

Link the manifest to the immutable clean config/source archive and store both hashes. If any exact distribution or operation order cannot be recovered, it is a blocking provenance gap: resolve it on development data and issue a new versioned population before opening the test, rather than silently guessing from the narrative report.

Each family has exactly 60 unique scenarios per condition: 240 unique scenario-condition units per family and 480 across two families.

### 6.2 Family A: retained step task

Retain the existing 60 s hardware-anchored step family:

- first waypoint (0.0, -2.0);
- final waypoint (1.0, -2.0);
- legacy waypoint transition when `abs(y - y_wp1) <= 0.15 m`; this is a one-coordinate switch rule, not Euclidean distance to the first waypoint and not the final task-success test;
- success evaluated only at the final intended waypoint and heading;
- a new prospective scenario manifest, distinct from the historical 60 scenarios per condition.

The retained step task provides continuity with the archive. Its instantaneous setpoint change is not used to support a recovery-certificate claim.

### 6.3 Family B: prespecified smooth preview mission

Use one mission-relevant inspection-to-docking preview, named **smooth_dock_v1**:

The coordinates below are a proposed engineering task design for Path B; they were not extracted from, or validated by, the archived hardware missions.

- episode starts at the same declared nominal start pose used by the step task;
- segment 1 follows a quintic minimum-jerk translation to a pre-dock pose offset 0.6 m in x and 0.6 m in y with a +30 degree yaw change over the first half of the selected maneuver duration;
- segment 2 follows a quintic minimum-jerk translation to a final pose offset 1.0 m in x and 0.0 m in y from the start, returning to the final declared docking yaw over the second half;
- position, yaw, velocity, angular rate, acceleration, and angular acceleration are continuous at the segment join;
- the remainder of the 60 s episode holds the docking pose;
- the complete successor reference and preview are committed before each action.

If workspace coordinates require a rigid translation or rotation, transform the entire path without changing its body-frame derivative profile. Do not change curvature, duration, or waypoints after opening the test set.

### 6.4 Feasibility calibration before test

The normalized path shape and a deterministic duration-selection rule are prespecified. Test candidate maneuver durations of 30, 40, and 50 s in ascending order using only the analytic feedforward/admissibility checks below. Select the shortest passing duration, then run the development rollouts. The smooth task is eligible for testing only after this development-only feasibility gate:

1. Analytically verify continuity and finite derivative bounds.
2. Verify nominal reference feedforward stays inside the frozen admissibility budget with at least the predeclared implementation margin at every sample.
3. Run 20 separate healthy development scenarios with M0.
4. Require no generator failure, no reference/heading-band inconsistency, a complete N+1 MPC reference sequence for the frozen N = 12 horizon, and at least 18 of 20 task completions under the frozen success definition.

The predeclared implementation margin is at least 20%: after expressing each relevant nominal command/admissibility facet as normalized utilization, its maximum must be no more than 0.80 throughout the path. If a 20-rollout gate fails, do not inspect any Path B test outcomes. Move to the next longer duration in the same 30/40/50 s ladder, retain the normalized path shape, re-version the task, rerun the development gate, and create a fresh untouched test manifest only after the task is frozen. If none of the three durations passes both the 20% analytic margin and rollout gate, abandon `smooth_dock_v1` or redesign and version a replacement using development data; do not relax the margin or open/reuse a test manifest. This gate establishes nominal feasibility, not that M2 will beat M5.

The M2-versus-M5 result on the new smooth family tests whether the complete learned-MPC pipeline attains lower post-onset RMSE than nominal feedback/repair. It does not isolate a causal effect of planning.

## 7. Execution priorities

### Priority 0: scope and provenance freeze

- Complete Sections 3 and 5.
- Freeze title, questions, methods, endpoints, task-success definition, task families, condition distributions, seed set, scenario counts, and statistical code.
- Confirm lambda_I = 0 was selected on development data without consulting either historical or prospective test performance.
- Version the analysis plan and store its hash in every prospective result artifact.

### Priority 1: historical log reanalysis

- Rebuild historical tables from raw JSON/logs.
- Reconcile dirty source and report contradictions.
- Produce a method/checkpoint/scenario count table distinguishing unique scenarios from rollouts.
- Produce a complete action-source table.
- Classify each saved result as corrected-contract, uncorrected-contract, or unknown from artifact evidence. Treat only unmapped/unknown results as provenance-provisional; do not infer the class from the stale Section 0.1 narrative alone.

No new plant experiment is required for this stage.

### Priority 2: instrumentation replay and smoke gate

Before the large test, run 48 development-only smoke episodes:

- 2 task families;
- 4 conditions;
- 2 deterministic development scenarios per family-condition;
- 3 controllers: M0, M2 seed 0, and M5.

These 2 x 4 x 2 x 3 = 48 episodes verify logging, N+1 MPC references for N = 12, action taxonomy, fault-slot execution, fallback storage, non-mutating trials, and timing. They are never included in final effect estimates.

Before committing 2,400 prospective M4 rollouts, apply an optional claim-scope stop gate on development scenarios: use the same 16 scenario units above, all five M3 checkpoints, and paired M3/M4 deployments, for 16 x 5 x 2 = **160 development-only episodes**. If the selected packets, action sources, and trajectories are bitwise identical for every pair and the enabled M3 repeated-check rejection counter remains zero, omit M4 from the large prospective matrix and remove the M3-M4 performance-effect claim. Report only the semantic/replay finding. If any pair differs, or if the paper retains a repeated-check effect claim, keep the full M4 prospective matrix.

### Priority 3: clean repair contrast

- Implement R-off-clean as defined in Section 4.2.
- Pass the same semantic and replay gates as M2.
- Confirm only the repair switch differs.
- Include R-off-clean in every new prospective scenario so the repair comparison is paired.

### Priority 4: balanced seeds and modality audit

- Complete the five-seed target.
- Train M-motion without altering other hyperparameters.
- Freeze all checkpoints and hashes before opening the new test.
- Run the claim-aligned method matrix on both families and all four conditions; include full M4 only under the rule in Priority 2.

### Priority 5: limited hardware block

The fresh hardware block in Section 12 is recommended, not authorized by this document. Do not state or imply that it has been completed until raw logs and manifests exist.

## 8. Required logger and result schema

Every prospective episode must be sufficient to reconstruct every reported endpoint and command decision without rerunning the controller.

### 8.1 Episode-level provenance

- experiment and analysis-plan version;
- clean Git commit and repository state;
- config and scenario-manifest hashes;
- task-family and task-version identifiers;
- condition and scenario key;
- scenario, model-training, and analysis seeds;
- method ID and checkpoint SHA-256;
- dataset split;
- impairment parameters and onset;
- plant, estimator, allocator, controller, and solver versions;
- host identifier, operating system, CPU, and timing-clock source.

### 8.2 Per-step state, history, and reference

- control index and acquisition/transmission timestamps;
- physical state in simulation or aligned Vicon state on hardware;
- current and successor estimates;
- current and successor task references;
- full N+1 reference sequence used by the MPC, from the current through terminal prediction index, for frozen horizon N = 12;
- all N+1 predicted states used by the proposal;
- estimator innovations, validity scalar, state increments, previous transmitted command, and nominal residual;
- raw feature vector after ordering and scaling;
- startup-padding mask;
- inferred context and residual correction.

The logger must store both successor estimate and successor reference so post-hoc discrepancy calculations do not rely on reconstructed or shifted arrays.

Store N = 12 as MPC-horizon metadata and H = 5 separately as learned-model training-rollout-depth metadata. Never label an H+1 array as the controller preview.

### 8.3 Proposal, repair, allocation, and screen

- nominal feedforward and feedback proposal;
- complete proposed MPC command sequence;
- solver status, iteration/pass number, slacks, and objective components;
- raw first command;
- finite repair candidates in generation order;
- repair type and selected repair candidate;
- repair-seed origin, with the frozen values `raw_mpc`, `projected_mpc`, `p_error`, `feedback`, and `not_applicable`;
- separate Boolean fields for whether continuous projection and allocation compensation were applied;
- command role, distinguishing `mpc_primary`, `mpc_replacement`, `m5_feedback`, `stored_fallback`, and `supervisor`;
- allocator memory before the trial;
- proposed duty packet and proposed allocator-memory update;
- nominal-equivalent command after trial allocation;
- command admissibility verdict;
- first-screen and repeated-check left side, right side, allowance, and slack;
- checked fallback request, packet, nominal-equivalent command, screen values, and verdict;
- selected packet and committed allocator-memory update;
- physical fault realization in plant-only logs, never controller-visible.

### 8.4 Mutually exclusive action-source taxonomy

Exactly one transmitted-action source must be logged per step:

1. mpc_primary;
2. mpc_replacement;
3. m5_feedback;
4. fallback_first_screen;
5. fallback_repeated_check;
6. fallback_command_admissibility;
7. fallback_solver;
8. fallback_deadline;
9. supervisor_operating_radius;
10. supervisor_no_passing_fallback;
11. supervisor_preaction_ineligible_other;
12. supervisor_posteligibility_failure.

The source shares must sum to one. Candidate rejection reason and transmitted-action source are separate fields. The orthogonal seed-origin and projection/compensation fields distinguish an unchanged MPC command from a projected command, an allocation-compensated command, and replacement by the clipped P-error or feedback seed. In particular, a feedback seed selected inside the MPC repair search has role `mpc_replacement`, whereas the direct feedback controller M5 has role `m5_feedback`.

### 8.5 Timing and effort

Log:

- history/encoding time;
- residual prediction time;
- each MPC pass and total solve time;
- repair generation time;
- each allocation trial;
- each command screen;
- complete acquire-to-transmit decision time;
- deadline and overrun;
- host load metadata;
- commanded force/moment magnitude;
- command-rate norm;
- duty on-time, pulse count, saturation fraction, and nominal impulse/effort proxy.

Simulation timing is labeled host timing. Hardware timing must be measured on the real deployed host. Neither is called a hard real-time guarantee unless the runtime actually enforces one.

## 9. Endpoints and statistical estimands

### 9.1 Analysis population

Use all 60 unique scenarios per condition and family. Include:

- supervisor intervals;
- solver failures;
- command-search failures;
- gate inactivity;
- deadline misses;
- runs that never meet the task;
- complete post-onset windows through the declared episode end.

Do not discard failed, censored, inactive, or inconvenient trials. A corrupt file may be excluded only under a rule frozen before test; every exclusion remains in an audit table with its reason.

### 9.2 Primary continuous endpoint

For each rollout, compute post-onset physical position RMSE from the common onset or pseudo-onset through the episode end.

This changes the healthy-window estimand relative to the existing archive: the archived healthy endpoint used the complete episode, whereas the prospective matched design uses the frozen pseudo-onset through episode end. Label both windows explicitly, do not pool them, and do not present their values as the same endpoint. If raw historical trajectories permit, a separately labeled historical pseudo-onset reanalysis may be shown for context, but it remains historical.

For method m, family f, condition c, and scenario s, first average over that method's five independently trained checkpoints:

- mean_RMSE(m,f,c,s) = one fifth of the sum over that method's five training seeds;
- d21(f,c,s) = mean_RMSE(M2,f,c,s) - mean_RMSE(M1,f,c,s);
- d25(f,c,s) = mean_RMSE(M2,f,c,s) - RMSE(M5,f,c,s).

Thus scenarios are paired, but M1 and M2 training seeds are not falsely paired merely because they share numerical seed labels. Negative values favor M2.

The condition-balanced family estimand gives each of the four conditions equal weight and averages the scenario-paired differences within condition:

Delta21(f) = one fourth of the sum over conditions of the mean over the 60 scenario-specific d21 values;

Delta25(f) = one fourth of the sum over conditions of the mean over the 60 scenario-specific d25 values.

Report family-specific estimands. The smooth-family Delta25 is the key learned-MPC pipeline RMSE estimand. Do not hide the retained step-family result inside an overall average or call Delta25 a planning-only effect.

### 9.3 Training-seed and scenario uncertainty

Use a prespecified crossed scenario-paired bootstrap:

- resample the 60 scenario IDs within each condition and keep all method outcomes for a resampled scenario paired;
- independently resample the five M1, M2, and M-motion training seeds with replacement;
- reuse the same resampled M2 seed vector across every contrast involving M2 in that bootstrap replicate;
- for M2--M5, pair each resampled M2 outcome to the same single seedless M5 outcome for that scenario;
- for M2--R-off-clean, resample the checkpoint-matched deployment pair jointly because R-off-clean reuses the corresponding M2 checkpoint;
- resample M3 and M2 seed pairs jointly only if provenance verifies that each pair used the declared matched initialization and data/minibatch-order policy; otherwise resample their seeds independently and disclose that the behavioral-loss contrast is not common-random-number paired;
- resample each M3--M4 checkpoint pair jointly because M4 reuses its corresponding M3 checkpoint;
- give each condition equal weight;
- use analysis seed **260921** and 10,000 resamples;
- report point estimate and percentile 95% interval.

Point estimates use the within-method five-seed means defined above, not differences between arbitrarily paired M1 and M2 seed labels. M5 is seedless; do not pretend its reuse across M2 seeds creates independent M5 realizations. Apply the same independent-seed rule to M2--M-motion.

Also report all five seed-level means. Five seeds do not guarantee a narrow interval.

Report nominal 95% intervals for all effects. For the two co-primary claim gates, additionally use central 97.5% bootstrap intervals (1.25th and 98.75th percentiles), providing a Bonferroni multiplicity allowance for the two planned comparisons at a nominal familywise 5% level. Bootstrap coverage is approximate with five training seeds. Secondary condition/family and modality intervals are descriptive, not additional unadjusted confirmatory discoveries.

### 9.4 Task success

The 0.15 m, 5 degree, and 2.1 s values came from a development JSON and are provisional engineering thresholds, not measured mission requirements. Before generating the prospective test manifest, either freeze them with an engineering/mission rationale or change them using development evidence only, then version and freeze the scorer. They may not change after any prospective outcome is viewed.

The preferred Path B freeze preserves the JSON meaning as an elapsed-time requirement. Task success then requires, at the final intended goal:

- position error no greater than 0.15 m;
- absolute yaw error no greater than 5 degrees;
- both conditions satisfied at every scoring observation in a consecutive window spanning at least 2.1 elapsed seconds according to logged timestamps;
- success completed before the 60 s episode deadline.

At exactly 10 Hz, 21 consecutive observations span 20 elapsed intervals, or 2.0 s; they do not establish 2.1 elapsed seconds. The timestamp-based 2.1 s convention requires 22 consecutive observations when samples are exactly 0.1 s apart. If the team instead retains the existing 21-observation implementation, rename the endpoint as "21 consecutive observations (2.0 s elapsed at 10 Hz)," justify and freeze that development choice, and update the JSON before test. Never report both conventions as 2.1 s.

This is a sampled task-completion endpoint, not an intersample guarantee.

Report the scenario-paired success-rate difference and condition-balanced rate for M2-M1 and M2-M5 using the same independent training-seed resampling and shared scenario resampling specified above. Wilson intervals may additionally describe a seedless method or one fixed checkpoint over independent unique scenarios, but not a paired difference or pooled correlated rollouts across learned seeds.

The historical approximately 0.662 m recovery tolerance is a separate diagnostic endpoint. Label it **diagnostic recovery**, never task success, and never merge its counts with the 0.15 m/5 degree/2.1 s outcome.

### 9.5 Failure and censoring

Assign exactly one mutually exclusive terminal progress category:

- never entered position tolerance;
- entered position tolerance but never yaw tolerance simultaneously;
- entered both tolerances but did not complete the required dwell;
- task success;
- corrupted/unscorable under the frozen exclusion rule.

Record orthogonal failure/event flags separately, allowing multiple true flags in one run: departure after entering tolerance, supervisor intervention/ineligibility, no passing fallback, solver failure, repair/search failure, deadline overrun, numerical/logging anomaly, and episode-deadline censoring. Do not force these causal/operational events into the progress category or use an undocumented precedence rule.

Report complete counts by method, condition, and family.

### 9.6 Secondary outcomes

- yaw RMSE and peak yaw error;
- position MAE and peak position error;
- time to final-goal task success;
- old diagnostic recovery rate/time;
- command effort, rate, pulse count, saturation, and duty;
- candidate, repair, fallback, and supervisor shares;
- first-screen and repeated-check activity;
- solver, repair, allocation, and total latency;
- deadline-miss rate;
- prediction error, reported separately from physical tracking.

No secondary endpoint is substituted post hoc for a failed primary comparison.

## 10. Claim acceptance gates

These gates determine manuscript wording only.

### 10.1 Dynamic-context RMSE claim

Claim only that changing context attains lower condition-balanced post-onset position RMSE than the trained static-context baseline if:

- prospective step-family Delta21 is below zero with its 97.5% co-primary interval below zero;
- all conditions and failures are shown.

Otherwise report the RMSE comparison as unresolved or adverse. Task success, effort, failures, and timing remain descriptively reported; they are not discretionary gates that can broaden or rescue the endpoint-specific RMSE claim. A successful RMSE gate does not authorize an overall task-utility claim.

### 10.2 Learned-MPC pipeline RMSE claim

Claim only that the complete learned-MPC pipeline attains lower condition-balanced post-onset position RMSE than nominal feedback/repair if, on smooth_dock_v1:

- Delta25 is below zero with its 97.5% co-primary interval below zero.

If M5 remains superior or indistinguishable, say so plainly. Task success, effort, constraints, failures, and timing remain descriptive secondary outcomes and cannot be invoked post hoc to reverse this RMSE gate. Even a successful M2--M5 RMSE gate establishes neither overall task utility nor a planning-only advantage, because M2--M5 changes both learned prediction and predictive optimization.

### 10.3 Multimodal-stream claim

Claim that estimator-diagnostic channels add value only if M2 improves on M-motion prospectively. Because M-motion still contains vision-influenced estimated states and residuals, the claim is limited to explicit diagnostic channels, not all perception information.

If unresolved, retain the title as requested but describe multimodal input composition precisely and avoid a modality-fusion benefit claim.

### 10.4 Behavioral-loss claim

The current selected value is lambda_I = 0. Report M3-M2 even if adverse. Do not revive behavioral supervision as a benefit without a new, independently justified training design and a new untouched test.

### 10.5 Repeated-check and repair claims

- M3-M4 supports only the incremental value of the repeated check.
- M2 versus R-off-clean supports only finite repair.
- Do not use historical M7 as the clean repair effect.
- If an effect is zero, describe the component as redundant under the preceding screen rather than beneficial.

### 10.6 Certificate and safety wording

No outcome in this plan authorizes a verified invariant-region, calibrated safety-probability, collision-free, continuous-time safety, or guaranteed recovery claim. The transmitted-command proposition remains conditional on its explicit discrepancy assumptions.

Passing these gates does not imply RA-L acceptance.

## 11. Exact prospective run budget

### 11.1 Training jobs

Assuming archived checkpoint provenance passes:

- M1: retain Stage 5 seeds 0-2 and add seeds 3-4 = 2 new training jobs;
- M2: add seeds 3-4 = 2 new training jobs;
- M3: add seeds 3-4 = 2 new training jobs;
- M-motion: train seeds 0-4 = 5 new training jobs.

Minimum new training jobs under that provenance assumption: **11**.

If archived checkpoints fail provenance, retrain M1, M2, M3, and M-motion for all five seeds: **20** training jobs.

M4 and R-off-clean reuse frozen checkpoints. M0 and M5 require no training.

### 11.2 Development-only episodes

- Smooth-task feasibility gate: 20 M0 episodes per attempted maneuver duration, hence **20--60** episodes across the prespecified 30/40/50 s ladder.
- Instrumentation smoke gate: 48 episodes.

Baseline development-only controller episodes: **68--108**.

If using the complete M3/M4 semantic stop gate, add 160 paired development episodes, for **228--268** development episodes total.

These are not included in test estimates.

### 11.3 Prospective test matrix

There are:

- 2 task families;
- 4 conditions;
- 60 unique scenarios per family-condition.

Unique scenario-condition units:

2 x 4 x 60 = **480**.

The recommended full Path B target retains a prospective repeated-check comparison. Seeded test methods are M1, M2, M3, M4, and M-motion:

5 methods x 5 seeds x 480 = **12,000** controller episodes.

Seedless methods are M0 and M5:

2 methods x 480 = **960** controller episodes.

Core method-matrix total:

12,000 + 960 = **12,960** controller episodes.

R-off-clean adds:

5 M2 checkpoints x 480 = **2,400** controller episodes.

Recommended full Path B prospective test target:

12,960 + 2,400 = **15,360** controller episodes.

Together with development, if the M3/M4 stop gate is not invoked:

15,360 + 68--108 = **15,428--15,468** new controller episodes, excluding training-data generation.

This 15,360-episode target is a comprehensive recommended Path B design, not an absolute or universal minimum for RA-L. Under the prespecified semantic stop rule, a claim-aligned design may omit the full M4 matrix and remove the repeated-check performance claim:

- M1, M2, M3, and M-motion: 4 methods x 5 seeds x 480 = 9,600;
- M0 and M5: 2 methods x 480 = 960;
- R-off-clean: 5 checkpoints x 480 = 2,400;
- reduced prospective test total: **12,960** episodes.

With 68--108 baseline development episodes and the 160-episode M3/M4 stop gate, that reduced route comprises **13,188--13,228** new controller episodes excluding training-data generation. It supports no population-level M3-M4 effect estimate; it supports only the reported development semantic/replay result. If any gate pair differs, the 160 gate episodes have already been spent: restore the 2,400-rollout M4 test matrix, giving **15,588--15,628** total new controller episodes including development.

The existing dirty campaign and its 5,280 reported rollouts remain historical and are not added to the prospective sample size.

Optional temporal/simple-encoder ablation:

5 seeds x 480 = **2,400** additional test episodes plus five training jobs.

### 11.4 Deterministic count reporting

Every table must show:

- unique scenario count;
- trained checkpoint count;
- controller rollout count;
- whether a method is seedless;
- whether confidence intervals cross training seeds, scenarios, or both.

Never report 300 replicated M5 outcomes when they are five copies of the same 60 deterministic scenario outcomes.

## 12. Hardware program

### 12.1 Mandatory archival identification

Before retaining the current hardware table, create:

- hardware_manifest.csv;
- hardware_exclusions.csv;
- hardware_checkpoint_manifest.csv.

For every record, store:

- immutable file checksum;
- run identifier, date, and operator;
- controller source/version if recoverable;
- checkpoint hash and training-loss configuration;
- feature order, scaling, history length, and context dimension;
- solver, horizon, cost, command repair, allocator, and checking behavior;
- reference task and scoring window;
- impairment definition, onset, and physical setting;
- estimator and Vicon timing/alignment;
- inclusion/exclusion rule and reason;
- whether the run was among the selected stable trials.

Recompute the archival table from the manifest. If an implementation field is unknown, label it unknown rather than inferring it from later simulation code.

### 12.2 Recommended fresh targeted block

This plan recommends, but does not authorize, one balanced fresh hardware block:

- methods: M1, M2, and M5;
- task: smooth_dock_v1;
- conditions: healthy, actuator, perception, combined;
- 10 matched blocks per condition;
- each block runs all three methods in randomized order.

Exact target:

3 methods x 4 conditions x 10 repetitions = **120 hardware trials**.

Use the same frozen checkpoint set policy across conditions. For M1 and M2, each of the five trained seeds appears exactly twice per condition; freeze the cross-method seed pairing and method-order randomization schedule before runs. Do not choose the best checkpoint after hardware observation. Match initial condition, reference, impairment setting, and available environmental controls within each three-method block.

The target of ten blocks, giving two repetitions per learned seed in each condition, is a design choice, not a power guarantee.

### 12.3 Hardware endpoints

Report:

- complete-record and post-onset Vicon position RMSE;
- final-goal task success under the frozen thresholds and dwell semantics from Section 9.4;
- yaw error;
- effort, duty on-time, pulse count, saturation, and command variation;
- action-source shares;
- real deployed-host encoding, solve, repair, allocation, check, and total latency;
- deadline misses and failures.

Do not export simulated confidence, effect size, or certificate language to hardware.

## 13. Required tables, figures, and deliverables

### 13.1 Main-paper tables

**Table 1: Method and implementation matrix**

Rows M0, M1, M2, M3, M4, M5, M-motion, and R-off-clean. Columns:

- dynamic context;
- learned residual;
- behavioral loss;
- MPC planning;
- finite repair;
- first screen;
- repeated check;
- fallback/gate;
- trained seeds.

**Table 2: Prospective simulation outcomes**

For each family and condition, report M0, M1, M2, M3, M5, and M-motion:

- unique scenarios;
- trained seeds;
- post-onset RMSE;
- task success;
- effort;
- candidate/repair/fallback/supervisor shares.

M4 and R-off-clean may appear in a focused ablation panel if space is limited.

**Table 3: Scenario-paired effects and claim gates**

- family-specific Delta21 and Delta25;
- per-condition paired differences;
- 95% crossed intervals;
- M3-M2;
- M3-M4;
- M2-M-motion;
- M2-R-off-clean;
- task-success differences;
- gate result stated as supported, unresolved, or adverse.

**Table 4: Hardware provenance and results**

- archival rows with implementation status;
- fresh M1/M2/M5 block if executed;
- exact run counts and exclusions;
- no mixing of archival and fresh means.

### 13.2 Main-paper figures

1. **Actual implementation diagram:** feature composition, temporal encoder, frozen residual in MPC, finite repair, allocation, transmitted-command screen, fallback, and supervisor. Remove obsolete cost/tightening heads.
2. **Paired-effect forest plot:** M2-M1 and M2-M5 by family and condition, with condition-balanced summaries.
3. **Smooth mission example:** reference and physical paths plus position/yaw error, action source, effort, and key command-screen quantities for matched M2 and M5 scenarios.
4. **Multimodal and negative ablations:** M2-M-motion and M3-M2, showing all five seed means.
5. **Hardware paired plot:** M1/M2/M5 fresh blocks if executed; otherwise retain a clearly archival descriptive plot.

The eight-page paper will likely fit Figures 1-4 and Tables 1-3; the complete hardware/provenance and failure tables may be supplied as data artifacts, not as supplementary manuscript text used to evade the page limit.

### 13.3 Reproducibility deliverables

- clean source tag/archive and dependency lock;
- recovered historical dirty patch or an explicit statement that it is unavailable;
- versioned configuration and scenario manifests;
- task generator and smooth-task feasibility record;
- training/dev/test split manifests;
- checkpoint hashes and training curves;
- raw per-episode and per-step logs;
- hardware manifests and exclusions;
- long-form outcome file with one row per rollout;
- statistical-analysis script and fixed bootstrap seed;
- machine-readable table outputs;
- vector PDF figures;
- README with exact training, replay, test, and analysis commands;
- claim-gate report generated from frozen outputs.

## 14. Core versus optional completion

### Core Path B completion

- clean provenance and unified fault-execution contract;
- historical log reconciliation;
- exact method definitions M0-M5;
- five-seed M1/M2/M3;
- either a five-seed full M4 test or the prespecified semantic stop gate plus removal of the repeated-check performance claim;
- five-seed M-motion;
- both task families;
- 60 new matched scenarios per condition and family;
- clean R-off repair contrast;
- complete endpoint, failure, effort, and action-source reporting;
- hardware archive identification;
- no unsupported certificate or safety claim.

### Strongly recommended

- 120-trial fresh hardware M1/M2/M5 block;
- real-host timing;
- matched hardware task-success and effort reporting.

### Optional

- temporal transformer versus simple encoder;
- additional fault severities;
- OOD reference families;
- full numerical certificate and conformal calibration.

Optional work must not delay reporting adverse or null core-study results.

## 15. Freeze checklist before opening the new test

- [ ] Historical dirty patch recovered or declared unavailable.
- [ ] Clean commit/tag and dependency lock archived.
- [ ] Unified fault-slot execution passes semantic tests.
- [ ] Feature order, mask semantics, and FEATURE_SCALE documented.
- [ ] State order and wrench frame reconciled everywhere.
- [ ] Exact M0-M5, M-motion, and R-off definitions frozen.
- [ ] Training seeds 0-4 and checkpoint hashes frozen.
- [ ] Independent-versus-joint training-seed resampling rules and shared M2 bootstrap draws frozen in the analysis script.
- [ ] lambda_I = 0 development selection confirmed.
- [ ] Step and smooth task versions frozen.
- [ ] Smooth-task development feasibility gate passed.
- [ ] Exact machine-readable scenario population/distribution manifest and its SHA-256 frozen.
- [ ] Four condition distributions and onset rules frozen.
- [ ] New 60-scenario manifests generated but not opened.
- [ ] Provisional task thresholds justified/frozen and 2.1 s versus 21-observation semantics reconciled.
- [ ] Terminal progress categories and independent failure flags frozen.
- [ ] Repair-seed origin, projection/compensation flags, and transmitted command roles pass logger replay and the 48-episode smoke gate.
- [ ] Statistical script and bootstrap seed 260921 frozen.
- [ ] Hardware archival manifest completed.
- [ ] Claim gates accepted as wording rules, not desired outcomes.

Only after all boxes are checked should the prospective Path B test be executed.

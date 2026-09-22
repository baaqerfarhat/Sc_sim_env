# RA-L Path B revision — 2026-09-21

Title retained exactly:

**Multimodal Context Learning for Actuation and Perception Fault-Tolerant Model Predictive Control**

## Status

This is a revised, compilable manuscript based on the latest supplied Overleaf ZIP and the current archived results. It is not a report of newly executed experiments and is not yet a submission-ready claim of a completed prospective Path B study.

The original ZIP, prior projects, and revision instructions were not modified. All authored changes are in this new project.

Start with:

1. `main.pdf` — updated paper.
2. `EXPERIMENTS_AND_RESULTS_PLAN.md` — exact prospective method matrix, tasks, run counts, logging, scoring, statistics, claim gates, and priorities.
3. `main.tex`, `experiments.tex`, `architecture.tex`, and `refs.bib` — editable Overleaf source.

## What changed

| Component | Revision |
|---|---|
| Title and authors | Preserved from the latest supplied manuscript |
| Main learned method | Prediction-trained changing context (M2); the development-selected behavioral weight is zero |
| Behavioral supervision | Retained as an adverse M3-versus-M2 ablation, not presented as a demonstrated benefit |
| Learning inputs | Explicit 18-feature, 11-token causal history; no claim of an evaluated image encoder |
| MPC | Actual frozen residual, grouped reweighted quadratic passes, proposal box, slack penalties, and solver behavior |
| Command execution | Requested, trial-allocated, nominal-equivalent transmitted, and physical commands distinguished |
| Runtime mechanism | Finite command repair, stored checked fallback, operational eligibility, and supervisor described without exact-search or deadline guarantees |
| Theory | One conditional transmitted-command tracking bound; no unestablished operational safety/recovery certificate |
| Hardware | Earlier descriptive records retained with unequal sample counts and selected-stable-run caveat; not identified with later simulation checkpoints |
| Simulation | M2-versus-M0/M1 improvements, adverse M3 loss, stronger M5 feedback baseline, null M3/M4 contrast, and M7 confounding all reported |
| Endpoints | Historical whole-episode healthy versus post-onset faulted RMSE distinguished; strict task completion separated from the 0.662 m diagnostic |
| Figures | New code-native architecture diagram; hardware comparison reproduced from archived aggregate values with embedded scalable fonts |
| References | BibTeX entries are in `refs.bib`, not handwritten bibliography entries in the manuscript |

The M2-versus-M5 contrast measures the application-level value of the complete learned-MPC pipeline over a simpler nominal feedback/repair alternative. Because both learning and predictive optimization differ, it does not isolate the causal effect of planning alone.

## Exact input provenance

### Authoritative manuscript

Input: `../Multimodal_Context_Learning_for_Actuation_and_Perception_Fault_Tolerant_Model_Predictive_Control.zip`

SHA-256:

`55cce07f2a0b09a047ed3f85f326ef5ab1b7894e31d47b4752f2e50ac6e088db`

The source in this ZIP, not its stale bundled PDF and not the earlier `_3rd` folder, was used as the authority.

### Revision instructions

Input: `../RAL_Minimal_Theory_Revision_Current_Results.md`

SHA-256:

`ede19d4f2bca8b78e70eab83905c6099c3bbf86a924d58233820165edc5c2e81`

### Public simulator snapshot

Inspected snapshot:

`9e2af1607dfe5f90a76bf796b293436d71fab7ad`

[Pinned source and results](https://github.com/baaqerfarhat/Sc_sim_env/tree/9e2af1607dfe5f90a76bf796b293436d71fab7ad)

[Pinned Stage-6 artifact](https://github.com/baaqerfarhat/Sc_sim_env/blob/9e2af1607dfe5f90a76bf796b293436d71fab7ad/results/stage6_methods.json)

[Pinned training artifact](https://github.com/baaqerfarhat/Sc_sim_env/blob/9e2af1607dfe5f90a76bf796b293436d71fab7ad/results/stage5_training.json)

The archived run identity reports:

- run: `v4-architecture-repair`;
- base commit: `81f52657c7d16d8377ac0812d13295410de377a7`;
- dirty working tree: `true`;
- manifest hash: `07f277768a04859a`.

Stage-6 JSON SHA-256:

`2f28c0bb67eeff10b9ffa2c0bf96e63e8b9155cf67757f8455e9b76c217663d5`

The raw Stage-6 file is not copied into this small paper project. `evidence_summary.json` records the source hash, selected effects, task outcomes, deduplication, and consistency checks. `build_evidence.py` regenerates the summary from the raw artifact; it does not run the simulator.

### Important provenance distinction

The public plant source separates software allocator commit from physical fault realization. The narrative report nevertheless retains a stale subsection asserting a fault-slot mismatch, while later text reports that correction as already applied. This inconsistency is not proof of a defect in the saved v4 results. Exact dirty-source-to-artifact mapping must be recovered or explicitly left unknown. This project does not claim exact reproduction of the historical campaign from the public commit alone.

The configured actuator fraction `0.70` is a retained firing-cycle fraction on T7/T8: approximately 70% firing opportunities retained and 30% skipped, not 70% skipped and not continuous 70% thrust amplitude. Hidden physical fault realization is not an encoder input.

## Build and verification

Set `main.tex` as the Overleaf main document and use pdfLaTeX with BibTeX. The class and figure are included. The bibliography style `IEEEtran.bst` is supplied by standard TeX Live/Overleaf.

Local build:

```text
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Alternative:

```text
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Regenerate the compact evidence record:

```text
python build_evidence.py PATH/TO/results__stage6_methods.json
```

In the original workspace, the inspected raw artifact is at:

```text
../../tmp/ral_review_2026_09_21/results__stage6_methods.json
```

The script requires adjacent Stage-5 training metadata and reads optional run-identity metadata. It accepts either the original filenames or the local `results__`-prefixed names; explicit paths may also be supplied using `--training` and `--identity`. Verify the expected raw SHA-256 before substituting a downloaded file.

Regenerate the hardware figure:

```text
pdflatex -interaction=nonstopmode -halt-on-error fig_cross_fault.tex
```

The hardware plot source uses only the manuscript's reported means, standard deviations, and record counts. It does not fabricate raw trials, paired confidence intervals, or new measurements.

Final layout checks and source checks are recorded in `VALIDATION.md`.

## What remains before submission

The experiment plan contains the full specification. The immediate sequence is:

1. Recover/reconcile source, configuration, checkpoint, hardware-record, and fault-execution provenance.
2. Freeze endpoint semantics and instrument command provenance, effort, timing, and failure reporting.
3. Complete the balanced constant-context, changing-context, feedback, behavioral-loss, modality, and clean-repair comparisons on untouched scenario manifests.
4. Evaluate a development-frozen smooth preview task as well as the retained step task, retaining adverse results.
5. Reconcile the hardware archive; a fresh balanced M1/M2/M5 hardware block is recommended but has not been authorized or run.
6. Replace or extend the historical tables with actual prospective outputs, then update claim wording using the prespecified gates.

The full recommended simulation matrix is 15,360 test rollouts, or 12,960 with the prespecified repeated-check redundancy stop rule. Training-job counts depend on checkpoint provenance. These are proposed study targets, not journal-mandated minima or power guarantees. No acceptance outcome is promised.

Before final submission, also confirm the journal's current template, anonymity, page-limit, data-release, and reference-format requirements. The existing class/author format was retained for this working revision.

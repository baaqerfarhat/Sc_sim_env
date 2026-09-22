# Validation record — 2026-09-21

## Manuscript build and layout

- Main document: `main.tex`.
- Local toolchain: TeX Live 2024, pdfLaTeX, BibTeX, latexmk.
- Final compiled length: **7 US-letter pages**, including references.
- Final log: no LaTeX errors, unresolved citations/references, or overfull boxes.
- All seven final pages were rendered with Poppler and visually inspected.
- Equations, command-selection algorithm, both tables, both figures, and bibliography checked for clipping and overlap.
- All fonts in `main.pdf` are embedded Type 1 fonts; no Type 3 fonts remain.
- Bibliography entries live in `refs.bib`. The generated `.bbl` is a build product, not an inline bibliography in `main.tex`.

Final `main.pdf` SHA-256:

`f5b970b6719006a0e80012c05e7f2485df8dc041c249d4c86d25755e6e770b2f`

The render audit images are kept outside the deliverable project in the original workspace's `tmp/pdfs/ral_pathb_2026_09_21/checked-*.png`.

## Evidence checks executed

`build_evidence.py` completed successfully against the frozen Stage-5 and Stage-6 artifacts. Assertions verified:

- four conditions, 60 scenario identities per condition, and 5,280 archived controller rollouts;
- M1/M2/M3 each trained at seeds 0, 1, 2;
- only M1 seed 0 evaluated in Stage 6; all three M2/M3 seeds evaluated;
- all reported paired RMSE means match the archived episode rows;
- M5 scored outcomes are identical across the three repeated checkpoint indices before deduplication;
- M3 and M4 scored outcomes are identical in the archive;
- strict held-at-end task counts are zero for M2/M5 in the perception and combined conditions.

The confidence-interval endpoints are faithfully extracted from the saved artifact; the bootstrap was not rerun. Task and diagnostic counts are recomputed from saved per-episode rows. The original stage metadata is retained alongside the scorer-definition note.

## Definition corrections

- Actuator fraction 0.70 means 70% retained firing cycles, not 70% skipped cycles.
- Healthy historical RMSE uses the full episode, whereas faulted historical RMSE uses the post-onset interval.
- The pinned task scorer uses 21 consecutive observations, spanning 2.0 elapsed seconds at 10 Hz. Its JSON field labels the count-times-period product as 2.1 s. The manuscript discloses the mismatch; the prospective plan requires an explicit timestamp convention.
- M1 training coverage and evaluation coverage are distinguished.
- The repeated check and finite command repair are not treated as the same ablation.

## Scope of verification

This validation checks document build/layout and consistency of the reported archive summaries. It does not independently establish historical hardware provenance, recover the dirty run patch, reproduce controller trajectories, perform new training or experiments, validate a numerical safety certificate, or guarantee journal acceptance.

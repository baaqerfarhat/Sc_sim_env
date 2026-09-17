# Sc_sim_env

A planar 3-DOF spacecraft simulator built to test two unvalidated claims from
*Multimodal Context Learning for Actuation and Perception Fault-Tolerant Model Predictive
Control*: the behavioural-supervision gain and the numerical recovery certificate.

The simulator is written as a replica of the deployed flight stack rather than a
clean-room model of the same physics. Where the Jetson code does something unusual, the
simulator reproduces the unusual thing — the 0.40 duty ceiling, the 5% tiny-axis zeroing,
the 12 ms minimum valve on-time, the 0.5 s position filter that is hardcoded while a 0.4 s
parameter sits unused, and the yaw share that turns a declared 2 N·m cap into an actual
0.80 N·m. Every constant in `scsim/config.py` carries a provenance tag (24 CONFIRMED from
the deployment source, 4 OPEN, 6 SIM) and the whole configuration is hashed into every
result file.

**Read [`results/results.md`](results/results.md) first.** It describes the environment,
maps every number to a paper claim, and states plainly which claims the study does and
does not support.

## Findings

Supported, on matched scenario draws with block-bootstrap intervals:

- Learned context beats the zero-context hardware comparator by 0.20–0.39 m RMSE, significant in all four conditions.
- Learned context beats adaptive MPC by 0.38–0.68 m, all four significant.
- The post-allocation acceptance check is worth 1.42–1.60 m, all four significant — the largest effect measured.
- Recovery after fault onset is faster: 3.6 s vs 9.6 s median.

Not supported:

- **The behavioural-supervision gain.** `L_impact` optimises by ~22× and still costs 0.06–0.08 m in-distribution, with no gain in one-step prediction, latent retrieval, or either out-of-distribution stress family.
- **The recovery certificate.** The certified region is empty in all 2100 swept cells. The sweep locates the boundary instead: contraction needs mass and inertia known to ±5%, the step-setpoint reference is structurally uncertifiable, and the trained residual exceeds the admissible Lipschitz scale by four orders of magnitude.

## Running it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
python run_all.py --list     # stages, costs, and which are gates
python run_all.py            # everything, stopping at the first failed gate
python run_all.py 6 8 9 91   # individual stages, if their inputs already exist
```

Stages 1–3 are **gates**: they hold the simulator to the measured hardware envelopes
(achieved acceleration, tracking RMSE, estimator error, occluded error). Nothing
downstream is quotable unless they pass, so the runner stops on the first failure.

| Stage | Script | Produces | Approx |
|---|---|---|---|
| 1 | `stage1_openloop.py` | plant, allocator, duty law, fault injection (29 checks) | 1 min |
| 2 | `stage2_anchor.py` | **gate:** closed-loop hardware anchoring | 1 min |
| 3 | `stage3_estimator.py` | estimator surrogate fit, perception degradation | 3 min |
| 5 | `stage5_data_train.py` | 360 episodes, 3832 probe branches, 9 trained models | 70 min |
| 6 | `stage6_methods.py` | calibration and the 2400-episode comparison grid | 15 min |
| 7 | `stage7_certificate.py` | certificate LMIs, interval verification, authority sweep | 35 min |
| 8 | `stage8_horizon.py` | horizon axis, OOD stress, model-level metrics | 13 min |
| 9 | `stage9_figures.py`, `stage9_writeup.py` | 7 figures and `results/results.md` | 1 min |

`data/` (generated episodes and checkpoints) is not tracked; Stage 5 regenerates it.
Stages 6–9 need it, so a fresh clone must run Stage 5 first.

## Layout

```
scsim/          plant, allocator, duty law, estimator, MPC variants,
                context model, controllers, certificate, scenarios, config
stage*.py       one script per stage, each writing a frozen JSON artefact
run_all.py      ordered runner with gate semantics
results/        artefacts, run logs, figures, and results.md
```

## Reproducibility

Scenario draws are seeded by CRC32 of the draw key rather than Python's per-process
salted `hash`, so a re-run reproduces stored values to nine decimals. For a given
(condition, episode seed) every controller sees an identical reference, disturbance,
plant mismatch, estimator noise realisation and onset time — trajectories diverge only
through the control. The recovery tolerance, eligibility radius and acceptance allowance
are frozen on a calibration split that is disjoint from the test split.

## Provenance of the numbers

`results/*.json` are the frozen artefacts; `results/results.md` is generated from them by
`stage9_writeup.py` and reads nothing else, so the prose cannot drift from the numbers.
Regenerate it at any time with `python run_all.py 91`.

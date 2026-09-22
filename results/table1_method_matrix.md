| Method | Definition | Checkpoints | Unique scenarios | Rollouts | Rollouts/unit |
|---|---|---|---|---|---|
| M0 | nominal, no learned residual or context | 1 | 480 | 480 | 1.0 |
| M1 | trained constant context | 5 | 480 | 2400 | 5.0 |
| M2 | changing context, prediction losses only (SELECTED) | 5 | 480 | 2400 | 5.0 |
| M3 | changing context + behavioural loss | 5 | 480 | 2400 | 5.0 |
| M5 | nominal feedback + repair, no MPC optimisation | 1 | 480 | 480 | 1.0 |
| Mmotion | M2 without the estimator-diagnostic channels | 5 | 480 | 2400 | 5.0 |
| Roff | M2 with finite proposal repair disabled | 5 | 480 | 2400 | 5.0 |
| **total** | | | 480 | **12960** | |

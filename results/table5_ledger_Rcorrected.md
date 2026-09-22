| Method | never entered position tolerance | position but never simultaneous yaw | both tolerances but no dwell | task success | corrupted unscorable | n |
|---|---|---|---|---|---|---|
| M0 | 31 | 17 | 54 | 378 | 0 | 480 |
| M1 | 196 | 96 | 292 | 1816 | 0 | 2400 |
| M2 | 193 | 59 | 263 | 1885 | 0 | 2400 |
| M3 | 244 | 135 | 316 | 1705 | 0 | 2400 |
| M5 | 40 | 5 | 32 | 403 | 0 | 480 |
| Mmotion | 200 | 59 | 252 | 1889 | 0 | 2400 |
| Roff | 1745 | 424 | 231 | 0 | 0 | 2400 |

Orthogonal event flags (several may be true for one rollout):

| Method | departed after entering | supervisor intervention | no passing fallback | solver failure | repair search failure | deadline overrun | numerical anomaly | episode deadline censored |
|---|---|---|---|---|---|---|---|---|
| M0 | 339 | 24 | 24 | 0 | 480 | 11 | 0 | 102 |
| M1 | 1626 | 145 | 145 | 0 | 2400 | 0 | 0 | 584 |
| M2 | 1540 | 52 | 52 | 330 | 2400 | 0 | 0 | 515 |
| M3 | 1592 | 142 | 142 | 1 | 2400 | 1 | 0 | 695 |
| M5 | 288 | 10 | 0 | 0 | 0 | 2 | 0 | 77 |
| Mmotion | 1534 | 63 | 63 | 403 | 2400 | 6 | 0 | 511 |
| Roff | 229 | 1120 | 764 | 1425 | 0 | 3 | 0 | 2400 |

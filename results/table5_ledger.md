| Method | never entered position tolerance | position but never simultaneous yaw | both tolerances but no dwell | task success | corrupted unscorable | n |
|---|---|---|---|---|---|---|
| M0 | 200 | 11 | 41 | 228 | 0 | 480 |
| M1 | 1025 | 48 | 194 | 1133 | 0 | 2400 |
| M2 | 1027 | 62 | 178 | 1133 | 0 | 2400 |
| M3 | 1074 | 70 | 206 | 1050 | 0 | 2400 |
| M5 | 193 | 11 | 27 | 249 | 0 | 480 |
| Mmotion | 1047 | 60 | 177 | 1116 | 0 | 2400 |
| Roff | 1938 | 284 | 177 | 1 | 0 | 2400 |

Orthogonal event flags (several may be true for one rollout):

| Method | departed after entering | supervisor intervention | no passing fallback | solver failure | repair search failure | deadline overrun | numerical anomaly | episode deadline censored |
|---|---|---|---|---|---|---|---|---|
| M0 | 191 | 304 | 0 | 0 | 417 | 4 | 0 | 252 |
| M1 | 917 | 1510 | 0 | 0 | 2100 | 1 | 0 | 1267 |
| M2 | 874 | 1481 | 0 | 301 | 2074 | 2 | 0 | 1267 |
| M3 | 901 | 1518 | 0 | 0 | 2096 | 2 | 0 | 1350 |
| M5 | 176 | 300 | 0 | 0 | 0 | 0 | 0 | 231 |
| Mmotion | 866 | 1482 | 0 | 383 | 2076 | 1 | 0 | 1284 |
| Roff | 173 | 2392 | 0 | 740 | 0 | 1 | 0 | 2399 |

"""Reproduce the whole simulation study from a clean checkout.

Stages are gates as much as steps. Stage 0 checks the semantics of the simulator
itself, stages 1-3 hold it to the measured hardware envelopes, and nothing downstream
is meaningful if any of them fail, so the run stops on the first non-zero exit rather
than carrying on and producing numbers nobody should quote.

    python run_all.py              # everything, in order
    python run_all.py 6 8 9        # only the listed stages
    python run_all.py --list       # what each stage costs

Stage 5 (data generation and training) and Stage 6 (the comparison grid) dominate the
wall time. Both write their outputs to results/, so a later stage can be re-run alone
provided its inputs already exist.

RUN IDENTITY. Every stage records the config manifest hash, and the corrected campaign
writes under a distinct run id so its outputs can never be mixed with the earlier
development campaign preserved in results_v1_archive/ and data_v1_archive/. A config
hash alone is not sufficient provenance when controller source or checkpoint weights
change, so the code commit is recorded too.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

# stage -> (script, what it produces, roughly how long on 12 cores)
STAGES = {
    0: ("stage0_semantics.py",
        "GATE: information boundary, physics, selection semantics, enclosures",
        "1 min"),
    1: ("stage1_openloop.py", "plant, allocator, duty law, fault injection", "1 min"),
    2: ("stage2_anchor.py", "GATE: closed-loop hardware anchoring", "1 min"),
    3: ("stage3_estimator.py", "estimator surrogate fit + perception degradation",
        "3 min"),
    5: ("stage5_data_train.py",
        "episodes, matched probe groups, lambda_I grid, trained models", "75 min"),
    6: ("stage6_methods.py", "calibration + the M0-M6 comparison grid", "35 min"),
    7: ("stage7_certificate.py", "certificate LMIs, interval verification, sweep",
        "35 min"),
    8: ("stage8_horizon.py", "horizon axis, OOD stress, model-level metrics", "13 min"),
    9: ("stage9_figures.py", "figures", "1 min"),
    91: ("stage9_writeup.py", "results.md + README findings block", "instant"),
    92: ("stage9_response.py",
         "response_to_retention_plan.md (point-by-point reply to the review)",
         "instant"),
}
ORDER = [0, 1, 2, 3, 5, 6, 7, 8, 9, 91, 92]

# Gates: a failure invalidates everything after it.
#
# Stage 0 is FIRST and is the most important of them. It asserts that hidden fault
# information cannot reach the controller, that physical thrust follows the true
# attitude, that the selection logic transmits what it claims to, and that the
# interval enclosures are not falsifiable by sampling. An earlier campaign had no such
# stage and shipped results in which the encoder observed the fault through the command
# channel, the plant rotated force by the estimator's yaw, and a failing fallback was
# transmitted anyway. Ordering alone never caught any of it.
GATES = {0, 1, 2, 3}


def run(stage):
    script, what, cost = STAGES[stage]
    label = f"stage {stage if stage != 91 else '9 (writeup)'}"
    print(f"\n{'=' * 78}\n{label}: {what}  [~{cost}]\n{'=' * 78}", flush=True)
    t0 = time.time()
    log = f"results/stage{stage}.log"
    os.makedirs("results", exist_ok=True)
    with open(log, "w") as f:
        rc = subprocess.call([sys.executable, "-u", "-W", "ignore", script],
                             stdout=f, stderr=subprocess.STDOUT)
    dt = (time.time() - t0) / 60
    tail = subprocess.run(["tail", "-3", log], capture_output=True,
                          text=True).stdout.rstrip()
    print(f"{tail}\n-> exit {rc} in {dt:.1f} min (log: {log})", flush=True)
    return rc


# Sec 2 of the retention plan: a campaign whose CONTROLLER changed gets its own
# identifier. v3 unified the fault-slot execution contract, made M4 a
# single-component ablation, scored task completion at the final waypoint and swept
# both candidate horizons. Its numbers must not be pooled with v2's.
RUN_ID = "v3-contract-and-ablation"


def write_run_identity():
    """Sec 10: record what produced these artefacts, beyond the config hash."""
    import json

    from scsim import config as C

    def sh(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=10).stdout.strip() or None
        except Exception:
            return None

    ident = {
        "run_id": RUN_ID,
        "config_manifest_hash": C.manifest_hash(),
        "git_commit": sh("git", "rev-parse", "HEAD"),
        "git_dirty": bool(sh("git", "status", "--porcelain")),
        "python": sys.version.split()[0],
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "supersedes": (
            "v1 (results_v1_archive): defective information boundary, plant rotation "
            "and fallback selection. v2 (run id v2-corrected): fixed those, but "
            "applied the hidden fault one cycle early in the closed-loop path, "
            "bundled three safeguards into the M4 ablation, and scored task "
            "completion at the current rather than the final waypoint. Neither is "
            "comparable with these numbers."),
        "changes_vs_previous": [
            "single physical execution contract: commit() is software-only, realize() "
            "previews then consumes exactly one fault slot, on every path",
            "M4 is a single-component ablation: only the Eq. (18) post-allocation "
            "decrease test is disabled; eligibility, first-action, solver fallback "
            "and the command-admissibility budget remain enforced",
            "all action sources logged and aggregated; shares sum to one",
            "task completion scored at the FINAL waypoint and heading; recovery is "
            "onset-relative with maintenance and reacquisition separated",
            "both candidate horizons (manuscript N=10, build spec N=12) swept and "
            "compared on matched draws",
        ],
    }
    os.makedirs("results", exist_ok=True)
    with open("results/run_identity.json", "w") as f:
        json.dump(ident, f, indent=1)
    print(f"run id {RUN_ID}  config {ident['config_manifest_hash']}  "
          f"commit {str(ident['git_commit'])[:8]}"
          + ("  (WORKING TREE DIRTY)" if ident["git_dirty"] else ""))


def main(argv):
    if "--list" in argv:
        for s in ORDER:
            script, what, cost = STAGES[s]
            gate = "  GATE" if s in GATES else ""
            print(f"  {s:<3} {script:<22} ~{cost:<9} {what}{gate}")
        return 0

    want = [int(a) for a in argv if a.isdigit()] or ORDER
    unknown = [s for s in want if s not in STAGES]
    if unknown:
        print(f"unknown stage(s): {unknown}; known: {sorted(STAGES)}")
        return 2

    write_run_identity()
    t0 = time.time()
    for s in want:
        rc = run(s)
        if rc != 0:
            print(f"\nSTOPPED: stage {s} exited {rc}."
                  + (" This is an anchoring GATE, so no downstream number is "
                     "quotable until it passes." if s in GATES else ""))
            return rc
    print(f"\nall requested stages done in {(time.time() - t0) / 60:.1f} min")
    print("read results/results.md; figures in results/figures/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

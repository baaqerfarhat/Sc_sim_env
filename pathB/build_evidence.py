#!/usr/bin/env python3
"""Build the compact Stage-6 evidence record used by experiments.tex.

This script only summarizes an existing artifact; it never runs a simulation.  Usage:

    python build_evidence.py PATH/TO/results__stage6_methods.json

The output is evidence_summary.json beside this script unless --output is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean


CONDITIONS = ("healthy", "actuator", "perception", "combined")
PUBLIC_SNAPSHOT = "9e2af1607dfe5f90a76bf796b293436d71fab7ad"


def finite_mean(values):
    values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return fmean(values) if values else None


def rounded(value, digits=4):
    return None if value is None else round(float(value), digits)


def stable_value(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Stage-6 methods JSON artifact")
    parser.add_argument("--training", type=Path, help="Stage-5 training JSON (otherwise found beside source)")
    parser.add_argument("--identity", type=Path, help="Optional run-identity JSON (otherwise found beside source)")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("evidence_summary.json"))
    args = parser.parse_args()

    raw = args.source.read_bytes()
    data = json.loads(raw)
    rows = data["rows"]

    def adjacent_file(prefixed_name, plain_name):
        prefixed = args.source.with_name(prefixed_name)
        return prefixed if prefixed.exists() else args.source.with_name(plain_name)

    training_path = args.training or adjacent_file("results__stage5_training.json", "stage5_training.json")
    if not training_path.exists():
        raise FileNotFoundError(
            "Provide Stage-5 training metadata with --training or beside the Stage-6 "
            "artifact so trained and evaluated seed counts can be distinguished"
        )
    training_raw = training_path.read_bytes()
    training = json.loads(training_raw)
    training_runs = training["runs"]

    assert tuple(data["conditions"]) == CONDITIONS
    assert data["n_test_per_condition"] == 60
    assert data["model_seeds"] == [0, 1, 2]
    assert len(rows) == 5280
    for name in ("nominal_recovery", "constant_context", "no_impact", "full",
                 "full_no_check", "fallback_only"):
        assert name in data["methods"]

    trained_seed_ids = {
        "M1_constant_context": sorted({
            int(run["seed"]) for run in training_runs.values()
            if run["tag"].startswith("const_s")
        }),
        "M2_no_impact": sorted({
            int(run["seed"]) for run in training_runs.values()
            if run["tag"].startswith("no_impact_s")
        }),
        "M3_full": sorted({
            int(run["seed"]) for run in training_runs.values()
            if run["tag"].startswith("full_s")
        }),
    }
    evaluated_seed_ids = {
        "M1_constant_context": sorted({
            int(row["model_seed"]) for row in rows
            if row["method"] == "constant_context"
        }),
        "M2_no_impact": sorted({
            int(row["model_seed"]) for row in rows
            if row["method"] == "no_impact"
        }),
        "M3_full": sorted({
            int(row["model_seed"]) for row in rows
            if row["method"] == "full"
        }),
    }
    assert trained_seed_ids == {
        "M1_constant_context": [0, 1, 2],
        "M2_no_impact": [0, 1, 2],
        "M3_full": [0, 1, 2],
    }
    assert evaluated_seed_ids == {
        "M1_constant_context": [0],
        "M2_no_impact": [0, 1, 2],
        "M3_full": [0, 1, 2],
    }

    contrasts = {
        "M2-M0": ("no_impact-nominal_recovery", "episode"),
        "M2-M1": ("no_impact-constant_context", "episode"),
        "M2-M5": ("no_impact-fallback_only", "crossed"),
        "M3-M2": ("full-no_impact", "crossed"),
    }
    method_pairs = {
        "M2-M0": ("no_impact", "nominal_recovery"),
        "M2-M1": ("no_impact", "constant_context"),
        "M2-M5": ("no_impact", "fallback_only"),
        "M3-M2": ("full", "no_impact"),
    }
    outcome_index = {
        (row["method"], row["condition"], row["model_seed"], row["ep_seed"]): row
        for row in rows
    }
    effects = {}
    for label, (key_prefix, interval) in contrasts.items():
        effects[label] = {}
        for condition in CONDITIONS:
            key = f"{key_prefix}|{condition}|post_onset_rmse"
            point = data["paired_effects"][key]
            first, second = method_pairs[label]
            differences = []
            for row in rows:
                if row["method"] != first or row["condition"] != condition:
                    continue
                paired_key = (second, condition, row["model_seed"], row["ep_seed"])
                if paired_key not in outcome_index:
                    paired_key = (second, condition, 0, row["ep_seed"])
                comparator = outcome_index[paired_key]
                differences.append(row["post_onset_rmse"] - comparator["post_onset_rmse"])
            assert math.isclose(fmean(differences), point["mean"], abs_tol=1e-12)
            ci = (data["paired_effects"][key + "|crossed"]
                  if interval == "crossed" else point)
            effects[label][condition] = {
                "mean_m": rounded(point["mean"]),
                "ci95_m": [rounded(ci["lo"]), rounded(ci["hi"])],
                "interval_level": interval,
                "unique_scenarios": int(point["n_blocks"]),
                "rollouts": int(point["n_pairs"]),
            }

    by_cell = {}
    for row in rows:
        by_cell.setdefault((row["method"], row["condition"], row["model_seed"]), []).append(row)

    # M5 is deterministic in the scored outcomes.  Verify this before deduplicating
    # its three repeated checkpoint-index rows to 60 unique scenario draws.
    outcome_keys = ("post_onset_rmse", "post_onset_peak", "task_success",
                    "task_held_at_end", "success", "recovery_time")
    for condition in CONDITIONS:
        for ep_seed in sorted({r["ep_seed"] for r in rows if r["method"] == "fallback_only"
                               and r["condition"] == condition}):
            same_episode = sorted(
                (r for r in rows if r["method"] == "fallback_only"
                 and r["condition"] == condition and r["ep_seed"] == ep_seed),
                key=lambda r: r["model_seed"],
            )
            assert len(same_episode) == 3
            reference = tuple(stable_value(same_episode[0][k]) for k in outcome_keys)
            assert all(tuple(stable_value(r[k]) for k in outcome_keys) == reference
                       for r in same_episode[1:])

    task = {}
    for condition in CONDITIONS:
        m2 = [r for r in rows if r["method"] == "no_impact" and r["condition"] == condition]
        m5 = [r for r in rows if r["method"] == "fallback_only"
              and r["condition"] == condition and r["model_seed"] == 0]
        assert len(m2) == 180 and len(m5) == 60
        task[condition] = {
            "M2": {
                "success": sum(bool(r["task_success"]) for r in m2),
                "n": len(m2),
                "held_at_end": sum(bool(r["task_held_at_end"]) for r in m2),
            },
            "M5_deduplicated": {
                "success": sum(bool(r["task_success"]) for r in m5),
                "n": len(m5),
                "held_at_end": sum(bool(r["task_held_at_end"]) for r in m5),
            },
        }
    for condition in ("perception", "combined"):
        assert task[condition]["M2"]["held_at_end"] == 0
        assert task[condition]["M5_deduplicated"]["held_at_end"] == 0

    recovery = {}
    for condition in CONDITIONS[1:]:
        m2 = [r for r in rows if r["method"] == "no_impact" and r["condition"] == condition]
        m5 = [r for r in rows if r["method"] == "fallback_only"
              and r["condition"] == condition and r["model_seed"] == 0]
        recovery[condition] = {
            "M2": {"success": sum(bool(r["success"]) for r in m2), "n": len(m2)},
            "M5_deduplicated": {"success": sum(bool(r["success"]) for r in m5), "n": len(m5)},
        }

    sources = {}
    for method in ("no_impact", "full"):
        sources[method] = {}
        for condition in CONDITIONS:
            subset = [r for r in rows if r["method"] == method and r["condition"] == condition]
            sources[method][condition] = {
                "candidate": rounded(finite_mean(r["frac_src_candidate"] for r in subset)),
                "supervisor": rounded(finite_mean(r["frac_src_supervisor"] for r in subset)),
            }
    sources["fallback_only_deduplicated"] = {}
    for condition in CONDITIONS:
        subset = [r for r in rows if r["method"] == "fallback_only"
                  and r["condition"] == condition and r["model_seed"] == 0]
        sources["fallback_only_deduplicated"][condition] = {
            "fallback_only": rounded(finite_mean(r["frac_src_fallback_only"] for r in subset)),
            "supervisor": rounded(finite_mean(r["frac_src_supervisor"] for r in subset)),
        }

    # M3 and M4 must be outcome-identical in this campaign.
    indexed = {(r["method"], r["condition"], r["model_seed"], r["ep_seed"]): r for r in rows}
    for condition in CONDITIONS:
        for seed in data["model_seeds"]:
            for ep_seed in sorted({r["ep_seed"] for r in rows if r["method"] == "full"
                                   and r["condition"] == condition and r["model_seed"] == seed}):
                a = indexed[("full", condition, seed, ep_seed)]
                b = indexed[("full_no_check", condition, seed, ep_seed)]
                assert all(stable_value(a[k]) == stable_value(b[k]) for k in outcome_keys)

    identity_path = args.identity or adjacent_file("results__run_identity.json", "run_identity.json")
    identity = json.loads(identity_path.read_text()) if identity_path.exists() else {}
    summary = {
        "source": {
            "artifact": args.source.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "training_artifact": training_path.name,
            "training_sha256": hashlib.sha256(training_raw).hexdigest(),
            "public_snapshot_commit": PUBLIC_SNAPSHOT,
            "archived_run_commit": identity.get("git_commit"),
            "archived_run_dirty": identity.get("git_dirty"),
            "manifest_hash": data["manifest_hash"],
        },
        "design": {
            "conditions": list(CONDITIONS),
            "scenarios_per_condition": 60,
            "trained_seed_ids": trained_seed_ids,
            "trained_seed_counts": {
                method: len(seeds) for method, seeds in trained_seed_ids.items()
            },
            "evaluated_seed_ids": evaluated_seed_ids,
            "evaluated_seed_counts": {
                method: len(seeds) for method, seeds in evaluated_seed_ids.items()
            },
            "primary_endpoint": data["primary_endpoint"],
            "recovery_tolerance_m": rounded(data["recovery_tolerance_m"]),
            "task_spec": data["task_spec"],
            "task_scoring_note": (
                "Archived metadata labels dwell_s=2.1. The pinned Stage-6 source uses "
                "TASK_DWELL_STEPS=21 consecutive 10 Hz observations, spanning 2.0 elapsed "
                "seconds. The original metadata is preserved above, not silently corrected."
            ),
            "calibration": {
                "R": rounded(data["calibration"]["R"]),
                "eta": rounded(data["calibration"]["eta"]),
                "source_policy": "M3/full, seed 0, separate calibration split",
            },
        },
        "post_onset_rmse_effects": effects,
        "task_completion": task,
        "diagnostic_recovery": recovery,
        "action_sources": sources,
        "assertions": {
            "M5_outcomes_identical_across_repeated_seed_indices": True,
            "M3_M4_outcomes_identical": True,
            "degraded_held_at_end_zero_for_M2_M5": True,
            "paired_effect_means_match_episode_rows": True,
        },
    }
    args.output.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()

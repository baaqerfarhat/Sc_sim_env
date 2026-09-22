"""Path B Sec 13: the tables and figures, built only from frozen artefacts.

Nothing here recomputes a number. Every value is read from the JSON written by an earlier
stage, so a table and the artefact behind it cannot drift apart, and regenerating the
manuscript cannot silently change a result.

  Table 1  the method matrix as RUN, with checkpoint counts, unique scenario counts and
           rollout counts separated, so a deterministic method's replicated rollouts can
           never be read as independent samples
  Table 2  descriptive outcomes per family, condition and method
  Table 3  the estimands, their intervals and the claim-gate verdicts
  Table 4  the action-source decomposition over the full 12-label taxonomy
  Table 5  the failure and censoring ledger

  Fig 1  the allowance curve, showing where the first-action screen stops firing
  Fig 2  the estimation floor and why the archived true-state tolerance was unreachable
  Fig 3  a forest plot of every contrast on both families
  Fig 4  representative traces from the declared scenario
"""
from __future__ import annotations

import json
import os

import numpy as np

import pathb_common as PB

RES, FIG = "results", "results/figs"
os.makedirs(FIG, exist_ok=True)


def load(name):
    with open(f"{RES}/{name}.json") as f:
        return json.load(f)


def _f(v, p=4, nan="--"):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return nan
    return nan if not np.isfinite(x) else f"{x:.{p}f}"


# ==========================================================================
# tables, emitted as markdown so they drop straight into the answer document
# ==========================================================================
def table1(test):
    L = ["| Method | Definition | Checkpoints | Unique scenarios | Rollouts | Rollouts/unit |",
         "|---|---|---|---|---|---|"]
    for mid, c in test["counts"].items():
        L.append(f"| {mid} | {PB.METHODS[mid]['label']} | {c['n_distinct_checkpoints']} "
                 f"| {c['n_unique_units']} | {c['n_rollouts']} "
                 f"| {c['rollouts_per_unit']:.1f} |")
    tot = sum(c["n_rollouts"] for c in test["counts"].values())
    L.append(f"| **total** | | | {test['manifest']['n_units']} | **{tot}** | |")
    return "\n".join(L)


def table2(an):
    t = an["table"]
    L = ["| Family | Condition | Method | post-onset RMSE (m) | peak (m) | yaw RMSE (rad) "
         "| achieved | declared | MPC share | supervisor share |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for f in PB.FAMILIES:
        for c in PB.CONDITIONS:
            for mid in PB.METHODS:
                k = f"{f}|{c}|{mid}"
                if k not in t:
                    continue
                r = t[k]
                L.append(
                    f"| {f} | {c} | {mid} "
                    f"| {_f(r['post_onset_rmse']['mean'],3)} "
                    f"± {_f(r['post_onset_rmse']['sd'],3)} "
                    f"| {_f(r['post_onset_peak']['mean'],3)} "
                    f"| {_f(r['post_onset_rmse_yaw']['mean'],3)} "
                    f"| {_f(r['task_success_rate'],3)} "
                    f"| {_f(r.get('task_success_rate_declared'),3)} "
                    f"| {_f(r['share_mpc']['mean'],3)} "
                    f"| {_f(r['share_supervisor']['mean'],3)} |")
    return "\n".join(L)


def table3(an):
    L = ["| Estimand | Family | Contrast | Point (m) | 95% interval | 97.5% interval "
         "| Verdict |", "|---|---|---|---|---|---|---|"]
    for name, s in an["co_primary"].items():
        L.append(f"| **{name}** (co-primary) | {s['family']} | {s['contrast']} "
                 f"| {s['mean']:+.4f} "
                 f"| [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}] "
                 f"| [{s['ci975'][0]:+.4f}, {s['ci975'][1]:+.4f}] "
                 f"| {'excludes 0' if s['excludes_zero_975'] else 'contains 0'} |")
    for k, s in an["secondary"].items():
        L.append(f"| secondary | {s['family']} | {s['contrast']} | {s['mean']:+.4f} "
                 f"| [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}] | -- "
                 f"| {'excludes 0' if s['excludes_zero_95'] else 'contains 0'} |")
    return "\n".join(L)


def table4(an):
    """Sec 8.4: the full taxonomy, so no share of commands is left unattributed."""
    t = an["table"]
    srcs = [s for s in PB.ACTION_SOURCES
            if any(np.isfinite(t[k].get(f"src_{s}", {}).get("mean", np.nan))
                   and t[k][f"src_{s}"]["mean"] > 1e-9 for k in t)]
    L = ["| Family | Condition | Method | " + " | ".join(srcs) + " | sum |",
         "|---" * (4 + len(srcs)) + "|"]
    for f in PB.FAMILIES:
        for c in PB.CONDITIONS:
            for mid in PB.METHODS:
                k = f"{f}|{c}|{mid}"
                if k not in t:
                    continue
                vals = [t[k].get(f"src_{s}", {}).get("mean", np.nan) for s in srcs]
                tot = np.nansum([v for v in vals if np.isfinite(v)])
                L.append(f"| {f} | {c} | {mid} | "
                         + " | ".join(_f(v, 3, nan="0.000") for v in vals)
                         + f" | {tot:.3f} |")
    return "\n".join(L)


def table5(test):
    cats = PB.PROGRESS_CATEGORIES
    L = ["| Method | " + " | ".join(c.replace("_", " ") for c in cats) + " | n |",
         "|---" * (2 + len(cats)) + "|"]
    for mid, led in test["ledger"].items():
        L.append(f"| {mid} | " + " | ".join(str(led["progress"][c]) for c in cats)
                 + f" | {led['n']} |")
    L += ["", "Orthogonal event flags (several may be true for one rollout):", "",
          "| Method | " + " | ".join(f.replace("_", " ") for f in PB.EVENT_FLAGS)
          + " |", "|---" * (1 + len(PB.EVENT_FLAGS)) + "|"]
    for mid, led in test["ledger"].items():
        L.append(f"| {mid} | " + " | ".join(str(led["flags"][f])
                                            for f in PB.EVENT_FLAGS) + " |")
    return "\n".join(L)


# ==========================================================================
# figures
# ==========================================================================
def figures(gates, floor, an, test, sfx=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    made = []

    # ---- Fig 1: the allowance curve -------------------------------------
    cur = gates["calibration"]["eta_curve"]
    fin = [c for c in cur if np.isfinite(float(c["eta"]))]
    inf = [c for c in cur if not np.isfinite(float(c["eta"]))]
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.4))
    # eta spans 0 to 64 and then the no-check limit, so it is plotted against RANK with
    # labelled ticks. A log axis cannot show eta = 0 and a symlog axis puts meaningless
    # negative ticks on a non-negative parameter.
    e = [float(c["eta"]) for c in fin]
    x = np.arange(len(fin))
    labs = [("0" if v == 0 else f"{v:g}") for v in e]
    ax[0].plot(x, [c["post_onset_rmse"] for c in fin], "o-", color="#1f77b4")
    if inf:
        ax[0].axhline(inf[0]["post_onset_rmse"], ls="--", color="#d62728",
                      label=r"no screen at all ($\eta\to\infty$)")
        ax[0].legend(fontsize=8, frameon=False)
    ax[0].set_xlabel(r"first-action allowance $\eta$")
    ax[0].set_ylabel("calibration post-onset RMSE (m)")
    ax[0].set_title("the screen stops costing anything once it stops firing", fontsize=9)
    ax[1].plot(x, [c["share_mpc"] for c in fin], "o-", label="MPC command share")
    ax[1].plot(x, [c["share_supervisor"] for c in fin], "s-", label="supervisor share")
    if inf:
        ax[1].axhline(inf[0]["share_supervisor"], ls="--", color="#d62728", lw=0.9)
    ax[1].set_xlabel(r"$\eta$")
    ax[1].set_ylabel("share of commanded steps")
    for a in ax:
        a.set_xticks(x)
        a.set_xticklabels(labs, fontsize=7.5)
    ax[1].set_title("the residual supervisor share is eligibility, not the screen",
                    fontsize=9)
    ax[1].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    p = f"{FIG}/fig1_allowance_curve{sfx}.png"
    fig.savefig(p, dpi=170)
    plt.close(fig)
    made.append(p)

    # ---- Fig 2: the estimation floor ------------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.4))
    for mode, col in (("healthy", "#1f77b4"), ("occluded", "#d62728")):
        o = floor["openloop"][mode]
        t = sorted(float(k) for k in o["pos_by_time"])
        ax[0].plot(t, [o["pos_by_time"][f"{int(k)}"] for k in t], "o-", color=col,
                   label=mode)
        ax[1].plot(t, [o["yaw_by_time_deg"][f"{int(k)}"] for k in t], "o-", color=col,
                   label=mode)
    ax[0].axhline(PB.TASK_TOL_POS, ls=":", color="k",
                  label=f"archived true-state tol {PB.TASK_TOL_POS} m")
    ax[0].axhline(PB.TASK_TOL_POS_TRUE, ls="--", color="g",
                  label=f"v2 achieved tol {PB.TASK_TOL_POS_TRUE} m")
    ax[1].axhline(5.0, ls=":", color="k", label="archived 5 deg")
    ax[1].axhline(15.0, ls="--", color="g", label="v2 achieved 15 deg")
    ax[0].set_xlabel("time since alignment (s)")
    ax[0].set_ylabel("estimation error, 90th pct (m)")
    ax[0].set_title("no absolute reference after $t_0$: the error is a random walk",
                    fontsize=9)
    ax[1].set_xlabel("time since alignment (s)")
    ax[1].set_ylabel("heading error, 90th pct (deg)")
    ax[1].set_title("the archived true-state tolerance sits below the floor", fontsize=9)
    for a in ax:
        a.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    p = f"{FIG}/fig2_estimation_floor{sfx}.png"
    fig.savefig(p, dpi=170)
    plt.close(fig)
    made.append(p)

    # ---- Fig 3: forest plot ---------------------------------------------
    items = []
    for name, s in an["co_primary"].items():
        items.append((f"{name}  {s['contrast']} [{s['family']}]", s["mean"],
                      s["ci975"], True))
    for k, s in an["secondary"].items():
        items.append((f"{s['contrast']} [{s['family']}]", s["mean"], s["ci95"], False))
    items.reverse()
    fig, ax = plt.subplots(figsize=(7.2, 0.34 * len(items) + 1.1))
    for i, (lab, m, ci, co) in enumerate(items):
        col = "#d62728" if m > 0 and not (ci[0] <= 0 <= ci[1]) else (
            "#2ca02c" if m < 0 and not (ci[0] <= 0 <= ci[1]) else "#7f7f7f")
        ax.plot(ci, [i, i], "-", color=col, lw=2.6 if co else 1.5)
        ax.plot([m], [i], "D" if co else "o", color=col, ms=6 if co else 4.5)
    ax.axvline(0, color="k", lw=0.9)
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels([i[0] for i in items], fontsize=7.5)
    ax.set_xlabel("difference in condition-balanced post-onset position RMSE (m)\n"
                  "negative favours the first-named method")
    ax.set_title("co-primary contrasts use the 97.5% Bonferroni interval (diamonds)",
                 fontsize=9)
    fig.tight_layout()
    p = f"{FIG}/fig3_forest{sfx}.png"
    fig.savefig(p, dpi=170)
    plt.close(fig)
    made.append(p)

    # ---- Fig 4: representative traces -----------------------------------
    try:
        with open(f"{RES}/pathb_traces{sfx}.json") as f:
            tr = json.load(f)
    except FileNotFoundError:
        tr = {}
    if tr:
        fig, ax = plt.subplots(2, 2, figsize=(9.5, 5.6))
        keys = sorted(tr)[:2]
        for j, k in enumerate(keys):
            d = tr[k]
            xt = np.asarray(d["x_true"], dtype=float)
            xh = np.asarray(d["x_hat"], dtype=float)
            rs = np.asarray(d["ref_score"], dtype=float)
            t = np.arange(len(xt)) * 0.1
            on = d.get("onset", 0) * 0.1
            ax[0, j].plot(t, np.linalg.norm(xt[:, :2] - rs[:, :2], axis=1), lw=1.2,
                          label="true tracking error")
            ax[0, j].plot(t, np.linalg.norm(xh[:, :2] - rs[:, :2], axis=1), lw=1.0,
                          label="error the controller sees")
            ax[0, j].plot(t, np.linalg.norm(xh[:, :2] - xt[:, :2], axis=1), lw=1.0,
                          ls="--", label="estimation error")
            ax[0, j].axvline(on, color="r", ls=":", lw=1.0, label="onset")
            ax[0, j].set_title(k.replace("|", "  "), fontsize=8)
            ax[0, j].set_ylabel("position error (m)")
            ax[0, j].legend(fontsize=6.5, frameon=False)
            src = d.get("action_src", [])
            labs = sorted(set(src))
            idx = {s: i for i, s in enumerate(labs)}
            ax[1, j].plot(t[:len(src)], [idx[s] for s in src], ".", ms=2.2)
            ax[1, j].set_yticks(range(len(labs)))
            ax[1, j].set_yticklabels(labs, fontsize=6.5)
            ax[1, j].axvline(on, color="r", ls=":", lw=1.0)
            ax[1, j].set_xlabel("time (s)")
        fig.tight_layout()
        p = f"{FIG}/fig4_traces{sfx}.png"
        fig.savefig(p, dpi=170)
        plt.close(fig)
        made.append(p)
    return made


def main():
    # Both matrices are reported. The suffix keeps the pre-registered tables and the
    # corrected-radius tables side by side rather than one overwriting the other.
    import sys
    sfx = "_Rcorrected" if "--corrected" in sys.argv else ""
    gates, floor = load("pathb4_gates"), load("pathb2_floor")
    test, an = load(f"pathb5_test{sfx}"), load(f"pathb6_analysis{sfx}")

    tabs = {f"table1_method_matrix{sfx}": table1(test),
            f"table2_descriptive{sfx}": table2(an),
            f"table3_estimands{sfx}": table3(an),
            f"table4_action_sources{sfx}": table4(an),
            f"table5_ledger{sfx}": table5(test)}
    for name, md in tabs.items():
        with open(f"{RES}/{name}.md", "w") as f:
            f.write(md + "\n")
        print(f"wrote {RES}/{name}.md ({md.count(chr(10)) + 1} lines)")

    made = figures(gates, floor, an, test, sfx)
    for p in made:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

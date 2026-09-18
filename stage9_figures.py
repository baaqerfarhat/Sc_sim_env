"""Stage 9: figures and the results writeup, mapping each artefact to a paper claim.

Deliverables (protocol Sec 9):
  fig1_anchoring        the hardware anchors the sim is held to, and where it lands
  fig2_methods          main comparison, with paired effects and seed-level points
  fig3_trial            the four aligned panels for the prespecified representative
                        combined-fault trial
  fig4_certificate      authority / tolerance boundary, and which term binds
  fig5_severity         severity map: RMSE and activity over effectiveness x perception
  results.md            claim-by-claim evidence table

The representative trial is prespecified as the full-method combined-fault trial whose
RMSE is nearest the median among complete trials, chosen from the Stage 6 records
before any trace is plotted.
"""
from __future__ import annotations

import json
import os

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from scsim import config as C

RES, FIG = "results", "results/figures"
os.makedirs(FIG, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 140, "savefig.dpi": 140, "font.size": 8,
    "axes.titlesize": 9, "axes.labelsize": 8, "legend.fontsize": 7,
    "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True,
    "figure.constrained_layout.use": True,
})

METHOD_LABEL = {
    "zero_context": "HW  zero-context (hardware)",
    "nominal_recovery": "M0  nominal, no residual",
    "constant_context": "M1  constant context",
    "no_impact": r"M2  changing context ($\lambda_I{=}0$)",
    "full": "M3  + behavioural supervision",
    "full_no_check": "M4  M3, no post-alloc check",
    "fallback_only": "M5  checked fallback only",
    "adaptive_mpc": "M6  adaptive MPC",
}
MC = {"zero_context": "#7f7f7f", "nominal_recovery": "#2ca02c",
      "constant_context": "#9467bd", "adaptive_mpc": "#8c564b",
      "no_impact": "#1f77b4", "full": "#d62728",
      "full_no_check": "#ff9896", "fallback_only": "#17becf"}
COND_LABEL = {"healthy": "healthy", "actuator": "actuation fault",
              "perception": "perception degr.", "combined": "combined"}


def load(name):
    p = f"{RES}/{name}"
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


# ==========================================================================
def _detail_value(check):
    """Pull the leading numeric out of a check's detail string."""
    import re
    m = re.search(r"=\s*([-\d.]+)", check.get("detail", ""))
    return float(m.group(1)) if m else None


def fig_anchoring(s1, s2, s3):
    """What the simulation is pinned to. Every later claim rests on these."""
    fig, ax = plt.subplots(1, 3, figsize=(9.4, 2.7))
    c2 = s2["checks"]
    c3 = s3["checks"]

    # -- achieved acceleration --
    a = ax[0]
    lo, hi = C.ANCHORS.accel_p95_lo, C.ANCHORS.accel_p95_hi
    a.axhspan(lo, hi, color="#2ca02c", alpha=0.18,
              label=f"hardware band {lo}–{hi}")
    v = c2["accel"]["p95"]
    a.plot([0], [v], "o", color="#d62728", ms=8, label=f"sim p95 {v:.4f}")
    a.plot([0], [c2["accel"]["median"]], "d", color="#1f77b4", ms=6,
           label=f"sim median {c2['accel']['median']:.4f}")
    a.plot([0], [c2["accel"]["chain_pred"]], "*", color="black", ms=9,
           label=f"open-loop chain {c2['accel']['chain_pred']:.4f}")
    a.set_xticks([])
    a.set_xlim(-0.5, 0.5)
    a.set_ylabel(r"achieved $|a|$  (m/s$^2$)")
    a.set_title("A. actuator authority")
    a.legend(loc="upper right", fontsize=6.2)

    # -- position RMSE / peak vs hardware Table I --
    a = ax[1]
    tk = c2["tracking"]
    a.errorbar([0], [tk["hw_rmse"]], yerr=[C.ANCHORS.rmse_healthy_sd], fmt="s",
               color="#2ca02c", ms=7, capsize=4,
               label=f"hw RMSE {tk['hw_rmse']:.3f}")
    a.plot([1], [tk["rmse_mean"]], "o", color="#d62728", ms=7,
           label=f"sim RMSE {tk['rmse_mean']:.3f}")
    a.plot([0], [tk["hw_peak"]], "s", color="#2ca02c", ms=7, mfc="none",
           label=f"hw peak {tk['hw_peak']:.3f}")
    a.plot([1], [tk["peak_mean"]], "o", color="#d62728", ms=7, mfc="none",
           label=f"sim peak {tk['peak_mean']:.3f}")
    a.set_xlim(-0.6, 1.6)
    a.set_xticks([0, 1])
    a.set_xticklabels(["hardware", "sim"])
    a.set_ylabel("position error (m)")
    a.set_title("B. tracking, step reference")
    a.legend(loc="center right", fontsize=6.2)

    # -- estimation error envelopes --
    a = ax[2]
    bands = [("healthy\n$|dx|$ p95", C.ANCHORS.est_pos_p95_lo, C.ANCHORS.est_pos_p95_hi,
              _detail_value(c3["healthy_pos_error_in_band"])),
             ("occluded\n$|dx|$ p95", C.ANCHORS.occ_pos_p95_lo, C.ANCHORS.occ_pos_p95_hi,
              _detail_value(c3["occluded_pos_error_in_band"]))]
    for i, (lbl, blo, bhi, val) in enumerate(bands):
        a.add_patch(plt.Rectangle((i - 0.3, blo), 0.6, bhi - blo,
                                  color="#2ca02c", alpha=0.2))
        if val is not None:
            a.plot([i], [val], "o", color="#d62728", ms=8)
            a.annotate(f"{val:.3f}", (i, val), textcoords="offset points",
                       xytext=(8, 0), fontsize=6.5)
    a.set_xticks([0, 1])
    a.set_xticklabels([b[0] for b in bands])
    a.set_xlim(-0.6, 1.6)
    a.set_ylabel("position error (m)")
    a.set_yscale("log")
    a.set_title("C. estimator envelopes")
    a.legend(handles=[Line2D([], [], color="#2ca02c", lw=6, alpha=0.4,
                             label="hardware band"),
                      Line2D([], [], marker="o", ls="", color="#d62728",
                             label="sim")], loc="upper left", fontsize=6.2)

    fig.suptitle("Fig 1  Hardware anchoring: the simulation is held to the measured "
                 "envelopes before any claim is made", fontsize=9)
    fig.savefig(f"{FIG}/fig1_anchoring.png", bbox_inches="tight")
    plt.close(fig)
    print("  fig1_anchoring.png")


# ==========================================================================
def fig_methods(s6):
    """Main comparison + paired effects + seed-level points."""
    tab, rows = s6["table"], s6["rows"]
    conds = s6["conditions"]
    meths = s6["methods"]

    fig = plt.figure(figsize=(10.5, 6.2))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1.0])

    # -- (a) RMSE bars by condition x method --
    ax = fig.add_subplot(gs[0, :2])
    w = 0.13
    for j, m in enumerate(meths):
        xs, ys, es = [], [], []
        for i, c in enumerate(conds):
            t = tab.get(f"{c}|{m}")
            if not t:
                continue
            xs.append(i + (j - len(meths) / 2 + 0.5) * w)
            ys.append(t["rmse_pos"]["mean"])
            es.append(t["rmse_pos"]["sd"] / max(np.sqrt(t["rmse_pos"]["n"]), 1))
        ax.bar(xs, ys, w, yerr=es, capsize=2, color=MC[m], label=METHOD_LABEL[m],
               edgecolor="black", linewidth=0.4)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels([COND_LABEL[c] for c in conds])
    ax.set_ylabel("position RMSE (m)")
    ax.set_title("A. tracking error by condition (mean $\\pm$ s.e., "
                 f"{s6['n_test_per_condition']} matched episodes)")
    ax.legend(ncol=2, fontsize=6.5, loc="upper left")

    # -- (b) recovery success --
    ax = fig.add_subplot(gs[0, 2])
    for j, m in enumerate(meths):
        xs, ys = [], []
        for i, c in enumerate(conds):
            t = tab.get(f"{c}|{m}")
            if not t or not t["n_attempted"]:
                continue
            xs.append(i + (j - len(meths) / 2 + 0.5) * w)
            ys.append(t["success_rate"])
        ax.bar(xs, ys, w, color=MC[m], edgecolor="black", linewidth=0.4)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels([COND_LABEL[c] for c in conds], rotation=30, ha="right")
    ax.set_ylabel("recovery success rate")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"B. recovery (tol {s6['recovery_tolerance_m']:.2f} m)")

    # -- (c) paired effects --
    ax = fig.add_subplot(gs[1, :2])
    eff = s6.get("paired_effects", {})
    labels, mus, los, his = [], [], [], []
    for pair in ("full-no_impact", "full-constant_context", "full-adaptive_mpc",
                 "full-zero_context", "full-full_no_check"):
        for c in conds:
            k = f"{pair}|{c}|rmse_pos"
            if k not in eff:
                continue
            st = eff[k]
            labels.append(f"{pair.split('-')[1][:12]} / {c[:6]}")
            mus.append(st["mean"])
            los.append(st["mean"] - st["lo"])
            his.append(st["hi"] - st["mean"])
    y = np.arange(len(labels))
    cols = ["#d62728" if (m + h) < 0 else ("#2ca02c" if (m - l) > 0 else "#7f7f7f")
            for m, l, h in zip(mus, los, his)]
    ax.errorbar(mus, y, xerr=[los, his], fmt="o", ms=3.5, lw=1.0,
                ecolor="#444", ls="none")
    ax.scatter(mus, y, c=cols, s=22, zorder=3)
    ax.axvline(0, color="black", lw=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=5.8)
    ax.invert_yaxis()
    ax.set_xlabel(r"$\Delta$RMSE, full $-$ baseline (m).  negative = full is better")
    ax.set_title("C. paired effects, 95% block bootstrap over parent episodes")

    # -- (d) seed-level --
    ax = fig.add_subplot(gs[1, 2])
    st = s6.get("seed_level_rmse", {})
    off = {"full": 0, "no_impact": 1, "constant_context": 2, "full_no_check": 3}
    for key, vals in st.items():
        m, c = key.split("|")
        if m not in off or c not in conds:
            continue
        x = conds.index(c) + (off[m] - 1.5) * 0.18
        ax.plot([x] * len(vals), vals, "o", color=MC[m], ms=3.5, alpha=0.85)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels([COND_LABEL[c] for c in conds], rotation=30, ha="right")
    ax.set_ylabel("RMSE (m)")
    ax.set_title("D. seed-level (3 training seeds)")

    fig.suptitle("Fig 2  Matched method comparison. All variants share references, "
                 "limits, estimator, timing and scenario draws.", fontsize=9)
    fig.savefig(f"{FIG}/fig2_methods.png", bbox_inches="tight")
    plt.close(fig)
    print("  fig2_methods.png")


# ==========================================================================
def fig_trial(tr, meta):
    """The four aligned panels of protocol Sec 9.2."""
    x = np.array(tr["x_true"])
    xh = np.array(tr["x_hat"])
    rs = np.array(tr["ref_score"])
    t = np.arange(len(x)) * C.TS
    onset = tr["onset"] * C.TS
    e_pos = np.linalg.norm(x[:, :2] - rs[:, :2], axis=1)
    e_yaw = np.abs(np.arctan2(np.sin(x[:, 4] - rs[:, 4]), np.cos(x[:, 4] - rs[:, 4])))

    fig, ax = plt.subplots(4, 1, figsize=(9.0, 8.2), sharex=True)

    # 1. physical error + tolerance
    a = ax[0]
    a.plot(t, e_pos, color="#1f77b4", lw=1.1, label="position error (true)")
    a.plot(t, np.linalg.norm(xh[:, :2] - rs[:, :2], axis=1), color="#1f77b4",
           lw=0.7, alpha=0.45, ls="--", label="position error (estimated)")
    a.axhline(meta["tol"], color="#2ca02c", lw=1.0, ls=":",
              label=f"recovery tolerance {meta['tol']:.2f} m")
    a2 = a.twinx()
    a2.plot(t, np.degrees(e_yaw), color="#ff7f0e", lw=0.8, alpha=0.8)
    a2.set_ylabel("yaw error (deg)", color="#ff7f0e")
    a2.grid(False)
    a.set_ylabel("position error (m)")
    a.set_title("1. physical error against the ORIGINAL task reference")
    a.legend(loc="upper right", fontsize=6.5)

    # 2. ||e||_P vs R, s_cert
    a = ax[1]
    eP = np.array(tr["e_P"], dtype=float)
    a.plot(t, eP, color="#d62728", lw=1.0, label=r"$\|e_k\|_P$")
    a.axhline(meta["R"], color="#2ca02c", lw=1.0, ls="--",
              label=f"eligibility radius R = {meta['R']:.2f}")
    if np.isfinite(meta.get("s_cert", np.nan)):
        a.axhline(meta["s_cert"], color="black", lw=1.0, ls=":",
                  label=f"$s_{{cert}}$ = {meta['s_cert']:.3g}  (ABOVE the plot range "
                        f"=> region empty)")
    a.set_ylabel(r"$\|e_k\|_P$")
    a.set_yscale("log")
    a.set_title("2. supervision coordinates. The certified region is EMPTY at this "
                "authority, so R is an operational radius")
    a.legend(loc="upper right", fontsize=6.5)

    # 3. transmitted-command slack
    a = ax[2]
    sl = np.array(tr["slack_cmd"], dtype=float)
    acc = np.array(tr["accepted"], dtype=bool)
    a.plot(t, sl, color="#444", lw=0.7, label="one-step slack of Eq. (18)")
    a.axhline(0, color="black", lw=0.9)
    rej = ~acc
    if rej.any():
        a.plot(t[rej], np.nan_to_num(sl[rej]), "v", color="#d62728", ms=3.5,
               label=f"rejected, fallback transmitted ({rej.sum()} steps)")
    a.set_ylabel("slack (rhs $-$ lhs)")
    a.set_title("3. acceptance check evaluated at the TRANSMITTED-equivalent wrench")
    a.legend(loc="lower right", fontsize=6.5)

    # 4. duties / events
    a = ax[3]
    dt_on = np.array(tr["pulse_command_s"])
    a.plot(t, dt_on.sum(1) / C.TS, color="#1f77b4", lw=0.8,
           label="total commanded duty / slot")
    a.plot(t, np.array(tr["accel"]), color="#ff7f0e", lw=0.7, alpha=0.8,
           label=r"achieved $|a|$ (m/s$^2$)")
    g = np.array(tr["gate"], dtype=int)
    a.fill_between(t, 0, 1, where=(g == 0), color="#d62728", alpha=0.10,
                   transform=a.get_xaxis_transform(), label="ineligible")
    fs = np.array(tr["fault_skip"], dtype=bool)
    pv = ~np.array(tr["pose_valid"], dtype=bool)
    a.fill_between(t, 0, 1, where=fs, color="#8c564b", alpha=0.16,
                   transform=a.get_xaxis_transform(), label="thruster pulse skipped")
    a.fill_between(t, 0, 1, where=pv, color="#9467bd", alpha=0.16,
                   transform=a.get_xaxis_transform(), label="pose dropout")
    a.set_ylabel("duty / accel")
    a.set_xlabel("time (s)")
    a.set_title("4. actuation, fault and perception events")
    a.legend(loc="upper right", ncol=2, fontsize=6.5)

    for a in ax:
        a.axvline(onset, color="black", lw=1.1, ls="-.", alpha=0.7)
    ax[0].annotate("fault / degradation onset", xy=(onset, ax[0].get_ylim()[1]),
                   xytext=(6, -9), textcoords="offset points", fontsize=6.5)

    fig.suptitle("Fig 3  Representative combined-fault trial (prespecified: nearest "
                 f"median RMSE among complete full-method trials; RMSE "
                 f"{meta['rmse']:.3f} m)", fontsize=9)
    fig.savefig(f"{FIG}/fig3_trial.png", bbox_inches="tight")
    plt.close(fig)
    print("  fig3_trial.png")


# ==========================================================================
def fig_certificate(s7):
    rows = s7["sweep"]
    fig, ax = plt.subplots(1, 3, figsize=(10.2, 2.9))

    # (a) contraction vs parameter tolerance
    a = ax[0]
    for fam, col in (("step", "#1f77b4"), ("smooth", "#d62728")):
        spans = sorted({r["param_span"] for r in rows if r["family"] == fam})
        best = [min(r["lam"] for r in rows
                    if r["family"] == fam and r["param_span"] == s) for s in spans]
        a.plot([s * 100 for s in spans], best, "o-", color=col, ms=4,
               label=f"{fam} reference")
    a.axhline(1.0, color="black", lw=1.0, ls="--", label=r"$\lambda = 1$")
    a.set_xlabel("mass / inertia tolerance (%)")
    a.set_ylabel(r"best achievable $\gamma+\nu$")
    a.set_title("A. contraction vs plant tolerance\n(Sec 14 OPEN item)")
    a.legend(fontsize=6.5)

    # (b) best achievable s_cert/R over the duty axis, both families, plus the
    #     maximum-authority corner. The MINIMUM over designs and tolerances is the
    #     quantity that decides emptiness, so a scatter of all cells hides it.
    a = ax[1]
    for fam, col in (("step", "#1f77b4"), ("smooth", "#d62728")):
        sub = [r for r in rows if r["family"] == fam and r["lam"] < 1.0
               and r["fmax"] == C.FMAX_PER_THRUSTER
               and r["duty_offset"] == C.FIT_OFFSET]
        duties = sorted({r["duty_ceiling"] for r in sub})
        best = [min(r["ratio"] for r in sub if r["duty_ceiling"] == d)
                for d in duties]
        a.plot(duties, best, "o-", color=col, ms=4, label=f"{fam}, hw thrusters")
        corner = [r for r in rows if r["family"] == fam and r["lam"] < 1.0
                  and r["duty_ceiling"] == 1.0 and r["fmax"] == 4.0
                  and r["duty_offset"] == 0.0]
        if corner:
            a.plot([1.0], [min(r["ratio"] for r in corner)], "*", color=col, ms=13,
                   mec="black", mew=0.5,
                   label=f"{fam}, max authority corner")
    a.axhspan(0, 1.0, color="#2ca02c", alpha=0.16)
    a.axhline(1.0, color="#2ca02c", lw=1.3, ls="--",
              label=r"$s_{cert}=R$: NONEMPTY below")
    a.axvline(0.40, color="black", ls=":", lw=1.0)
    a.set_yscale("log")
    a.set_ylim(0.5, 1e3)
    a.annotate("hardware duty 0.40", xy=(0.41, 0.62), fontsize=6, ha="left")
    a.set_xlabel("duty ceiling")
    a.set_ylabel(r"best achievable $s_{cert}/R_{max}$")
    a.set_title("B. distance to a nonempty region")
    a.legend(fontsize=5.8, loc="upper center", ncol=2)

    # (c) which term binds
    a = ax[2]
    labs, vals = [], []
    for fam in ("step", "smooth"):
        sub = [r for r in rows if r["family"] == fam and r["lam"] < 1.0]
        if not sub:
            continue
        b = min(sub, key=lambda r: r["ratio"])
        for k, lbl in (("b_r", "$b_r$"), ("d_cert", "$d_{cert}$"),
                       ("eta", r"$\eta$")):
            labs.append(f"{fam}\n{lbl}")
            vals.append(b[k])
    a.bar(range(len(vals)), vals, color=["#d62728", "#1f77b4", "#ff7f0e"] * 2,
          edgecolor="black", linewidth=0.4)
    a.set_xticks(range(len(labs)))
    a.set_xticklabels(labs, fontsize=6)
    a.set_yscale("log")
    a.set_ylabel("term magnitude (P norm)")
    a.set_title("C. which term binds")

    fig.suptitle("Fig 4  Recovery certificate: the boundary in authority and plant "
                 "tolerance, and the binding term", fontsize=9)
    fig.savefig(f"{FIG}/fig4_certificate.png", bbox_inches="tight")
    plt.close(fig)
    print("  fig4_certificate.png")


# ==========================================================================
def fig_check(s6):
    """The post-allocation acceptance check is load-bearing.

    Two independent readings of the same mechanism: the calibration-split eta curve
    (how hard the check is enforced) and the test-split full vs full_no_check contrast.
    """
    cal = s6.get("calibration", {})
    curve = cal.get("eta_curve")
    if not curve:
        return
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 2.8))

    a = ax[0]
    eta = [c["eta"] for c in curve]
    rm = [c["rmse"] for c in curve]
    rj = [c["frac_reject"] for c in curve]
    a.plot(eta, rm, "o-", color="#d62728", ms=5, label="calibration RMSE")
    a.set_xlabel(r"acceptance allowance $\eta$  (larger = more permissive)")
    a.set_ylabel("position RMSE (m)", color="#d62728")
    sel = cal.get("eta")
    if sel is not None:
        a.axvline(sel, color="black", ls=":", lw=1.0)
        a.annotate(f"selected $\\eta$={sel:g}", xy=(sel, max(rm)),
                   xytext=(6, -4), textcoords="offset points", fontsize=6.5)
    a2 = a.twinx()
    a2.plot(eta, rj, "s--", color="#1f77b4", ms=4, label="rejected fraction")
    a2.set_ylabel("rejected fraction", color="#1f77b4")
    a2.grid(False)
    ec = cal.get("eta_conformal")
    if ec is not None:
        a.annotate(f"conformal $\\delta$=0.025\nwould give $\\eta$={ec:.2f}\n"
                   f"(near-inert)", xy=(ec, min(rm) + 0.55 * (max(rm) - min(rm))),
                   xytext=(-58, 0), textcoords="offset points", fontsize=6,
                   ha="left", arrowprops=dict(arrowstyle="->", lw=0.7))
    a.set_title("A. enforcing the check harder monotonically\nimproves tracking")

    # -- test-split contrast --
    a = ax[1]
    tab = s6["table"]
    conds = s6["conditions"]
    w = 0.36
    for j, m in enumerate(("full", "full_no_check")):
        xs = [i + (j - 0.5) * w for i in range(len(conds))]
        ys = [tab[f"{c}|{m}"]["rmse_pos"]["mean"] for c in conds]
        es = [tab[f"{c}|{m}"]["rmse_pos"]["sd"] /
              max(np.sqrt(tab[f"{c}|{m}"]["rmse_pos"]["n"]), 1) for c in conds]
        a.bar(xs, ys, w, yerr=es, capsize=3, color=MC[m], label=METHOD_LABEL[m],
              edgecolor="black", linewidth=0.4)
    a.set_xticks(range(len(conds)))
    a.set_xticklabels([COND_LABEL[c] for c in conds], rotation=20, ha="right")
    a.set_ylabel("position RMSE (m)")
    a.set_title("B. test split: same checkpoint,\ncheck enforced vs bypassed")
    a.legend(fontsize=6.5)

    fig.suptitle("Fig 6  The post-allocation acceptance check (Eq. 18) is "
                 "load-bearing", fontsize=9)
    fig.savefig(f"{FIG}/fig6_check.png", bbox_inches="tight")
    plt.close(fig)
    print("  fig6_check.png")


def fig_horizon(s8):
    if not s8:
        return
    tab = s8["horizon"]["table"]
    Ns = sorted({int(k.split("|")[1]) for k in tab})
    fig, ax = plt.subplots(1, 3, figsize=(9.6, 2.7))
    for cond, col in (("healthy", "#1f77b4"), ("combined", "#d62728")):
        for j, (key, lbl) in enumerate((("rmse_pos", "position RMSE (m)"),
                                        ("frac_reject", "rejected fraction"),
                                        ("ms_per_step", "wall ms / step"))):
            ys = [tab[f"{cond}|{N}"][key]["mean"] for N in Ns]
            es = [tab[f"{cond}|{N}"][key]["sd"] for N in Ns]
            ax[j].errorbar(Ns, ys, yerr=es, fmt="o-", ms=4, color=col,
                           capsize=2, label=cond)
            ax[j].set_xlabel("MPC horizon $N$")
            ax[j].set_ylabel(lbl)
    ax[0].axvline(C.N_HORIZON_HW, color="black", ls=":", lw=1.0)
    ax[0].annotate("hardware $N{=}12$", xy=(C.N_HORIZON_HW, ax[0].get_ylim()[1]),
                   xytext=(4, -10), textcoords="offset points", fontsize=6.5)
    ax[2].axhline(C.TS * 1e3, color="#2ca02c", ls="--", lw=1.0,
                  label=f"{C.TS*1e3:.0f} ms slot")
    ax[0].legend(fontsize=7)
    ax[2].legend(fontsize=7)
    fig.suptitle("Fig 5  Horizon axis, measured in closed loop. N does not enter the "
                 "certificate algebraically.", fontsize=9)
    fig.savefig(f"{FIG}/fig5_horizon.png", bbox_inches="tight")
    plt.close(fig)
    print("  fig5_horizon.png")


def fig_ood(s8):
    """In-distribution cost vs out-of-distribution benefit of the behavioural term."""
    if not s8 or not s8.get("ood"):
        return
    tab, eff = s8["ood"]["table"], s8["ood"]["paired_full_minus_no_impact"]
    kinds = sorted({k.split("|")[0] for k in tab})
    conds = [c for c in ("healthy", "actuator", "perception", "combined")
             if any(k.split("|")[1] == c for k in tab)]
    methods = ("zero_context", "constant_context", "no_impact", "full")
    cols = {"zero_context": "#7f7f7f", "constant_context": "#ff7f0e",
            "no_impact": "#1f77b4", "full": "#d62728"}

    fig, ax = plt.subplots(1, len(kinds) + 1,
                           figsize=(3.4 * (len(kinds) + 1), 2.9))
    for a, kind in zip(ax, kinds):
        w, xs = 0.2, np.arange(len(conds))
        for i, m in enumerate(methods):
            ys = [tab.get(f"{kind}|{c}|{m}", {}).get("rmse_pos", {}).get("mean",
                                                                        np.nan)
                  for c in conds]
            es = [tab.get(f"{kind}|{c}|{m}", {}).get("rmse_pos", {}).get("sd", 0)
                  for c in conds]
            a.bar(xs + (i - 1.5) * w, ys, w, yerr=es, capsize=1.5,
                  color=cols[m], label=m.replace("_", " "), error_kw=dict(lw=0.7))
        a.set_xticks(xs)
        a.set_xticklabels(conds, fontsize=7, rotation=20)
        a.set_ylabel("position RMSE (m)")
        a.set_title(f"stress: {kind}", fontsize=8)
    ax[0].legend(fontsize=6, ncol=2)

    # paired effect: in-distribution (Stage 6) alongside the stress cells
    a = ax[-1]
    labels, mu, lo, hi = [], [], [], []
    for k, st in eff.items():
        kind, c = k.split("|")
        labels.append(f"{kind}\n{c}")
        mu.append(st["mean"])
        lo.append(st["mean"] - st["lo"])
        hi.append(st["hi"] - st["mean"])
    y = np.arange(len(labels))
    a.errorbar(mu, y, xerr=[lo, hi], fmt="o", ms=4, color="#d62728", capsize=2)
    a.axvline(0.0, color="black", lw=0.8)
    a.set_yticks(y)
    a.set_yticklabels(labels, fontsize=6.5)
    a.set_xlabel(r"$\Delta$RMSE, full $-$ no_impact (m)")
    a.set_title("paired effect, negative = supervision helps", fontsize=8)
    fig.suptitle("Fig 7  Behavioural supervision under distribution shift. Stress "
                 "cells are never pooled with the calibrated population.", fontsize=9)
    fig.savefig(f"{FIG}/fig7_ood.png", bbox_inches="tight")
    plt.close(fig)
    print("  fig7_ood.png")


def representative_trial(s6, cert_eta, cert_R, tol):
    """Prespecified: full-method combined-fault trial nearest the MEDIAN RMSE."""
    import stage6_methods as s6m
    from scsim import config as Cc

    sub = [r for r in s6["rows"] if r["method"] == "full"
           and r["condition"] == "combined" and r["n_steps"] == Cc.EPISODE_STEPS]
    if not sub:
        return None
    med = float(np.median([r["rmse_pos"] for r in sub]))
    pick = min(sub, key=lambda r: abs(r["rmse_pos"] - med))
    print(f"  representative trial: ep_seed={pick['ep_seed']} "
          f"model_seed={pick['model_seed']} RMSE={pick['rmse_pos']:.4f} "
          f"(median {med:.4f})")
    cert = s6m.certificate_design()
    cert.update(eta=cert_eta, R=cert_R)
    m = s6m._job(("full", pick["model_seed"], "combined", pick["ep_seed"], cert,
                  tol, Cc.N_HORIZON_HW, True))
    return m["_trace"], {"tol": tol, "R": cert_R, "rmse": m["rmse_pos"],
                         "s_cert": s6["supervision_design"].get("s_cert", np.nan)}


def main():
    s1, s2 = load("stage1_openloop.json"), load("stage2_anchor.json")
    s3 = load("stage3_estimator.json")
    s6, s7, s8 = (load("stage6_methods.json"), load("stage7_certificate.json"),
                  load("stage8_horizon.json"))
    print("figures:")
    if s2 and s3:
        fig_anchoring(s1, s2, s3)
    if s6:
        fig_methods(s6)
        fig_check(s6)
        sd = s6["supervision_design"]
        got = representative_trial(s6, sd["eta"], sd["R"],
                                   s6["recovery_tolerance_m"])
        if got:
            fig_trial(*got)
    if s7:
        fig_certificate(s7)
    if s8:
        fig_horizon(s8)
        fig_ood(s8)
    print(f"\nwrote figures to {FIG}/")


if __name__ == "__main__":
    main()

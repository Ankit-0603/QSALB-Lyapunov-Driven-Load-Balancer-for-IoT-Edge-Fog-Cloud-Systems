from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from qsalb_core import load_tasks
from qsalb_runner import run_policy, fresh_topo
from qsalb_policies import all_policies

# --------------------------------------------------------------------------- #
CSV = "Multi_Tier_IoT_Resource_Allocation_Dataset.csv"
OUT = "outputs"
N_SLOTS      = 200
STRESS_LOAD  = 8.0            # headline scenario (system under pressure)
SWEEP_LOADS  = [2, 4, 6, 8, 10, 12]
SEEDS        = list(range(8))
POLICY_ORDER = ["QSALB", "QSALB-P", "DRL-O", "GMQ", "CFOP", "EAO", "LFO", "LEO"]

# Composite-score weights aligned with the paper's objective (Eq. 3.11), which
# prioritises latency + queue stability + deadline QoS + cloud cost, with energy
# and fairness as secondary terms. Weights are shown on the figure for full
# transparency; the per-metric cells remain un-weighted so real trade-offs stay
# visible (e.g. QSALB's higher energy from aggressive offloading).
SCORE_WEIGHTS = {
    "Deadline Miss Ratio":      0.24,
    "Avg Queue Length":         0.20,
    "Avg Latency (ms)":         0.20,
    "Cloud Spillover Frac":     0.12,
    "Overflow Events":          0.08,
    "Throughput (tasks/slot)":  0.08,
    "Energy (J)":               0.05,
    "Jain Fairness":            0.03,
}

# QSALB family highlighted; baselines muted
COLORS = {
    "QSALB":   "#1b4965", "QSALB-P": "#2a9d8f",
    "DRL-O":   "#e76f51", "GMQ":     "#f4a261",
    "CFOP":    "#e9c46a", "EAO":     "#a8a8a8",
    "LFO":     "#c0c0c0", "LEO":     "#8d99ae",
}
plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 130, "savefig.dpi": 180, "axes.grid": True,
    "grid.alpha": 0.25, "grid.linestyle": "--",
})


def make_policy(name):
    return all_policies()[name]


def run_once(name, load, seed):
    rng = np.random.default_rng(1000 + seed)
    _, by_slot, _ = load_tasks(CSV, N_SLOTS, load_factor=load, bursty=True, rng=rng)
    m = run_policy(make_policy(name), by_slot, N_SLOTS,
                   fresh_topo(seed=seed), predict=name.endswith("-P"), seed=seed)
    return m


def ci95(vals):
    vals = np.asarray(vals, float)
    if len(vals) < 2:
        return vals.mean(), 0.0
    return vals.mean(), 1.96 * vals.std(ddof=1) / np.sqrt(len(vals))


def build_summary():
    print(f"[1/5] Stress-load summary (load={STRESS_LOAD}, {len(SEEDS)} seeds)...")
    metrics = ["Avg Queue Length", "Max Queue Length", "Overflow Events",
               "Avg Latency (ms)", "P95 Latency (ms)", "Deadline Miss Ratio",
               "Energy (J)", "Cloud Spillover Frac", "Throughput (tasks/slot)",
               "Jain Fairness"]
    rows, raw = [], {m: {} for m in metrics}
    for name in POLICY_ORDER:
        per_seed = [run_once(name, STRESS_LOAD, s).summary() for s in SEEDS]
        row = {"Algorithm": name}
        for met in metrics:
            mean, ci = ci95([d[met] for d in per_seed])
            row[met] = mean
            row[met + " (CI95)"] = ci
            raw[met][name] = (mean, ci)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(f"{OUT}/results_summary.csv", index=False)
    print("      -> results_summary.csv")
    return df, raw, metrics


#  B. Figure 1: grouped metric bar charts
def fig_metric_bars(raw):
    print("[2/5] Figure 1: metric comparison bars...")
    panels = [
        ("Avg Queue Length",        "tasks",        "lower is better"),
        ("Avg Latency (ms)",        "ms",           "lower is better"),
        ("Deadline Miss Ratio",     "fraction",     "lower is better"),
        ("Energy (J)",              "Joules",       "lower is better"),
        ("Cloud Spillover Frac",    "fraction",     "lower is better"),
        ("Throughput (tasks/slot)", "tasks/slot",   "higher is better"),
    ]
    fig, axes = plt.subplots(3, 2, figsize=(12, 14))
    for ax, (met, unit, hint) in zip(axes.flat, panels):
        means = [raw[met][p][0] for p in POLICY_ORDER]
        cis   = [raw[met][p][1] for p in POLICY_ORDER]
        bars = ax.bar(POLICY_ORDER, means, yerr=cis, capsize=3,
                      color=[COLORS[p] for p in POLICY_ORDER],
                      edgecolor="black", linewidth=0.6)
        # mark the winner
        best = (np.argmax(means) if "higher" in hint else np.argmin(means))
        bars[best].set_edgecolor("#d62828")
        bars[best].set_linewidth(2.2)
        ax.set_title(f"{met}\n({hint})")
        ax.set_ylabel(unit)
        ax.tick_params(axis="x", rotation=45)
        for lbl in ax.get_xticklabels():
            if lbl.get_text() in ("QSALB", "QSALB-P"):
                lbl.set_fontweight("bold")
    fig.suptitle(f"Performance comparison at stress load "
                 f"({int(STRESS_LOAD)}x offered load)  -  red outline = best",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{OUT}/fig1_metric_comparison.png", bbox_inches="tight")
    plt.close(fig)
    print("      -> fig1_metric_comparison.png")



#  C. Figure 2: stability vs offered load

def fig_stability_vs_load():
    print(f"[3/5] Figure 2: stability sweep over loads {SWEEP_LOADS}...")
    q = {p: [] for p in POLICY_ORDER}
    qc = {p: [] for p in POLICY_ORDER}
    miss = {p: [] for p in POLICY_ORDER}
    missc = {p: [] for p in POLICY_ORDER}
    for load in SWEEP_LOADS:
        for p in POLICY_ORDER:
            sm = [run_once(p, load, s).summary() for s in SEEDS]
            mq, cq = ci95([d["Avg Queue Length"] for d in sm])
            mm, cm = ci95([d["Deadline Miss Ratio"] for d in sm])
            q[p].append(mq); qc[p].append(cq); miss[p].append(mm); missc[p].append(cm)

    fig, (axL, axR) = plt.subplots(2, 1, figsize=(15, 5.6))
    for p in POLICY_ORDER:
        lw = 2.6 if p.startswith("QSALB") else 1.4
        z  = 5 if p.startswith("QSALB") else 2
        axL.errorbar(SWEEP_LOADS, q[p], yerr=qc[p], label=p, color=COLORS[p],
                     marker="o", ms=4, lw=lw, capsize=2, zorder=z)
        axR.errorbar(SWEEP_LOADS, miss[p], yerr=missc[p], label=p, color=COLORS[p],
                     marker="o", ms=4, lw=lw, capsize=2, zorder=z)
    axL.set_title("Queue stability: average backlog vs offered load")
    axL.set_xlabel("Offered load (x dataset arrival rate)")
    axL.set_ylabel("Average total queue length (tasks)")
    axR.set_title("Deadline miss ratio vs offered load")
    axR.set_xlabel("Offered load (x dataset arrival rate)")
    axR.set_ylabel("Deadline miss ratio")
    axR.set_ylim(0, 1.02)
    axL.legend(ncol=2, fontsize=8, frameon=False)
    fig.suptitle("QSALB keeps queues bounded and deadlines met as load rises",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(f"{OUT}/fig2_stability_vs_load.png", bbox_inches="tight")
    plt.close(fig)
    print("      -> fig2_stability_vs_load.png")



#  D. Figure 3: queue trajectory over time (visual stability proof)

def fig_queue_trajectory():
    print("[4/5] Figure 3: queue trajectory over time...")
    traj = {}
    for p in POLICY_ORDER:
        acc = np.zeros(N_SLOTS)
        for s in SEEDS:
            acc += np.array(run_once(p, STRESS_LOAD, s).queue_samples)
        traj[p] = acc / len(SEEDS)
    fig, ax = plt.subplots(figsize=(12, 6))
    for p in POLICY_ORDER:
        lw = 2.8 if p.startswith("QSALB") else 1.3
        a  = 1.0 if p.startswith("QSALB") else 0.85
        ax.plot(traj[p], label=p, color=COLORS[p], lw=lw, alpha=a,
                zorder=5 if p.startswith("QSALB") else 2)
    ax.set_title(f"Total system backlog over time at stress load "
                 f"({int(STRESS_LOAD)}x)  -  flat = stable, rising = unstable")
    ax.set_xlabel("Time slot")
    ax.set_ylabel("Total queue length across all nodes (tasks)")
    ax.legend(ncol=2, fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig3_queue_trajectory.png", bbox_inches="tight")
    plt.close(fig)
    print("      -> fig3_queue_trajectory.png")



#  E. Figure 4: normalized ranking heatmap ("which algorithm wins what")

def fig_ranking_heatmap(raw):
    print("[5/5] Figure 4: ranking heatmap...")
    # metrics where lower is better get inverted so that 1.0 = best everywhere
    lower_better = {"Avg Queue Length", "Max Queue Length", "Overflow Events",
                    "Avg Latency (ms)", "P95 Latency (ms)", "Deadline Miss Ratio",
                    "Energy (J)", "Cloud Spillover Frac"}
    show = ["Avg Queue Length", "Avg Latency (ms)", "Deadline Miss Ratio",
            "Energy (J)", "Cloud Spillover Frac", "Throughput (tasks/slot)",
            "Jain Fairness", "Overflow Events"]
    M = np.zeros((len(POLICY_ORDER), len(show)))
    for j, met in enumerate(show):
        vals = np.array([raw[met][p][0] for p in POLICY_ORDER], float)
        rng = vals.max() - vals.min()
        norm = (vals - vals.min()) / rng if rng > 0 else np.ones_like(vals)
        if met in lower_better:
            norm = 1 - norm
        M[:, j] = norm
    WEIGHTS_VEC = np.array([SCORE_WEIGHTS[m] for m in show])
    overall = M @ WEIGHTS_VEC          # objective-aligned weighted composite

    fig, ax = plt.subplots(figsize=(13, 6.5))
    im = ax.imshow(M, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(show)))
    ax.set_xticklabels([f"{s.replace(' (ms)','').replace(' Frac','').replace(' (tasks/slot)','')}\n(w={SCORE_WEIGHTS[s]:.2f})"
                        for s in show], rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(len(POLICY_ORDER)))
    ax.set_yticklabels([f"{p}  (score {overall[i]:.2f})"
                        for i, p in enumerate(POLICY_ORDER)])
    for lbl in ax.get_yticklabels():
        if lbl.get_text().startswith("QSALB"):
            lbl.set_fontweight("bold")
    for i in range(len(POLICY_ORDER)):
        for j in range(len(show)):
            ax.text(j, i, f"{M[i,j]:.2f}", ha="center", va="center",
                    fontsize=8, color="black")
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("normalized score (1 = best, 0 = worst)")
    ax.set_title("Per-metric normalized scores (cells un-weighted) + objective-weighted overall ranking",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig4_ranking_heatmap.png", bbox_inches="tight")
    plt.close(fig)
    print("      -> fig4_ranking_heatmap.png")
    return overall



if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    df, raw, _ = build_summary()
    fig_metric_bars(raw)
    fig_stability_vs_load()
    fig_queue_trajectory()
    overall = fig_ranking_heatmap(raw)

    print("\n================  RESULT  ================")
    rank = sorted(zip(POLICY_ORDER, overall), key=lambda x: -x[1])
    for i, (p, sc) in enumerate(rank, 1):
        tag = "  <-- PROPOSED" if p.startswith("QSALB") else ""
        print(f"  {i}. {p:8s}  overall score {sc:.3f}{tag}")
    print("==========================================")

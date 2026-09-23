"""
qsalb_weight_search.py
======================
Hyperparameter search for the four QSALB weights (ALPHA, BETA, GAMMA, KAPPA).

WHAT IT DOES
------------
1. Loads all 1000 tasks from your dataset.
2. Tries N random combinations of the four weights.
3. Runs QSALB on the full 1000 tasks for each combination.
4. Records for each: deadline-miss ratio, average latency, average queue
   length, cloud spillover fraction.
5. Ranks the combinations by a "goodness score" that prioritises deadlines
   and stability (matching your paper's objective).
6. Prints the top 10 combinations.
7. Saves every trial to weight_search_results.csv.
8. Saves a scatter-plot figure weight_search_plot.png that visually shows
   which weight regions are best.

WHY
---
Just choosing weights like (1.0, 0.6, 8.0, 2.5) without evidence is a
weakness. This script gives you a defensible answer:
    "I searched N combinations and picked the one that minimised deadline
     misses on my dataset."

HOW TO RUN
----------
    python qsalb_weight_search.py                  (default: 100 trials)
    python qsalb_weight_search.py 200              (200 trials, slower)
    python qsalb_weight_search.py 50 grid          (grid search, 81 combos)

The script is fully self-contained: it does NOT import from your other
qsalb_*.py files, so it will not affect anything else in your project.
"""

import sys
import math
import random
import pandas as pd
import matplotlib
matplotlib.use("Agg")             # allow saving figures without a display
import matplotlib.pyplot as plt

CSV_IN  = "Multi_Tier_IoT_Resource_Allocation_Dataset.csv"
CSV_OUT = "weight_search_results.csv"
FIG_OUT = "weight_search_plot.png"


# ═════════════════════════════════════════════════════════════════════════════
#  PART 1 - THE FOUR-LAYER NETWORK  (identical to qsalb_decision.py)
# ═════════════════════════════════════════════════════════════════════════════

def build_network():
    nodes = []
    for i in range(20):
        nodes.append({"name": f"IoT{i+1}", "layer": "IoT",
                      "speed": 1.0, "mu_max": 1, "q_max": 12,
                      "queue": 0, "energy": 1000.0, "is_battery": True})
    for i in range(8):
        nodes.append({"name": f"Edge{i+1}", "layer": "Edge",
                      "speed": 2.5, "mu_max": 3, "q_max": 40,
                      "queue": 0, "energy": 8000.0, "is_battery": True})
    for i in range(3):
        nodes.append({"name": f"Fog{i+1}", "layer": "Fog",
                      "speed": 5.0, "mu_max": 8, "q_max": 120,
                      "queue": 0, "energy": math.inf, "is_battery": False})
    nodes.append({"name": "Cloud1", "layer": "Cloud",
                  "speed": 10.0, "mu_max": 30, "q_max": 100000,
                  "queue": 0, "energy": math.inf, "is_battery": False})
    return nodes


LINK_LATENCY = {
    ("IoT","IoT"):0.0, ("IoT","Edge"):8.0, ("IoT","Fog"):30.0, ("IoT","Cloud"):70.0,
    ("Edge","Edge"):4.0, ("Edge","Fog"):18.0, ("Edge","Cloud"):60.0,
    ("Fog","Fog"):6.0,  ("Fog","Cloud"):55.0,
}

def get_link_latency(src_layer, dst_layer):
    return LINK_LATENCY.get((src_layer, dst_layer),
           LINK_LATENCY.get((dst_layer, src_layer), 40.0))


DEADLINE_MS = {
    "Video Processing": 120.0, "Network Traffic": 150.0,
    "Image Processing": 300.0, "Data Analytics":  500.0,
}


# ═════════════════════════════════════════════════════════════════════════════
#  PART 2 - DELAY & ENERGY FORMULAS
# ═════════════════════════════════════════════════════════════════════════════

def processing_time(node, task):
    return task["exec_ms"] / node["speed"]

def waiting_time(node, task):
    return (node["queue"] / (node["mu_max"] + 0.001)) * processing_time(node, task)

def communication_delay(src_node, dst_node, task):
    if src_node["name"] == dst_node["name"]:
        return 0.0
    return get_link_latency(src_node["layer"], dst_node["layer"]) \
           + task["net_latency"] + task["jitter"]

def total_latency(src_node, dst_node, task):
    return (communication_delay(src_node, dst_node, task)
            + waiting_time(dst_node, task)
            + processing_time(dst_node, task))

def energy_cost(src_node, dst_node, task):
    layer_order = {"IoT":0, "Edge":1, "Fog":2, "Cloud":3}
    if src_node["name"] == dst_node["name"]:
        hops = 0
    else:
        hops = max(1, abs(layer_order[dst_node["layer"]] - layer_order[src_node["layer"]]))
    e_tx   = 0.55  * task["size_mb"] * hops if hops > 0 else 0.0
    e_proc = 0.012 * processing_time(dst_node, task) if dst_node["is_battery"] else 0.0
    return e_tx + e_proc

def is_feasible(node):
    if node["queue"] >= node["q_max"]:
        return False
    if node["is_battery"] and node["energy"] <= 50.0:
        return False
    return True


# ═════════════════════════════════════════════════════════════════════════════
#  PART 3 - QSALB DECISION (parameterised by weights)
# ═════════════════════════════════════════════════════════════════════════════
# NOTE: the four weights (alpha, beta, gamma, kappa) are PASSED IN here so
# we can try different values. This is the whole point of the search.

def qsalb_decide(nodes, src_index, task, alpha, beta, gamma, kappa):
    src_node = nodes[src_index]

    candidates = [src_index]
    candidates += [i for i, n in enumerate(nodes) if n["layer"] == "Edge"]
    candidates += [i for i, n in enumerate(nodes) if n["layer"] == "Fog"]
    candidates += [i for i, n in enumerate(nodes) if n["layer"] == "Cloud"]

    best_score = math.inf
    best_index = src_index

    for j in candidates:
        dst_node = nodes[j]
        if not is_feasible(dst_node):
            continue

        drift   = dst_node["queue"] - src_node["queue"]
        latency = total_latency(src_node, dst_node, task)
        energy  = energy_cost(src_node, dst_node, task)
        cloud   = 1.0 if dst_node["layer"] == "Cloud" else 0.0

        # THE FORMULA (Eq. 3.11/4.10) with tunable weights:
        score = kappa*drift + alpha*latency + beta*energy + gamma*cloud

        if score < best_score:
            best_score = score
            best_index = j

    return best_index


# ═════════════════════════════════════════════════════════════════════════════
#  PART 4 - RUN ONE TRIAL (a full pass over the 1000 tasks with given weights)
# ═════════════════════════════════════════════════════════════════════════════

def run_trial(alpha, beta, gamma, kappa, tasks_precomputed):
    """
    Run QSALB on all 1000 tasks with the given weights.
    Returns a dict of metrics measured for this trial.
    """
    nodes = build_network()          # fresh network for each trial
    tier_counts = {"IoT": 0, "Edge": 0, "Fog": 0, "Cloud": 0}
    deadlines_met = 0
    total_latency_sum = 0.0
    queue_samples = []
    cloud_tasks = 0
    n_tasks = len(tasks_precomputed)

    for idx, task in enumerate(tasks_precomputed):
        src_index = task["src_index"]

        # Ask QSALB where to send the task
        dst_index = qsalb_decide(nodes, src_index, task, alpha, beta, gamma, kappa)
        src_node = nodes[src_index]
        dst_node = nodes[dst_index]

        # Measure this task's outcome
        proc = processing_time(dst_node, task)
        comm = communication_delay(src_node, dst_node, task)
        wait = waiting_time(dst_node, task)
        total = proc + comm + wait
        met = total <= task["deadline"]

        tier_counts[dst_node["layer"]] += 1
        if met:
            deadlines_met += 1
        if dst_node["layer"] == "Cloud":
            cloud_tasks += 1
        total_latency_sum += total

        # Enqueue at destination (so later decisions see realistic congestion)
        if dst_node["queue"] < dst_node["q_max"]:
            dst_node["queue"] += 1

        # Periodic service and queue sampling every 20 tasks
        if (idx + 1) % 20 == 0:
            total_q = sum(n["queue"] for n in nodes)
            queue_samples.append(total_q)
            for n in nodes:
                n["queue"] = max(n["queue"] - n["mu_max"], 0)

    avg_queue = (sum(queue_samples) / len(queue_samples)) if queue_samples else 0.0

    return {
        "deadline_miss_ratio": (n_tasks - deadlines_met) / n_tasks,
        "avg_latency_ms":      total_latency_sum / n_tasks,
        "avg_queue_length":    avg_queue,
        "cloud_spillover":     cloud_tasks / n_tasks,
        "iot_pct":  100 * tier_counts["IoT"]  / n_tasks,
        "edge_pct": 100 * tier_counts["Edge"] / n_tasks,
        "fog_pct":  100 * tier_counts["Fog"]  / n_tasks,
        "cloud_pct": 100 * tier_counts["Cloud"] / n_tasks,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  PART 5 - THE GOODNESS SCORE (how we rank combinations)
# ═════════════════════════════════════════════════════════════════════════════
# A lower score = better. We weight what your paper prioritises.
#   Deadline miss: heavy weight (real-time IoT MUST meet deadlines)
#   Queue length : heavy weight (paper's stability guarantee)
#   Latency      : moderate
#   Cloud usage  : light (cost)

def goodness_score(metrics):
    return (2.0 * metrics["deadline_miss_ratio"]
          + 0.02 * metrics["avg_queue_length"]
          + 0.005 * metrics["avg_latency_ms"]
          + 0.5 * metrics["cloud_spillover"])


# ═════════════════════════════════════════════════════════════════════════════
#  PART 6 - LOAD DATASET ONCE (avoid re-reading 100 times)
# ═════════════════════════════════════════════════════════════════════════════

def load_tasks_once():
    df = pd.read_csv(CSV_IN)
    print(f"Loaded {len(df)} tasks from {CSV_IN}")

    dev_ids = sorted(df["Device_ID"].unique(), key=lambda x: int(x[1:]))
    dev_to_index = {d: i for i, d in enumerate(dev_ids)}

    tasks = []
    for _, row in df.iterrows():
        tasks.append({
            "device":      row["Device_ID"],
            "src_index":   dev_to_index[row["Device_ID"]],
            "workload":    row["Workload_Type"],
            "exec_ms":     float(row["Task_Execution_Time(ms)"]),
            "size_mb":     float(row["Memory_Usage(MB)"]) / 1024.0,
            "net_latency": float(row["Network_Latency(ms)"]),
            "jitter":      float(row["Jitter(ms)"]),
            "deadline":    DEADLINE_MS.get(row["Workload_Type"], 300.0),
        })
    return tasks


# ═════════════════════════════════════════════════════════════════════════════
#  PART 7 - GENERATE WEIGHT COMBINATIONS
# ═════════════════════════════════════════════════════════════════════════════

def random_combinations(n_trials, rng):
    """Sample n_trials random combinations from sensible ranges."""
    combos = []
    for _ in range(n_trials):
        alpha = round(rng.uniform(0.1, 3.0),  2)   # latency weight
        beta  = round(rng.uniform(0.1, 2.0),  2)   # energy weight
        gamma = round(rng.uniform(1.0, 15.0), 2)   # cloud cost weight (bigger)
        kappa = round(rng.uniform(0.5, 6.0),  2)   # congestion weight
        combos.append((alpha, beta, gamma, kappa))
    return combos

def grid_combinations():
    """Systematic 3x3x3x3 = 81 combinations."""
    alphas = [0.5, 1.0, 2.0]
    betas  = [0.3, 0.6, 1.0]
    gammas = [4.0, 8.0, 12.0]
    kappas = [1.0, 2.5, 5.0]
    return [(a, b, g, k) for a in alphas for b in betas
                        for g in gammas for k in kappas]


# ═════════════════════════════════════════════════════════════════════════════
#  PART 8 - PLOTTING THE RESULTS
# ═════════════════════════════════════════════════════════════════════════════

def make_plot(all_results):
    """Four scatter plots: each weight vs the goodness score."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    weight_names = [("alpha", "ALPHA (latency)"),
                    ("beta",  "BETA (energy)"),
                    ("gamma", "GAMMA (cloud cost)"),
                    ("kappa", "KAPPA (congestion)")]

    for ax, (key, label) in zip(axes.flat, weight_names):
        xs = [r[key]        for r in all_results]
        ys = [r["goodness"] for r in all_results]
        ax.scatter(xs, ys, alpha=0.5, s=30, c="#2a9d8f", edgecolors="black", linewidths=0.4)
        # Highlight the best 5 combinations in red
        top5 = sorted(all_results, key=lambda r: r["goodness"])[:5]
        ax.scatter([r[key] for r in top5], [r["goodness"] for r in top5],
                   s=90, c="#d62828", edgecolors="black", linewidths=1.0, zorder=5,
                   label="Top-5 combinations")
        ax.set_xlabel(label)
        ax.set_ylabel("Goodness score (lower is better)")
        ax.set_title(f"{label}  vs  goodness")
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(loc="upper right", fontsize=9)

    fig.suptitle("QSALB weight search: how each weight affects performance\n"
                 "(each dot = one trial on all 1000 tasks; red dots = best 5)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(FIG_OUT, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
#  PART 9 - MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    n_trials = 100
    mode = "random"

    if len(sys.argv) > 1:
        try:
            n_trials = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2 and sys.argv[2].lower() == "grid":
        mode = "grid"

    # Load the 1000 tasks once
    tasks = load_tasks_once()

    # Build the list of weight combinations to try
    rng = random.Random(42)              # fixed seed for reproducibility
    if mode == "grid":
        combos = grid_combinations()
        print(f"\nRunning GRID search: {len(combos)} combinations (3x3x3x3)")
    else:
        combos = random_combinations(n_trials, rng)
        print(f"\nRunning RANDOM search: {len(combos)} combinations")
    print(f"Each trial runs QSALB on all {len(tasks)} tasks.\n")

    # Run each trial
    results = []
    for i, (alpha, beta, gamma, kappa) in enumerate(combos):
        metrics = run_trial(alpha, beta, gamma, kappa, tasks)
        score = goodness_score(metrics)
        results.append({
            "trial":    i + 1,
            "alpha":    alpha,
            "beta":     beta,
            "gamma":    gamma,
            "kappa":    kappa,
            "goodness": round(score, 4),
            "deadline_miss_ratio": round(metrics["deadline_miss_ratio"], 4),
            "avg_latency_ms":      round(metrics["avg_latency_ms"], 2),
            "avg_queue_length":    round(metrics["avg_queue_length"], 2),
            "cloud_spillover":     round(metrics["cloud_spillover"], 4),
            "iot_pct":   round(metrics["iot_pct"],  1),
            "edge_pct":  round(metrics["edge_pct"], 1),
            "fog_pct":   round(metrics["fog_pct"],  1),
            "cloud_pct": round(metrics["cloud_pct"],1),
        })
        if (i + 1) % 10 == 0 or (i + 1) == len(combos):
            print(f"  Completed {i+1:>3}/{len(combos)} trials  "
                  f"(best goodness so far: {min(r['goodness'] for r in results):.4f})")

    # Sort by goodness (best first)
    results.sort(key=lambda r: r["goodness"])

    # Save every trial to CSV
    pd.DataFrame(results).to_csv(CSV_OUT, index=False)

    # Make the plot
    make_plot(results)

    # Print the top 10
    print("\n" + "="*100)
    print(f"  TOP 10 WEIGHT COMBINATIONS   (by goodness score, lower is better)")
    print("="*100)
    print(f"{'Rank':>4}  {'ALPHA':>6}  {'BETA':>6}  {'GAMMA':>6}  {'KAPPA':>6}  |  "
          f"{'Goodness':>8}  {'Miss':>6}  {'Latency':>7}  {'Queue':>6}  {'Cloud':>6}")
    print("-"*100)
    for r in results[:10]:
        print(f"{r['trial']:>4}  {r['alpha']:>6.2f}  {r['beta']:>6.2f}  "
              f"{r['gamma']:>6.2f}  {r['kappa']:>6.2f}  |  "
              f"{r['goodness']:>8.4f}  "
              f"{r['deadline_miss_ratio']:>6.3f}  "
              f"{r['avg_latency_ms']:>7.1f}  "
              f"{r['avg_queue_length']:>6.1f}  "
              f"{r['cloud_spillover']:>6.3f}")
    print("="*100)

    # Recommendation
    best = results[0]
    print(f"\n  RECOMMENDED WEIGHTS  (best of {len(results)} trials):")
    print(f"     ALPHA = {best['alpha']}   (latency)")
    print(f"     BETA  = {best['beta']}   (energy)")
    print(f"     GAMMA = {best['gamma']}   (cloud cost)")
    print(f"     KAPPA = {best['kappa']}   (congestion)")
    print(f"\n  With these weights on all {len(tasks)} tasks:")
    print(f"     Deadline miss ratio: {best['deadline_miss_ratio']*100:.1f}%")
    print(f"     Average latency:     {best['avg_latency_ms']:.1f} ms")
    print(f"     Average queue:       {best['avg_queue_length']:.1f} tasks")
    print(f"     Cloud spillover:     {best['cloud_spillover']*100:.1f}%")
    print(f"\n  Tier distribution: IoT {best['iot_pct']}%  |  Edge {best['edge_pct']}%  |  "
          f"Fog {best['fog_pct']}%  |  Cloud {best['cloud_pct']}%")
    print(f"\n  Full results saved to: {CSV_OUT}")
    print(f"  Plot saved to:         {FIG_OUT}\n")


if __name__ == "__main__":
    main()
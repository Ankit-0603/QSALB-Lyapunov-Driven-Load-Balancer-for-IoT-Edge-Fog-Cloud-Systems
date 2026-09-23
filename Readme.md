# QSALB — Lyapunov-Driven Load Balancing for IoT–Edge–Fog–Cloud Systems

A queue-stability-aware load balancer for hierarchical IoT computing, built around a
**Lyapunov drift-plus-penalty** optimization rule. QSALB decides, in real time, where
each IoT task should run — locally, at the edge, at the fog, or in the cloud — so that
system queues stay mathematically bounded even under bursty, heavy traffic, while
jointly minimizing latency, energy, and cloud cost.

This repository contains a from-scratch Python implementation of QSALB and six
baseline offloading strategies, evaluated on a real 1000-task IoT dataset.

> B.Tech final-year project (Information Technology) — not a published paper, but a
> complete, working research implementation with reproducible results.

---

## Why this exists

IoT devices generate bursty, latency-sensitive workloads that can overwhelm
resource-constrained edge nodes. Most existing load balancers optimize short-term
metrics (latency, energy, throughput) but give **no guarantee** that queues won't grow
without bound under sustained or bursty load. QSALB closes that gap: it formulates
task offloading as a Lyapunov optimization problem, which provides a **provable
stability guarantee** — the long-run average queue length stays finite — while still
optimizing delay, energy, and cloud cost.

---

## Results at a glance

Evaluated on 1000 real IoT tasks (20 devices) across a 32-node four-layer network
(IoT → Edge → Fog → Cloud), at 8× stress load, averaged over 8 random seeds:

| Algorithm | Avg Queue Length | Avg Latency (ms) | Deadline Miss Ratio | Cloud Usage | Throughput |
|---|---|---|---|---|---|
| **QSALB**   | **3.6**  | **113**  | **13%** | 20% | 40.0 |
| **QSALB-P** | **3.6**  | **113**  | **13%** | 20% | 40.0 |
| DRL-O   | 8.5   | 132   | 20% | 32% | 39.9 |
| GMQ     | 32.2  | 258   | 35% | 9%  | 39.8 |
| CFOP    | 210.4 | 446   | 68% | 5%  | 38.9 |
| EAO     | 280.3 | 936   | 78% | 0%  | 38.5 |
| LFO     | 353.7 | 498   | 76% | 7%  | 38.1 |
| LEO     | 176.1 | 1708  | 98% | 0%  | 19.8 |

QSALB keeps queues bounded and deadlines met even as offered load scales from 2× to
12× the dataset's natural arrival rate, while every queue-blind baseline diverges
toward instability:

![Queue stability vs offered load](fig2_stability_vs_load.png)

More results and figures are in [`Results`](#results) below.

---

## How it works

Every time slot, QSALB scores each candidate destination node for a task using a
**drift-plus-penalty** rule:

```
score = κ·(congestion) + α·(latency) + β·(energy) + γ·(cloud cost)
```

- **Congestion (drift)** — the queue-length differential between source and
  destination; penalizes sending work to already-busy nodes (backpressure).
- **Latency** — communication delay + queue wait + processing time.
- **Energy** — battery cost of transmission and processing.
- **Cloud cost** — a penalty applied only when the destination is the cloud.

The task is sent to whichever feasible node has the **lowest score**. Minimizing this
combined score every slot provably bounds the Lyapunov drift, which in turn bounds
every queue in the system — regardless of how bursty the traffic is.

An optional **predictive mode (QSALB-P)** forecasts each node's next-slot arrivals and
folds that forecast into the congestion term, letting the scheduler react proactively
to congestion that hasn't happened yet.

---

## Repository structure

```
├── qsalb_core.py           # System model: nodes, tasks, topology, energy, metrics, CSV loader
├── qsalb_policies.py       # QSALB (the algorithm) + 6 baseline decision rules
├── qsalb_runner.py         # Slot-based simulation engine (queue dynamics)
├── qsalb_experiment.py     # Full evaluation pipeline: runs all algorithms, produces figures
├── qsalb_full.py           # Self-contained single-file version of QSALB, for inspection/demo
├── qsalb_task_output.py    # Runs QSALB on the full dataset, outputs a per-task decision CSV
├── qsalb_weight_search.py  # Hyperparameter search over the four objective weights
├── see_decisions.py        # Lightweight CLI to print live per-task routing decisions
├── Multi_Tier_IoT_Resource_Allocation_Dataset.csv   # 1000-task real IoT dataset
├── results_summary.csv     # Final metric table (mean ± 95% CI over 8 seeds)
├── fig1_metric_comparison.png
├── fig2_stability_vs_load.png
├── fig3_queue_trajectory.png
├── fig4_ranking_heatmap.png
└── docs/                   # Full write-up: dataset explanation, code walkthrough, figures explained
```

---

## Getting started

**Requirements:** Python 3.9+, `numpy`, `pandas`, `matplotlib`

```bash
git clone https://github.com/<your-username>/qsalb.git
cd qsalb

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install numpy pandas matplotlib
```

### Run the full evaluation (produces all 4 figures + results table)

```bash
python qsalb_experiment.py
```

Outputs `results_summary.csv` and four PNG figures in the working directory.

### See exactly which task goes where

```bash
python qsalb_full.py 20 details    # first 20 tasks, with full scoring breakdown
python qsalb_task_output.py        # runs all 1000 tasks, saves a decision-by-decision CSV
```

### Search for better objective weights

```bash
python qsalb_weight_search.py 100  # 100 random trials over (α, β, γ, κ)
```

---

## The algorithms compared

| Algorithm | Type | Strategy |
|---|---|---|
| **QSALB** | Proposed | Lyapunov drift-plus-penalty optimization |
| **QSALB-P** | Proposed | QSALB + predictive arrival forecasting |
| LEO | Baseline | Local Execution Only — never offloads |
| GMQ | Baseline | Greedy Minimum-Queue — shortest visible queue |
| LFO | Baseline | Latency-First — minimizes nominal delay, ignores congestion |
| EAO | Baseline | Energy-Aware — minimizes battery cost |
| DRL-O | Baseline | Online Q-learning agent (DQN-style) |
| CFOP | Baseline | Cloud-First Overflow — spills to cloud when edge/fog are congested |

## The network

A simulated 4-layer IoT–Edge–Fog–Cloud topology, sized to match the dataset and
standard literature specifications:

| Layer | Nodes | Relative Speed | Role |
|---|---|---|---|
| IoT   | 20 | ×1  | Task sources; battery-powered, low compute |
| Edge  | 8  | ×2–3 | Nearby micro-servers, peer cooperation |
| Fog   | 3  | ×4–6 | Regional servers, higher capacity |
| Cloud | 1  | ×10 | Effectively unlimited compute, monetary cost |

## The dataset

`Multi_Tier_IoT_Resource_Allocation_Dataset.csv` — 1000 real task records generated by
20 IoT devices, with workload type, CPU/memory usage, network latency, jitter, and
execution time. Deadlines (50–500 ms) are derived per workload type. Six columns drive
the simulation directly (`Device_ID`, `Task_Execution_Time`, `Memory_Usage`,
`Network_Latency`, `Jitter`, `Workload_Type`); the dataset's own tier-placement and
label columns are intentionally excluded, since QSALB determines the placement itself.

---

## Results

**Queue stability under stress (8× load):** QSALB and QSALB-P consistently achieve the
lowest average queue length, latency, and deadline-miss ratio of all eight algorithms.

![Metric comparison](fig1_metric_comparison.png)

**Stability holds continuously over time**, not just on average:

![Queue trajectory over time](fig3_queue_trajectory.png)

**Overall ranking** across all metrics, weighted by the paper's objective priorities:

![Ranking heatmap](fig4_ranking_heatmap.png)

Full methodology, per-figure axis/unit explanations, and a line-by-line code
walkthrough are in the [`docs/`](docs) folder.

---

## Limitations

- This is a **trace-driven simulation**, not a deployment on physical hardware.
- The predictive module uses a simple exponentially-weighted moving average, not a
  deep sequence model (LSTM/GRU), as future work would explore.
- DRL-O is a compact tabular Q-learning surrogate rather than a full deep network —
  sufficient to compare behavior, not a production RL system.
- Node capacities and link latencies are calibrated to published literature ranges,
  not measured from physical devices.

## Future work

- Deploy on a real edge/fog hardware testbed.
- Replace the moving-average predictor with an LSTM/GRU forecaster.
- Add mobility modeling and targeted regional fog-congestion scenarios.
- Federated training of the predictive module across nodes.
- Online/adaptive tuning of the objective weights.
- Extend to large-scale (thousands of devices) and dependent-task (DAG) workflows.

---

## Author

**Ankit Agrawal** — B.Tech Information Technology, Techno International New Town
[LinkedIn](https://www.linkedin.com/in/ankit-agarwal-6a86aa2b8/) ·
[GitHub](https://github.com/Ankit-0603)

Project team: Ankit Agrawal, Sweety Shaw, Baishali Koley, Md. Farhaan Ahmed
Guide: Dr. Kamalesh Karmakar, Dept. of Information Technology

---

## License

This project is shared for academic and portfolio purposes. Feel free to open an issue
or reach out if you'd like to build on it.

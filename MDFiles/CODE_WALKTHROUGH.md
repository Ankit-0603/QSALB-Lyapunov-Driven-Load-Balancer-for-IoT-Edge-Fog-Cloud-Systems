# Complete Code Walkthrough — tied to your CSV and the research paper

*Every important block of all four files, explained in plain English, with:*
- 📄 **Paper** = the equation/section it implements
- 📊 **CSV** = the dataset column(s) it touches

*Legend for the paper symbols you'll see:*
`s_k` = task data size · `c_k` = CPU cycles (compute demand) · `d_k` = deadline ·
`Q` = queue length · `µ` = service rate · `f` = CPU speed · `x_ij` = offload decision ·
`V(t)` = Lyapunov function · `α,φ,ι,χ` = objective weights.

---

# FILE 1 — `qsalb_core.py` (the simulated world)

## 1.1 `class Node` — one machine
```python
@dataclass
class Node:
    nid, name, layer, speed, mu_max, q_max, energy, ..., queue = 0.0
```
A blueprint for a single machine, storing its layer, `speed` (CPU power), `mu_max`
(tasks it finishes per slot), `q_max` (queue capacity), `energy` (battery) and its live
`queue`.
📄 **Paper:** the per-node properties in Sec. 3.1 — "each node `j` has processing capacity
`f_j`, local queue `Q_j`, max service rate `µ_max_j`, energy `E_j`."
📊 **CSV:** not from a column — these are the *machines*, not the tasks. The 20 IoT nodes
correspond to your 20 devices D1–D20.

## 1.2 `build_topology()` — create all machines
```python
# 20 IoT (speed 1), 8 Edge (speed 2-3), 3 Fog (speed 4-6), 1 Cloud (speed 10)
```
Builds the four layers with capacities increasing as you go up.
📄 **Paper:** Sec. 5.1 hardware ranges (Edge 5–10 GFLOPS, Fog 20–50, Cloud 100–500) and
Sec. 3.4 ordering `f_cloud ≫ f_fog ≫ f_edge ≫ f_iot`. The `speed` numbers encode that
ordering.
📊 **CSV:** 20 IoT nodes = your 20 unique `Device_ID` values.

## 1.3 `LINK_LATENCY` + `link_latency()` — network delays between layers
```python
("IoT","Edge"): 8.0, ("Edge","Fog"): 18.0, ("Fog","Cloud"): 55.0, ...
```
The base one-way delay to move a task between layers. IoT→Edge is cheap; Fog→Cloud is
expensive.
📄 **Paper:** the `L_ij` term in the communication model (Eq. 3.2) and the statement
"IoT→Edge low-latency … Fog→Cloud highest latency" (Sec. 3.3).
📊 **CSV:** combined at runtime with your **`Network_Latency(ms)`** and **`Jitter(ms)`**
columns (see `comm_ms` in File 2).

## 1.4 `class Task` + `DEADLINE_MS` — one job
```python
DEADLINE_MS = {"Video Processing":120, "Network Traffic":150,
               "Image Processing":300, "Data Analytics":500}
@dataclass
class Task: tid, src_node, base_exec_ms, size_mb, net_latency_ms, jitter_ms, deadline_ms ...
```
📄 **Paper:** the task model `w_k = (s_k, d_k, c_k)` (Eq. 3.1) — size, deadline, cycles.
📊 **CSV:** the deadline comes from your **`Workload_Type`** column; the other fields come
from the columns mapped below.

## 1.5 `load_tasks()` — turn your CSV into the task stream ⭐
This is where your dataset literally enters the program.
```python
df = pd.read_csv(csv_path)                       # read your CSV
dev_to_node = {d:i for i,d in enumerate(dev_ids)} # D1..D20 -> node 0..19
...
Task(src_node    = dev_to_node[r["Device_ID"]],
     base_exec_ms= r["Task_Execution_Time(ms)"],          # compute demand c_k
     size_mb     = r["Memory_Usage(MB)"]/1024,            # payload s_k
     net_latency_ms = r["Network_Latency(ms)"],           # part of L_ij
     jitter_ms   = r["Jitter(ms)"],                       # part of L_ij
     deadline_ms = DEADLINE_MS[r["Workload_Type"]])       # deadline d_k
```
📄 **Paper:** builds the `w_k=(s_k,d_k,c_k)` tasks (Eq. 3.1) and the arrival process
`A_i(t)` (Sec. 3.2).
📊 **CSV → code mapping (memorise this):**
| CSV column | Task field | Paper symbol |
|---|---|---|
| `Device_ID` | `src_node` | source `i` |
| `Task_Execution_Time(ms)` | `base_exec_ms` | `c_k` (compute) |
| `Memory_Usage(MB)`÷1024 | `size_mb` | `s_k` (data size) |
| `Network_Latency(ms)` | `net_latency_ms` | `L_ij` |
| `Jitter(ms)` | `jitter_ms` | `L_ij` |
| `Workload_Type` | `deadline_ms` | `d_k` |

The `load_factor` (replicate rows) and `bursty` (MMPP-style waves) knobs:
📄 **Paper:** the workload models of Sec. 5.2 — "Poisson baseline, bursty MMPP, trace-driven
arrivals." Your 1000 rows are the trace; load_factor + bursty create the stress scenarios.

## 1.6 Energy functions
```python
E_TX_PER_MB = 0.55; E_PROC_PER_MS = 0.012
transmission_energy(size_mb, hops) = 0.55 * size_mb * hops
processing_energy(exec_ms)        = 0.012 * exec_ms
```
📄 **Paper:** the energy model (Eq. 3.8): `E_i(t+1) = E_i(t) − E_tx − E_proc`. Transmission
energy scales with data size; processing energy scales with compute time.
📊 **CSV:** `size_mb` comes from **`Memory_Usage(MB)`**; `exec_ms` from
**`Task_Execution_Time(ms)`**.

## 1.7 `class Metrics` + `summary()` — the scoreboard
Collects queue samples, latencies, deadline misses, energy, overflow, cloud count, and
computes the final numbers including **Jain's fairness index**:
```python
jain = (sum(load))**2 / (N * sum(load**2))
```
📄 **Paper:** every metric in Sec. 5.4 — average/max queue, overflow, latency, deadline
miss, energy, cloud spillover, throughput, Jain's fairness.
📊 **CSV:** these are *outputs* measured over your 1000 tasks.

---

# FILE 2 — `qsalb_policies.py` (the decision rules / the brain)

## 2.1 The estimator helpers — the paper's delay/energy formulas
```python
proc_ms(node, task)  = task.base_exec_ms / node.speed          # processing time
wait_ms(node, task)  = (node.queue / (node.mu_max+ε)) * proc_ms # waiting time
comm_ms(src,dst,task)= link_latency + task.net_latency_ms + task.jitter_ms  # network
est_latency = comm_ms + wait_ms + proc_ms                       # end-to-end
```
📄 **Paper, line by line:**
- `proc_ms` = `T_proc = c_k / f_j` (Eq. 3.3 / 4.1).
- `wait_ms` = `T_wait = Q_j / (µ_j + ε)` (Eq. 3.4 / 3.7) — note the `ε` "prevents division
  by zero," exactly as the paper says.
- `comm_ms` = `T_comm = s_k/B_ij + L_ij` (Eq. 3.2 / 4.2).
- `est_latency` = the deadline-constraint sum `T_comm + T_wait + T_proc` (Eq. 3.6).
📊 **CSV:** `proc_ms` uses **`Task_Execution_Time`**; `comm_ms` uses **`Network_Latency`**
and **`Jitter`**.

## 2.2 `feasible()` — can this machine accept the task?
```python
if node.queue >= node.q_max: return False     # queue full
if node.is_battery and node.energy <= e_min: return False  # battery too low
```
📄 **Paper:** the feasibility constraints in Sec. 4.4.3 — "queue admissibility `Q_j ≤
Q_max`," "energy availability `E_i ≥ E_min`," plus bandwidth/deadline.

## 2.3 `class QSALB.decide()` — **Algorithm 1, the proposed method** ⭐⭐
This is the single most important block in your whole project.
```python
qi = Q_i (+ eps_pred * predicted_arrivals[i] if prediction ON)
for j in feasible_candidates:
    qj    = Q_j (+ eps_pred * predicted_arrivals[j] if ON)
    drift = qj - qi                  # congestion (backpressure) term
    D     = est_latency(i, j, task)  # latency penalty
    E     = est_energy(i, j, task)   # energy penalty
    C     = 1 if j is Cloud else 0   # cloud-cost penalty
    score = kappa*drift + alpha*D + beta*E + gamma*C
choose the j with the LOWEST score
```
📄 **Paper, this *is* the drift-plus-penalty rule:**
- `score = χ·drift + α·D + φ·E + ι·C` is the objective of **Eq. 3.11 / 4.9 / 4.10**:
  `min  α·ΣT(latency) + φ·E(energy) + ι·C(cloud) + χ·ΣQ(congestion)`.
- `drift = qj − qi` is the **queue differential** `S_ij = Q_i − Q_j` (Eq. 4.11). It pushes
  tasks from congested to less-congested nodes — the "backpressure" idea (Sec. 4.4.1).
- The prediction terms `+ eps_pred * Â` implement **proactive queue adjustment**
  `Q̃_i = Q_i + ε·Â_i` (Eq. 4.13). `eps_pred` is the paper's `ε`.
- Looping over `feasible_candidates` and picking the minimum is the **local decision making**
  of Sec. 4.6.1, with complexity `O(K·|N|)` (Sec. 4.6.3).
- Returning exactly one `j` enforces `Σ_j x_ij = 1` (Eq. 3.5 / 4.5) — each task runs once.
📊 **CSV:** `D` and `E` here are computed from this task's **execution time, memory, network
latency and jitter** — so every score is grounded in your real data.

> **Honest note to mention:** the paper writes `S_ij = Q_i − Q_j`, but its own comment and
> Sec. 4.4.1 require penalising *congested destinations*, so the code uses `qj − qi` (the
> backpressure-correct sign). Saying this shows you understood the method, not just copied it.

## 2.4 The six baselines (Sec. 5.3) — each in a few lines
| Class | Code logic | Paper (Sec. 5.3) |
|---|---|---|
| `LEO` | `return src` (never offload) | Local Execution Only — lower-bound baseline |
| `GMQ` | pick candidate with smallest `node.queue` | Greedy Minimum-Queue |
| `LFO` | pick min `comm_ms + proc_ms` (queue-blind) | Latency-First Offloading |
| `EAO` | pick min `est_energy` | Energy-Aware Offloading |
| `DRLO` | Q-learning agent (see below) | Deep RL Offloader |
| `CFOP` | edge→fog→cloud as each gets congested | Cloud-First Overflow Policy |

## 2.5 `class DRLO` — the learning baseline
```python
self.Q = zeros((3 congestion-buckets, 4 actions))   # a learning table
decide():  pick action (target layer) ε-greedily from Q-table
learn(reward): Q[state,action] += lr * (reward + γ·maxQ(next) − Q[state,action])
```
📄 **Paper:** the DRL/Q-learning offloader of Sec. 5.3 and the RL discussion in Sec. 2.3.
It's a compact, reproducible stand-in for a full DQN/actor-critic.
📊 **CSV:** its reward depends on each task's latency vs. its **`Workload_Type`-derived
deadline**.

---

# FILE 3 — `qsalb_runner.py` (the clock — runs one experiment)

## 3.1 `DEFAULT_WEIGHTS` — the objective knobs
```python
alpha=1.0 (latency), beta=0.6 (energy), gamma=8.0 (cloud cost),
kappa=2.5 (congestion), eps_pred=0.4 (prediction strength)
```
📄 **Paper:** these are the weights `α, φ, ι, χ` of the objective (Eq. 3.11) and `ε`
(Eq. 4.13). High `gamma` discourages cloud use (cloud costs money).

## 3.2 `run_policy()` — **the per-slot loop = Algorithm 1's outer loop** ⭐
This brings the whole simulation to life. Walk through the four phases:

**Phase 0 — predictor (optional).**
```python
st = State(nodes, layer_idx, pred if predict else None, weights)
```
📄 Sec. 4.5 — the predictive enhancement layer; `pred` holds `Â_i(t+1)` (Eq. 4.12).

**Phase 1 — arrivals + offloading decisions.**
```python
for task in by_slot[t]:                 # tasks arriving this slot
    dst = policy.decide(st, src, task)  # WHERE to send it (Algorithm 1, step 4)
    if dnode.queue >= dnode.q_max: overflow++   # buffer full -> drop
    lat = est_latency(...);  if lat > task.deadline_ms: deadline_miss++   # Eq. 3.6
    tx, pe = energy charged;  node.energy -= ...                          # Eq. 3.8
    dnode.queue += 1                    # enqueue at chosen node
```
📄 **Paper:** this is Algorithm 1 steps 3–4 (compute drift-plus-penalty score, choose
destination, forward task), the deadline check (Eq. 3.6) and the energy update (Eq. 3.8).
📊 **CSV:** `task` here is a real row — its **execution time, memory, latency, jitter,
deadline** all drive `lat` and `tx`.

**Phase 2 — service (the queue update).**
```python
for nd in nodes:
    nd.queue = max(nd.queue - nd.mu_max, 0.0)   # each machine finishes mu_max tasks
```
📄 **Paper:** this is the **queue dynamics equation `Q_j(t+1) = max(Q_j(t) − µ_j + I_j(t),
0)`** (Eq. 4.3) — the single most important equation, here in code. (Arrivals `I_j` were
added in Phase 1; subtraction of `µ_j` happens here.)

**Phase 3 — predictor update + record metrics.**
```python
pred = 0.5*pred + 0.5*arrivals_this_slot     # EWMA forecast of next slot
total_backlog = sum(nd.queue for nd in nodes)
m.queue_samples.append(total_backlog)        # for the stability figures
```
📄 **Paper:** the arrival predictor (Eq. 4.12) and the queue-stability quantity we track,
`lim sup (1/T) Σ E[Q_j] < ∞` (Eq. 3.12). A flat `queue_samples` line = stable queues.

---

# FILE 4 — `qsalb_experiment.py` (runs everything, draws figures)

## 4.1 Configuration
```python
N_SLOTS=200; STRESS_LOAD=8; SWEEP_LOADS=[2,4,6,8,10,12]; SEEDS=range(8)
```
📄 **Paper:** the experimental methodology of Sec. 5.5 — multiple load scenarios, and
"results averaged over 20 independent runs with 95% confidence intervals" (here 8 seeds;
set to 20 to match exactly).

## 4.2 `run_once()` and `ci95()`
```python
run_once(name, load, seed): load_tasks(...) -> run_policy(...) -> metrics
ci95(vals): mean ± 1.96*std/√n      # 95% confidence interval
```
📄 **Paper:** the "95% confidence intervals" reporting protocol (Sec. 5.5).
📊 **CSV:** each `run_once` re-reads and replays your 1000 tasks at the given load.

## 4.3 The four figure functions
| Function | Figure | Paper / CSV link |
|---|---|---|
| `build_summary` | `results_summary.csv` | all Sec. 5.4 metrics on your data |
| `fig_metric_bars` | fig1 | side-by-side Sec. 5.4 metrics |
| `fig_stability_vs_load` | fig2 | queue stability (Eq. 3.12) across loads (Sec. 5.5) |
| `fig_queue_trajectory` | fig3 | backlog over time = visual proof of bounded queues |
| `fig_ranking_heatmap` | fig4 | overall ranking weighted by the objective (Eq. 3.11) |

---

# THE BIG PICTURE — how it all connects

```
   YOUR CSV (1000 rows)
        │   load_tasks()  ── columns -> Task fields (Eq. 3.1)
        ▼
   Task stream over time slots  (load_factor / bursty = Sec. 5.2 workloads)
        │
        ▼
   run_policy() loop, each slot:                         ← Algorithm 1
        1. policy.decide()  ── QSALB drift-plus-penalty  (Eq. 3.11/4.10)
        2. queue update Q(t+1)=max(Q−µ+I,0)              (Eq. 4.3)
        3. record queue, latency, deadline, energy       (Sec. 5.4)
        │
        ▼
   8 algorithms × multiple loads × 8 seeds (± 95% CI)    (Sec. 5.5)
        │
        ▼
   4 figures + summary table  →  "QSALB keeps queues bounded & wins"
```

---

# 30-second answers if a panelist points at the code

- **"Where is your algorithm?"** → `QSALB.decide()` in `qsalb_policies.py`. The `score`
  line is the drift-plus-penalty rule (Eq. 3.11).
- **"Where does the CSV come in?"** → `load_tasks()` in `qsalb_core.py`; it maps six columns
  to each Task's fields.
- **"Where is the queue stability equation?"** → Phase 2 of `run_policy()`:
  `nd.queue = max(nd.queue − nd.mu_max, 0)` is Eq. 4.3.
- **"Where is the deadline?"** → derived from `Workload_Type` via `DEADLINE_MS`, checked in
  `run_policy()` against `est_latency` (Eq. 3.6).
- **"How do you prove it's not luck?"** → 8 random seeds, averaged, with 95% confidence
  intervals (`ci95`), per Sec. 5.5.

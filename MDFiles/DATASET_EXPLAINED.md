# Your Dataset Explained — `Multi_Tier_IoT_Resource_Allocation_Dataset.csv`

*This explains the whole project **through your CSV**: what every column means, which
ones the code uses (and which it ignores, and why), and how one real row travels through
the simulation to become a result. Pair this with `STUDY_GUIDE.md`.*

---

## 1. What your dataset is, in one line

It is a log of **1000 IoT tasks** collected from **20 devices** (D1–D20), recorded every
10 seconds. Each row = **one task** with its measured characteristics (how big it is, how
long it took, the network conditions, what kind of work it is). My project replays these
1000 tasks through a simulated IoT–Edge–Fog–Cloud system and lets each algorithm decide
where to run them.

- 1000 rows (tasks) · 20 devices · 4 workload types · 13 columns
- Workload mix: Data Analytics 263, Image Processing 258, Video Processing 242, Network Traffic 237

---

## 2. Every column, in plain English

| # | Column | What it means (IoT context) | Example |
|---|---|---|---|
| 1 | `Timestamp` | When the task was recorded (10-second intervals) | 2024-03-25 12:00:10 |
| 2 | `Device_ID` | Which of the 20 IoT devices produced the task | D5 |
| 3 | `Sensor_Data` | The raw sensor reading (just descriptive text) | Temp: 22°C, Humidity: 61% |
| 4 | `Workload_Type` | The kind of computation the task needs | Data Analytics |
| 5 | `Processing_Tier` | Where **the dataset itself** placed the task | Device / Edge / Fog / Cloud |
| 6 | `CPU_Usage(%)` | CPU load observed for the task | 57 |
| 7 | `Memory_Usage(MB)` | Memory the task used (we treat as payload size) | 6812 |
| 8 | `Network_Latency(ms)` | Network delay measured for the task | 9 |
| 9 | `Jitter(ms)` | Variation/instability in that network delay | 2 |
| 10 | `Task_Execution_Time(ms)` | How long the task took to run | 216 |
| 11 | `Predicted_Resource_Allocation(%)` | A predicted resource share | 57 |
| 12 | `Actual_Resource_Allocation(%)` | The actual resource share given | 55 |
| 13 | `Target` | A 0/1 label (a supervised-ML class label) | 1 |

---

## 3. The 6 columns the simulation USES (and exactly how)

In the code, `load_tasks()` (in `qsalb_core.py`) reads the CSV and turns each row into a
**`Task` object**. Here is the precise mapping — memorise this table:

| CSV column | Becomes (Task field) | Role in the simulation |
|---|---|---|
| `Device_ID` | `src_node` | Which IoT device the task starts at (D1→node 0 … D20→node 19) |
| `Task_Execution_Time(ms)` | `base_exec_ms` | The task's intrinsic compute demand. On a faster machine it finishes proportionally quicker (`time = base_exec / node_speed`). |
| `Memory_Usage(MB)` | `size_mb` (÷1024) | The data payload that must be **transmitted** if the task is offloaded — drives network delay and transmission energy. |
| `Network_Latency(ms)` | `net_latency_ms` | Added to communication delay when the task crosses the network. |
| `Jitter(ms)` | `jitter_ms` | Extra communication delay from network instability. |
| `Workload_Type` | `deadline_ms` | Used to assign each task a **deadline** (see §5). |

> **So a real task carries real numbers.** Nothing is invented — the delays, sizes and
> compute times all come straight from your measurements.

---

## 4. The 7 columns the simulation does NOT use — and WHY ⭐

**This is the most likely "gotcha" question. Have this answer ready.**

| Unused column | Why it's not fed into the algorithms |
|---|---|
| `Timestamp` | Only marks order; I lay tasks onto simulation time-slots myself, and can vary the load. |
| `Sensor_Data` | Descriptive text (temperature/humidity); irrelevant to *where* to run a task. |
| `Processing_Tier` | **This is the dataset's *own* placement decision.** My whole project is to let *my* algorithms decide the tier. Feeding the dataset's answer back in would be **circular reasoning / cheating** — I'd just be copying it. |
| `CPU_Usage(%)` | A symptom of running the task; I already capture compute demand via `Task_Execution_Time`, so using both would double-count. |
| `Predicted_Resource_Allocation(%)` | Part of a resource-prediction/ML-classification task, not a routing input. |
| `Actual_Resource_Allocation(%)` | Same — it's an outcome label, not a decision input. |
| `Target` | A 0/1 supervised-learning label. It belongs to a *classification* problem; my project is an *optimization/scheduling* problem, so it isn't used. |

> **The clean sentence to say:** "The dataset was originally shaped for an ML
> classification task — it even contains the tier it chose and a target label. My project
> is different: it's an *optimization* problem where my algorithm must *decide* the tier.
> So I use the columns that describe the **task** (size, compute time, network conditions,
> device, workload type) and deliberately ignore the columns that describe the dataset's
> **own decisions and labels**, because using those would make the comparison circular."

That answer shows real understanding and usually impresses panels.

---

## 5. How `Workload_Type` becomes a deadline

Real-time IoT tasks have deadlines, but your CSV doesn't have a deadline column — so I
derive one from the workload type, staying inside the paper's stated 50–500 ms range
(Section 5.2). Stricter (latency-critical) work gets tighter deadlines:

| `Workload_Type` | Deadline assigned | Reasoning |
|---|---|---|
| Video Processing | 120 ms | Latency-critical (e.g. live video) |
| Network Traffic | 150 ms | Time-sensitive routing/monitoring |
| Image Processing | 300 ms | Moderate |
| Data Analytics | 500 ms | Can tolerate delay (batch-style) |

You can point at the `DEADLINE_MS` dictionary in `qsalb_core.py` if asked where this lives.

---

## 6. From 1000 rows to a running simulation

The 1000 rows don't all arrive at once — that would be unrealistic. `load_tasks()` spreads
them across **time slots** (clock ticks). Two knobs control the stress test:

- **`load_factor`** — multiplies the arrival rate. `load_factor=8` means we replay the
  tasks at 8× intensity to create congestion and reveal which algorithm stays stable. This
  is how the x-axis of `fig2_stability_vs_load.png` is produced (loads 2, 4, 6, 8, 10, 12).
- **`bursty=True`** — clusters arrivals into bursts (the paper's MMPP traffic), so load
  comes in waves instead of evenly. This stresses queue stability the way real IoT bursts do.

So your 1000 real tasks are the **building blocks**; the simulation arranges and repeats
them to study behaviour from light to heavy load.

---

## 7. A full worked example — following ONE real task end-to-end

Take **CSV row 5**: device **D8**, **Video Processing**, exec **239 ms**, memory **2072 MB**,
network latency **40 ms**, jitter **7 ms**. Here's its journey:

**Step 1 — Born.** It becomes a `Task` at IoT node for D8, with:
`base_exec_ms = 239`, `size_mb = 2.02`, `net_latency_ms = 40`, `jitter_ms = 7`,
`deadline_ms = 120` (because it's Video Processing).

**Step 2 — QSALB decides where to send it.** QSALB scores each possible machine. For
example, if it considered a **Fog** node (speed ≈ 5):
- processing time = 239 ÷ 5 ≈ **48 ms**
- communication = link(IoT→Fog) + 40 + 7 ≈ **77 ms**
- waiting = depends on that fog node's current queue
- It adds these (plus energy and cloud-cost terms, each weighted) into one **score**, and
  does the same for the local device, every edge, every fog, and the cloud.

**Step 3 — Chosen destination = lowest score.** Say the local D8 device is busy and a
nearby Fog node is free → QSALB sends it to that Fog node (draining the congested device
toward a less-congested, faster one — the core "backpressure" idea).

**Step 4 — Queue + service.** The task waits in the Fog node's queue, then the Fog node
processes it. Its **end-to-end latency** = communication + waiting + processing.

**Step 5 — Scored.** If that latency ≤ 120 ms → deadline met; otherwise it counts as a
**deadline miss**. Transmission + processing energy are charged. The queue length is
recorded. Multiply this by 1000 tasks × 8 algorithms × multiple seeds → the figures.

> Note: a 120 ms deadline with 40 ms of network latency is genuinely tight — which is why
> no algorithm hits 0% misses, and why a stability-aware method like QSALB (which avoids
> piling tasks onto congested nodes) misses far fewer than the queue-blind baselines.

---

## 8. Dataset-specific panel questions + answers

**Q. Describe your dataset.**
1000 IoT task records from 20 devices, each with workload type, CPU/memory usage, network
latency, jitter and execution time. I use it to drive a realistic IoT–Edge–Fog–Cloud
simulation.

**Q. Which columns did you actually use?**
Six: Device_ID, Workload_Type, Memory_Usage, Network_Latency, Jitter and
Task_Execution_Time — the ones that describe each task's characteristics.

**Q. Why did you ignore `Processing_Tier` / `Target`?**
Those are the dataset's *own* placement decision and a classification label. My project's
job is for the algorithm to *decide* the placement, so using the dataset's answer would be
circular. They'd be useful for a future ML predictor, not for the routing decision itself.

**Q. Where do deadlines come from? Your CSV has none.**
I derive them from workload type within the paper's 50–500 ms range — tighter for
latency-critical work like video (120 ms), looser for analytics (500 ms).

**Q. You only have 1000 rows — is that enough?**
Yes, because I don't just replay them once. I scale the arrival rate (load_factor) and add
bursty traffic to generate many load conditions from the same realistic tasks, then average
over multiple random seeds with confidence intervals.

**Q. Is `Memory_Usage` really the payload size?**
I use it as a proxy for the data that must be transmitted when offloading — larger memory
footprint → larger transfer → more network delay and transmission energy. It's a reasonable
modelling choice, stated clearly in the code.

**Q. How realistic is this?**
The task attributes (compute time, network latency, jitter, payload) are real measurements
from the dataset; the topology and capacities follow the paper's Section 5.1. It's a
faithful trace-driven simulation, which is the standard evaluation method in this field.

---

### The two sentences to remember about your data
1. "Each CSV row is one IoT task; I use its size, compute time, network conditions, device
   and workload type, and derive a deadline from the workload type."
2. "I ignore the dataset's own tier/label columns on purpose, because my algorithm must
   *decide* the tier — using them would be circular."

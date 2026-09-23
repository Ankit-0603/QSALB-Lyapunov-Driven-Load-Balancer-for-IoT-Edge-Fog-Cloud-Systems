# QSALB Project — Your Complete Study Guide

*A plain-English explanation of the whole project, written for someone new to Python,
so you can explain it confidently and answer panel questions on evaluation day.*

Read this top to bottom once, then re-read **Part 7 (panel questions)** until those
answers feel natural. You do **not** need to memorise code — you need to understand
the *ideas* and be able to point at the right file when asked.

---

## PART 0 — The 60-second pitch (memorise this)

> "My project tackles **load balancing** in a four-layer IoT system: tiny IoT devices,
> then Edge servers, then Fog servers, then the Cloud. When these devices produce lots
> of tasks, some machines get overloaded and form long waiting lines, called **queues**.
> Long queues mean delays and missed deadlines.
>
> I implemented **QSALB**, a method based on **Lyapunov optimization**, which decides
> *where to send each task* so that no machine's queue grows out of control — it keeps
> the system **stable**. I compared it against six other well-known strategies on a real
> IoT dataset of 1000 tasks, and measured queue length, delay, deadline misses, energy,
> cloud cost, throughput and fairness. **QSALB came out on top**: it keeps queues bounded
> and meets the most deadlines, especially when the system is under heavy load."

That paragraph alone answers the most common opening question: *"Tell us about your project."*

---

## PART 1 — The problem and the idea (no code yet)

### 1.1 The four layers (IoT → Edge → Fog → Cloud)
Think of it like a company handling customer requests:

- **IoT devices** = junior staff at the front desk. Many of them, but slow and weak
  (limited CPU, running on battery). In our data these are 20 devices, D1–D20.
- **Edge servers** = local team leads, a short walk away. Faster, a bit more capacity.
- **Fog servers** = a regional office. Much more powerful, but further away (more delay).
- **Cloud** = head office. Almost unlimited power, but far away (highest delay) **and it
  charges money** per task.

A task can be done where it's born (the IoT device) or **offloaded** (sent up) to a
faster machine. The catch: sending it costs time (network delay) and energy, and the
cloud costs money. So you can't just send everything to the cloud.

### 1.2 What is "load balancing" and "offloading"?
**Load balancing** = spreading work across machines so none is overwhelmed.
**Offloading** = the act of moving a task from one machine to another to balance the load.
Deciding *which* machine to send each task to is the whole problem.

### 1.3 What is a "queue" and why "stability"?
A **queue** is just a waiting line of tasks at a machine. If tasks arrive faster than a
machine can finish them, the line keeps growing — like a sink filling faster than it
drains. A growing-forever queue is **unstable**: delays explode and the system breaks.

A queue is **stable** if it stays bounded (doesn't grow to infinity) over time. **Queue
stability is the headline goal of this project.** That's what "QSALB" means:
**Q**ueue-**S**tability-**A**ware **L**oad **B**alancer.

### 1.4 What is Lyapunov optimization? (intuition, no scary math)
Named after the mathematician Lyapunov. The idea:

1. Define one number that measures **total congestion** in the whole system — basically
   "how full are all the queues right now." In the paper this is `V(t) = ½ × (sum of all
   queue lengths squared)`. Bigger = more congested.
2. Each time slot, choose the offloading decisions that push this congestion number
   **down** (or keep it from rising) — this is called minimizing the **drift**.
3. But don't *only* chase low queues — also keep latency, energy and cloud cost low.
   Balancing "reduce congestion" **plus** "keep the penalty (latency/energy/cost) low"
   is the famous **drift-plus-penalty** rule.

The beautiful part: doing this every slot **mathematically guarantees** the queues stay
bounded (stable) *without* needing to predict the future. That's why it beats heuristics
that only look at one thing.

> **One-line answer if asked "why Lyapunov?":** Because it gives a *provable* stability
> guarantee while still optimizing delay, energy and cost — heuristics and even most
> AI methods don't guarantee the queues stay bounded.

---

## PART 2 — How the simulation works (big picture)

We can't use thousands of real machines, so we **simulate** them in software, the way a
flight simulator imitates a plane. The simulation runs in **time slots** (think: ticks of
a clock). In each slot:

1. **New tasks arrive** at IoT devices (taken from your dataset).
2. **The algorithm decides** where each task goes (stay local, or offload to an edge/fog/cloud).
3. The task joins that machine's **queue**.
4. **Machines do work**: each machine finishes a few tasks from the front of its queue.
5. We **record measurements**: how long the queues are, delays, deadline misses, etc.

Repeat for ~200 slots. Then we look at the recorded numbers to see which algorithm did best.

We run this whole thing for **all 8 algorithms** and compare. We also repeat with different
random seeds (8 times) and average, so the result isn't a fluke — that's where the
"95% confidence interval" error bars come from.

---

## PART 3 — The 8 strategies in plain English

Your project compares the proposed method against six baselines, plus a predictive variant.
Here is each one with a simple analogy. (The paper lists these in Section 5.3.)

| Name | What it does | Analogy |
|---|---|---|
| **QSALB** (proposed) | Picks the destination that best balances *low congestion + low delay + low energy + low cloud cost* (drift-plus-penalty). | A smart dispatcher who weighs everything before assigning a job. |
| **QSALB-P** (proposed) | Same as QSALB but also **predicts** the next burst of work and prepares for it. | The same dispatcher, but who also reads the weather forecast. |
| **LEO** — Local Execution Only | Never offloads; every device does its own work. | Everyone insists on doing everything themselves — front desk drowns. |
| **GMQ** — Greedy Minimum-Queue | Always sends to whichever machine has the **shortest line right now**. | Pick the shortest checkout queue — ignores how far away or expensive it is. |
| **LFO** — Latency-First | Always sends to the machine with the **smallest expected delay**, ignoring how full it is. | Always drive to the "nearest" shop even if everyone else is already there. |
| **EAO** — Energy-Aware | Chooses to **save battery** above all. | Always pick the option that uses the least power, even if slow. |
| **DRL-O** — Deep RL Offloader | An **AI agent that learns** by trial and error which layer to use. | A trainee who learns from rewards/mistakes over time. |
| **CFOP** — Cloud-First Overflow | Uses edge/fog until they get congested, then **dumps to the cloud**. | When the local shop is busy, just pay extra and order from head office. |

**Why QSALB wins:** the baselines each optimize *one* thing (only queue, or only delay,
or only energy). QSALB balances *all* of them **and** has the stability guarantee, so under
heavy load it doesn't collapse the way the single-minded methods do.

---

## PART 4 — The metrics (what we measure and why)

These are exactly the metrics named in the paper's Section 5.4.

- **Average queue length** — how long the waiting lines are on average. *Lower = better, and
  staying low = stable.* This is the star metric.
- **Max queue length** — the worst congestion seen.
- **Overflow events** — how many times a machine's buffer was completely full and a task had
  to be dropped.
- **Average latency (ms)** — average end-to-end time per task = network delay + waiting in
  queue + processing time. *Lower = better.*
- **Deadline miss ratio** — fraction of tasks that finished too late. *Lower = better.* Very
  important for real-time IoT (e.g. a self-driving car can't be late).
- **Energy (Joules)** — battery used by IoT + Edge devices. *Lower = better.*
- **Cloud spillover fraction** — fraction of tasks that ended up in the (paid) cloud.
  *Lower = cheaper.*
- **Throughput** — tasks completed per slot. *Higher = better.*
- **Jain's fairness index** — a 0-to-1 score of how *evenly* work is spread across machines.
  1.0 = perfectly even. (A real metric; QSALB scores lower here because it deliberately
  favours the fastest machines — an honest trade-off.)

---

## PART 5 — The four figures (how to read each one)

These live in your `outputs` folder. Know what each one proves.

1. **fig2_stability_vs_load.png** — *your most important figure.* X-axis = how much load we
   pour in; Y-axis = average queue length (left) and deadline misses (right). QSALB and
   QSALB-P (thick lines) stay **low and flat** while every baseline shoots up. **This is the
   visual proof of queue stability.** If you only explain one figure, explain this.

2. **fig3_queue_trajectory.png** — total backlog over time at high load. QSALB hugs the
   bottom (flat = stable); others wander high (unstable). Flat line = bounded queue = stable.

3. **fig1_metric_comparison.png** — bar charts of all metrics side by side, with the winner
   of each metric outlined in **red**. Shows QSALB wins queue, latency, deadline, throughput.

4. **fig4_ranking_heatmap.png** — a colour grid (green = good, red = bad) scoring every
   algorithm on every metric, plus an overall score. QSALB-P and QSALB are top. The orange
   cells on QSALB's energy/fairness are the honest trade-offs — be ready to explain them
   (see Part 7, Q12).

---

## PART 6 — The code, file by file (plain English)

You have **4 code files**. Here's what each does and the beginner Python ideas inside.

> **Tiny Python primer (everything you need):**
> - A **variable** stores a value: `speed = 10`.
> - A **list** is an ordered collection: `[1, 2, 3]`.
> - A **dictionary** maps keys to values: `{"Edge": 8, "Fog": 3}`.
> - A **function** (`def name(...)`) is a reusable recipe that takes inputs and returns output.
> - A **class** is a blueprint that bundles data + actions together (like a template for an object).
> - A **loop** (`for x in things:`) repeats an action for each item.
> - `import numpy as np` loads a maths library we nickname `np` (fast number crunching).
> - `import pandas as pd` loads the table/spreadsheet library (for reading the CSV).

### File 1: `qsalb_core.py` — the world and its rules
This file builds the simulated world. Key pieces:

- **`class Node`** — a blueprint for one machine. It stores the machine's layer (IoT/Edge/
  Fog/Cloud), its `speed`, `mu_max` (how many tasks it can finish per slot), `q_max` (how
  big its queue can get), `energy` (battery), and `queue` (current waiting line).
- **`build_topology(...)`** — creates all the machines: 20 IoT, 8 Edge, 3 Fog, 1 Cloud,
  with capacities matching the paper's Section 5.1. Returns the list of machines.
- **`class Task`** — a blueprint for one job: which device made it, how big it is, how much
  CPU it needs, its deadline, etc.
- **`load_tasks(...)`** — opens your CSV file and turns each of the 1000 rows into a `Task`.
  It also spreads the tasks across time slots and can multiply the load (`load_factor`) to
  stress-test, and make traffic **bursty** (the MMPP idea from the paper).
- **`transmission_energy` / `processing_energy`** — small formulas for how much battery is
  spent sending a task over the network vs. computing it.
- **`class Metrics`** — a scoreboard that collects everything we measure during a run, and
  its `summary()` turns the raw data into the final numbers (avg queue, latency, etc.).

### File 2: `qsalb_policies.py` — the 8 decision rules (the brain)
This is the heart of the project. Each algorithm is a small **class** with one main method,
`decide(...)`, which answers: *"Given the current state and this task, which machine do I
send it to?"* It returns the chosen machine's index.

- Helper functions at the top estimate, for a possible destination: processing time
  (`proc_ms`), waiting time (`wait_ms`), network delay (`comm_ms`), total delay
  (`est_latency`), energy (`est_energy`), and whether the machine can even accept the task
  (`feasible` — checks the queue isn't full and there's battery left).
- **`class QSALB`** — implements **Algorithm 1**. For each candidate machine `j` it computes a
  **score** = `congestion + latency + energy + cloud-cost` (each weighted), then picks the
  machine with the **lowest score**. That single line *is* the drift-plus-penalty rule.
  If `predict=True`, it also adds predicted future arrivals to the congestion term.
- **`class LEO / GMQ / LFO / EAO / DRLO / CFOP`** — the six baselines, each a few lines that
  encode their simple rule (described in Part 3).
- **`all_policies()`** — a dictionary listing all 8 strategies so the experiment can loop
  over them.

> **If asked "show me where your algorithm is":** open `qsalb_policies.py`, scroll to
> `class QSALB`, and point at the `decide` method — that's Algorithm 1 in code.

### File 3: `qsalb_runner.py` — the clock that runs one experiment
- **`DEFAULT_WEIGHTS`** — the four importance knobs from the paper: `alpha` (latency),
  `beta` (energy), `gamma` (cloud cost), `kappa` (congestion), plus `eps_pred` (prediction
  strength). Changing these changes what the system prioritizes.
- **`run_policy(...)`** — **the main loop.** For each time slot it: (1) lets new tasks arrive,
  (2) asks the policy to decide where each goes, (3) puts tasks in queues and charges energy,
  (4) lets each machine finish `mu_max` tasks (the queue update `Q(t+1)=max(Q−µ+I,0)` from
  the paper), (5) records the queue length and other metrics. This is **Algorithm 1's per-slot
  loop** brought to life.

### File 4: `qsalb_experiment.py` — runs everything and draws the figures
This is the file you actually run. It:
- runs every policy over 8 random seeds (`build_summary`),
- saves the numbers to `results_summary.csv`,
- draws the four figures (`fig_metric_bars`, `fig_stability_vs_load`,
  `fig_queue_trajectory`, `fig_ranking_heatmap`),
- prints the final ranking.
- `ci95(...)` computes the 95% confidence-interval error bars (the little caps on the bars),
  proving the results are statistically reliable, not random luck.

---

## PART 7 — Likely panel questions + strong answers ⭐

*This is the section to over-prepare. Answers are short on purpose — say them in your words.*

**Q1. In one sentence, what is your project?**
A queue-stability-aware load balancer for IoT–Edge–Fog–Cloud systems that uses Lyapunov
optimization to decide task offloading, keeping queues bounded while minimizing delay,
energy and cloud cost.

**Q2. What is a queue and what is queue stability?**
A queue is the waiting line of tasks at a machine. Stability means the queue stays bounded
(finite) over time instead of growing forever. An unstable queue means exploding delays and
a broken system.

**Q3. What is Lyapunov optimization and why did you use it?**
It defines a single "congestion energy" value for the system and, each time slot, makes the
decision that keeps that value from growing — which *provably* keeps queues stable. I used it
because it gives a mathematical stability guarantee that heuristics and most AI methods lack,
while still optimizing latency, energy and cost.

**Q4. What is drift-plus-penalty?**
"Drift" is the change in congestion; minimizing drift keeps queues stable. "Penalty" is the
cost we also care about (latency + energy + cloud cost). Drift-plus-penalty minimizes their
weighted sum each slot, so we get **both** stability and good performance.

**Q5. How exactly does QSALB choose where to send a task?**
For every possible destination it computes a score that adds up: how congested that machine
is, the expected delay, the energy cost, and (if it's the cloud) the money cost — each
multiplied by an importance weight. It sends the task to the machine with the lowest score.

**Q6. What are your baselines and why those?**
LEO (local only), GMQ (shortest queue), LFO (lowest delay), EAO (lowest energy), DRL-O (an
AI/reinforcement-learning agent), CFOP (cloud overflow). They represent the three main
families in the literature — heuristic, optimization-based, and learning-based — so the
comparison is comprehensive.

**Q7. Why is QSALB better than the baselines?**
Each baseline optimizes only one objective and has no stability guarantee, so under heavy or
bursty load their queues blow up. QSALB balances all objectives *and* guarantees bounded
queues, so it stays low on queue length and deadline misses where others collapse — clearly
visible in fig2.

**Q8. DRL-O is "AI" — why doesn't it win?**
It learns well and is the strongest baseline, but it needs to learn by trial and error, can
be unstable while learning, and tends to dump tasks to the cloud (raising cost). It has no
formal stability guarantee, so QSALB still edges it out, especially on cloud cost and
worst-case stability.

**Q9. What dataset did you use?**
A multi-tier IoT resource-allocation dataset of 1000 task records from 20 devices, with each
task's workload type, CPU usage, memory, network latency, jitter and execution time. I derive
each task's deadline from its workload type, within the 50–500 ms range the paper specifies.

**Q10. How do you measure success?**
Eight metrics from the paper: average/max queue length, overflow events, latency, deadline-miss
ratio, energy, cloud spillover, throughput, and Jain's fairness. I average over 8 random seeds
and report 95% confidence intervals.

**Q11. What is the predictive module (QSALB-P)?**
An optional add-on that forecasts the next slot's task arrivals (using a simple moving average
in my implementation; LSTM/GRU in the full design) and adjusts decisions in advance. It
slightly improves cloud cost and fairness by preparing for bursts before they hit.

**Q12. QSALB uses more energy and has lower fairness — isn't that bad?**
It's an honest, deliberate trade-off. QSALB spends a little extra transmission energy to
offload tasks off congested devices, and it favours the fastest machines (lowering the fairness
score) — and in return it gets far lower delay, far fewer missed deadlines, and guaranteed
stability. The objective weights can be tuned if energy matters more in a given deployment.

**Q13. What does "the problem is NP-hard" mean (from the paper)?**
It means finding the perfect offloading solution exactly is computationally infeasible at
scale (no fast algorithm is known). That's *why* we use the Lyapunov drift-plus-penalty method
— it gives a near-optimal, stable solution cheaply and in a distributed way.

**Q14. Is your decision-making centralized or distributed?**
Distributed. Each node decides locally using its own queue and lightweight summaries from
neighbours, so it scales to large deployments. Complexity per decision is O(K·N) where K is the
number of candidate nodes (from the paper's Section 4.6.3).

**Q15. What is a time slot / discrete-time simulation?**
I model time as a sequence of small equal steps ("slots"). In each slot, tasks arrive,
decisions are made, machines do a fixed amount of work, and I record measurements. It's the
standard way to study queueing systems.

**Q16. Why not just send everything to the cloud?**
The cloud is far away (highest network delay) and charges money per task. Flooding it raises
latency and cost and wastes the nearby edge/fog capacity. Good load balancing uses the cloud
only as a last resort — which is exactly what QSALB learns to do (low cloud spillover).

**Q17. What are the limitations / future work?**
It's a simulation, not real hardware; the predictor is a simple moving average rather than a
deep network; and DRL-O is a lightweight surrogate of a full DQN. Future work: deploy on real
edge testbeds, add deep-learning predictors, and use federated learning for the predictions.

**Q18. How is this reproducible?**
Everything is seeded (fixed random numbers), I average over multiple seeds, report confidence
intervals, and the code is modular — anyone running `qsalb_experiment.py` gets the same figures.

---

## PART 8 — Honest limitations (say these *before* they catch you)

Owning your limitations makes you look strong, not weak:

1. It's a **simulation**, so numbers are relative comparisons, not real-hardware timings.
2. The **predictor** in code is a simple moving average; the paper envisions LSTM/GRU.
3. **DRL-O** is a compact stand-in for a full deep network — enough to compare behaviour,
   not a production RL system.
4. QSALB trades **a bit more energy and lower fairness** for big gains in stability and delay.
5. I corrected an apparent **sign typo** in the paper's drift formula so the code matches the
   paper's stated intent ("offload to less-congested nodes"). Mentioning this shows you
   understood the method deeply, not just copied it.

---

## PART 9 — A 5-step demo script for evaluation day

If you need to *run it live*, do exactly this:

```zsh
cd ~/Desktop/ClgProjClaude          # go to the project folder
source .venv/bin/activate           # turn on the environment (prompt shows (.venv))
python qsalb_experiment.py          # run everything (~a few seconds)
open outputs                        # open the folder with the figures
```

Then walk the panel through **fig2** first ("here QSALB stays flat while others blow up =
queue stability"), then the heatmap ("QSALB ranks #1 overall").

---

### Final tip
You don't need to know Python syntax perfectly. Panels mostly test whether you understand
**your own idea**: the problem, why Lyapunov gives stability, how QSALB decides, and why it
beats the baselines. Nail Parts 1, 3, and 7 and you'll do great. Good luck! 🎯

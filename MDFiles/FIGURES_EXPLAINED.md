# The Four Figures Explained — axes, calculations, and why each belongs in your paper

*For each figure: what the axes mean, exactly how the numbers were calculated (and why),
and which part of your paper it supports. Plain language throughout.*

---

## First, the building blocks used by every figure

Before the figures, the simulation produces **raw measurements**, then turns them into the
metrics from your paper's **Section 5.4**. Here is how each metric is calculated.

**Average queue length** — every time slot we add up the waiting lines at all machines
(total backlog), then average that over all 200 slots:
> `avg_queue = (1/T) × Σ_t ( Σ_j Q_j(t) )`  — average, over time, of total backlog.
*Why:* this is literally the quantity in the paper's stability requirement **Eq. 3.12**
`lim sup (1/T) Σ E[Q_j] < ∞`. A low, flat value = stable queues.

**Latency per task** = communication delay + waiting delay + processing delay:
> `T_k = T_comm + T_wait + T_proc`  (the three terms of **Eq. 3.6**).
**Average latency** = the mean of `T_k` over all tasks.

**Deadline miss ratio** = (tasks that finished later than their deadline, plus tasks dropped
because a queue was full) ÷ (total tasks). *Why:* real-time IoT needs deadlines met.

**Energy (Joules)** = sum of transmission energy + processing energy charged to the
battery devices (IoT + Edge), from **Eq. 3.8**.

**Cloud spillover fraction** = (tasks that ended at the cloud) ÷ (total routed tasks).
*Why:* the cloud costs money, so lower = cheaper (**Eq. 3.10**).

**Throughput** = (total tasks completed) ÷ (number of slots). Higher = more work done.

**Jain's fairness index** = `(Σ L_j)² / (N × Σ L_j²)`, where `L_j` = number of tasks sent to
node j. It ranges 0–1; **1 = perfectly even** spread of work. *Why:* a load-balancing
quality measure named in Section 5.4.

**The 95% confidence interval (the little error-bar caps).** We run each setting with **8
different random seeds** and average. The error bar is:
> `± 1.96 × (standard deviation) ÷ √(number of seeds)`
The `1.96` is the standard statistics constant for "95% confidence." *Why:* it proves the
results are reliable, not a lucky single run (your paper's Section 5.5 asks for this).

---

## FIGURE 1 — `fig1_metric_comparison.png` (bar charts)

**What it is:** six small bar charts, one per metric, each comparing all 8 algorithms at a
single heavy load (8× the dataset's arrival rate).

**Axes:**
- **X-axis** = the 8 algorithms (QSALB, QSALB-P, DRL-O, GMQ, CFOP, EAO, LFO, LEO).
- **Y-axis** = the value of that metric, in its natural unit (tasks, milliseconds, fraction,
  Joules, fraction, tasks/slot). Each panel title says "lower is better" or "higher is better."

**How the values were calculated:** for each algorithm and each metric, run the simulation
over 8 seeds at load 8, take the **average** as the bar height and the **95% CI** as the
error bar. The **red outline** marks the best algorithm for that metric (lowest for
"lower-is-better", highest for throughput).

**Why keep it (paper link):** it directly visualizes the **Section 5.4 metrics** side by
side, answering "does QSALB actually win on the metrics the paper promised to measure?"
It's your head-to-head scorecard.

---

## FIGURE 2 — `fig2_stability_vs_load.png` (line plots) ⭐ your most important figure

**What it is:** two line charts. **Left:** average queue length as load increases.
**Right:** deadline miss ratio as load increases.

**Axes:**
- **X-axis (both)** = **offered load** — how hard we push the system, from 2× up to 12× the
  dataset's natural arrival rate. Moving right = heavier traffic.
- **Left Y-axis** = average total queue length (tasks). **Right Y-axis** = deadline miss
  ratio (0 to 1).
- Each **line** is one algorithm; QSALB and QSALB-P are drawn thick.

**How the values were calculated:** for **each load level** in {2, 4, 6, 8, 10, 12}, run
every algorithm over 8 seeds, average the queue length (left) and deadline miss (right), and
plot the point with its 95% CI. Connecting the points across loads gives each line.

**Why this is the key figure (paper link):** the whole thesis is **queue stability**
(**Eq. 3.12**) — queues must stay bounded as load grows. This figure shows exactly that:
QSALB/QSALB-P stay **low and flat** while the queue-blind baselines **shoot upward** and
their deadline misses climb toward 100%. It is the empirical proof of the Lyapunov stability
guarantee and of the paper's claim that QSALB "reduces queue buildup, latency and
deadline-miss" (Abstract). It also maps to the multi-scenario methodology of **Section 5.5**.
**If you explain only one figure, explain this one.**

---

## FIGURE 3 — `fig3_queue_trajectory.png` (backlog over time)

**What it is:** one chart showing the total backlog of the whole system at every moment,
under heavy load (8×).

**Axes:**
- **X-axis** = **time slot** (0 to 200) — the simulation clock ticking forward.
- **Y-axis** = total queue length across all machines at that instant (tasks).
- Each **line** is one algorithm (QSALB/QSALB-P thick).

**How the values were calculated:** for each algorithm, run 8 seeds at load 8; each run
records the total backlog at every slot (200 numbers). We **average the 8 runs slot-by-slot**
to get one smooth trajectory per algorithm, then plot it.

**Why keep it (paper link):** it's the **visual definition of stability**. A **flat line near
the bottom = bounded queue = stable** (QSALB/QSALB-P); a **high, drifting line = unstable**
(the baselines). Where Figure 2 shows stability *as load changes*, Figure 3 shows it
*over time* — together they make the stability argument from both angles (the requirement in
**Eq. 3.12** and the queue dynamics of **Eq. 4.3**).

---

## FIGURE 4 — `fig4_ranking_heatmap.png` (overall ranking grid)

**What it is:** a colored grid scoring every algorithm on every metric, plus one overall
score — a single summary of "who is best overall."

**Axes:**
- **Y-axis (rows)** = the 8 algorithms, each labelled with its overall score, sorted best
  to worst.
- **X-axis (columns)** = the 8 metrics, each labelled with its weight (e.g. `w=0.24`).
- **Colour** = a **normalized score from 0 to 1** (green = best, red = worst).

**How the values were calculated — two steps:**
1. **Normalize each metric to 0–1** so different units can share one colour scale:
   `normalized = (value − worst) / (best − worst)`, flipped for "lower-is-better" metrics so
   that **1 always means best**. (This is the only way to compare milliseconds against Joules
   against fractions on one picture.)
2. **Overall score** = a **weighted average** of those normalized scores:
   `overall = Σ (weight × normalized_score)`. The weights prioritize the paper's objective —
   deadline (0.24), queue (0.20), latency (0.20) highest; energy (0.05), fairness (0.03)
   lowest — matching **Eq. 3.11**, which weights latency, congestion, cost above energy.

**Why keep it (paper link):** it condenses all of Section 5.4 into one ranked picture and
gives the headline conclusion — **QSALB-P and QSALB rank #1 and #2 overall**. Crucially, the
**cells are un-weighted**, so it honestly shows QSALB's trade-offs (orange on energy and
fairness) rather than hiding them — which is exactly the kind of transparency a panel
respects. The weighting mirrors the multi-objective cost of **Eq. 3.11**.

---

## One-paragraph summary you can say out loud

> "Figure 1 is the head-to-head bar comparison on all the metrics from Section 5.4. Figure 2
> is my main result: as I increase the offered load, QSALB keeps the queue length and
> deadline misses low and flat while the baselines blow up — that's the queue-stability
> guarantee from Equation 3.12. Figure 3 shows the same stability over time: a flat backlog
> line means bounded queues. Figure 4 normalizes every metric to a 0–1 score and computes a
> weighted overall ranking using the paper's objective weights, and QSALB comes out on top.
> All values are averaged over 8 random seeds with 95% confidence intervals, so they're
> statistically reliable, not luck."

---

## Quick reference table

| Figure | X-axis | Y-axis | Calculation | Paper link |
|---|---|---|---|---|
| **1** Bars | 8 algorithms | metric value (per unit) | mean ± 95% CI at load 8 | Sec. 5.4 metrics |
| **2** Lines | offered load (2–12×) | queue length / deadline miss | mean ± 95% CI per load | Eq. 3.12 stability, Sec. 5.5 |
| **3** Trajectory | time slot (0–200) | total backlog | 8-seed average per slot | Eq. 3.12 + Eq. 4.3 |
| **4** Heatmap | 8 metrics (weighted) | 8 algorithms (overall score) | normalize 0–1, weighted sum | Eq. 3.11 objective |

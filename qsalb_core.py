from __future__ import annotations
import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

#   IoT  : 20 sensing devices      
#   Edge : 8  micro-servers  
#   Fog  : 3  regional servers 
#   Cloud: 1  datacenter  

LAYERS = ("IoT", "Edge", "Fog", "Cloud")


@dataclass
class Node:
    nid: int                 # node index
    name: str                # storing some strgs
    layer: str               # name of LAYERS
    speed: float             
    mu_max: int              
    q_max: int               
    energy: float            
    energy_init: float      
    is_battery: bool         

    queue: float = 0.0       # current backlog i.e left tasks


def build_topology(n_edge: int = 8, n_fog: int = 3, n_cloud: int = 1,
                   n_iot: int = 20, rng: np.random.Generator | None = None):

    if rng is None:
        rng = np.random.default_rng(0)
    nodes: list[Node] = []
    idx = 0

    # IoT devices: 20
    for d in range(n_iot):
        nodes.append(Node(idx, f"IoT{d+1}", "IoT", #f"IoT{d+1}" is a f-string that inserts the number into the name
                          speed=1.0, mu_max=1, q_max=12,
                          energy=float(rng.integers(500, 2001)),
                          energy_init=0.0, is_battery=True))
        nodes[-1].energy_init = nodes[-1].energy #store random energy(battery) in energy_init
        idx += 1 #moves to next ID

    #Edge:8 (2-3 x faster than IOT device)
    for e in range(n_edge): 
        nodes.append(Node(idx, f"Edge{e+1}", "Edge",
                          speed=float(rng.uniform(2.0, 3.0)),
                          mu_max=3, q_max=40,
                          energy=8000.0, energy_init=8000.0, is_battery=True))
        idx += 1

    #Fog:
    for f in range(n_fog):
        nodes.append(Node(idx, f"Fog{f+1}", "Fog",
                          speed=float(rng.uniform(4.0, 6.0)),
                          mu_max=8, q_max=120,
                          energy=math.inf, energy_init=math.inf,
                          is_battery=False))
        idx += 1
    #Cloud:
    for c in range(n_cloud):
        nodes.append(Node(idx, f"Cloud{c+1}", "Cloud",
                          speed=10.0, mu_max=30, q_max=100000,
                          energy=math.inf, energy_init=math.inf,
                          is_battery=False))
        idx += 1

    layer_idx = {L: [n.nid for n in nodes if n.layer == L] for L in LAYERS}
    return nodes, layer_idx



# section 5.1. All taken as assumptions according to this section
LINK_LATENCY = {
    ("IoT", "IoT"):   0.0,
    ("IoT", "Edge"):  8.0,
    ("Edge", "Edge"): 4.0,
    ("Edge", "Fog"):  18.0,
    ("Fog", "Fog"):   6.0,
    ("Fog", "Cloud"): 55.0,
    ("Edge", "Cloud"): 60.0,   # rare direct edge->cloud
    ("IoT", "Fog"):   30.0,    # rare skip
    ("IoT", "Cloud"): 70.0,    # rare skip
}


def link_latency(src_layer: str, dst_layer: str) -> float:
    if src_layer == dst_layer:
        # local execution OR peer cooperation within same layer
        return 0.0 if src_layer in ("IoT", "Cloud") else LINK_LATENCY.get((src_layer, dst_layer), 4.0)
    return LINK_LATENCY.get((src_layer, dst_layer),
                            LINK_LATENCY.get((dst_layer, src_layer), 40.0))


#taking deadline from sec 5.2()
DEADLINE_MS = {
    "Video Processing": 120.0,
    "Network Traffic":  150.0,   
    "Image Processing": 300.0,   
    "Data Analytics":   500.0,   
}


@dataclass

#each is filled from the csv file
class Task:
    tid: int
    src_node: int            # originating IoT device (global node index)
    base_exec_ms: float      # intrinsic processing time at speed=1 (from dataset)
    size_mb: float           # data size (from Memory_Usage proxy)
    net_latency_ms: float    # measured network latency (from dataset)
    jitter_ms: float         # measured jitter (from dataset)
    deadline_ms: float       # derived from workload type
    workload: str
    arrival_slot: int        # slot at which it arrives


def load_tasks(csv_path: str, n_slots: int, load_factor: float = 1.0,
               bursty: bool = False, rng: np.random.Generator | None = None):
    
    #random generator, then reads your CSV file
    if rng is None:
        rng = np.random.default_rng(0)
    df = pd.read_csv(csv_path)

    # Map dataset Device_ID (D1..D20) -> IoT node index 0..19
    dev_ids = sorted(df["Device_ID"].unique(), key=lambda x: int(x[1:]))
    dev_to_node = {d: i for i, d in enumerate(dev_ids)}

    # Replicate rows according to load_factor to raise offered load.
    reps = max(1, int(round(load_factor)))
    frac = load_factor - reps if load_factor > reps else 0.0
    rows = pd.concat([df] * reps, ignore_index=True)
    if frac > 0:
        extra = df.sample(frac=frac, replace=False, random_state=int(rng.integers(1e6)))
        rows = pd.concat([rows, extra], ignore_index=True)
    rows = rows.sample(frac=1.0, random_state=int(rng.integers(1e6))).reset_index(drop=True)

    n_tasks = len(rows)


    if bursty:
        # 2-state MMPP-like modulation: alternate "high" and "low" arrival phases
        slot_weights = np.ones(n_slots)
        state = 1
        for s in range(n_slots):
            if rng.random() < 0.15:            # state switch probability
                state ^= 1
            slot_weights[s] = 3.0 if state == 1 else 0.5
        slot_weights /= slot_weights.sum()
        arrival_slots = rng.choice(n_slots, size=n_tasks, p=slot_weights)
    else:
        arrival_slots = rng.integers(0, n_slots, size=n_tasks)

    tasks: list[Task] = []
    for i, (_, r) in enumerate(rows.iterrows()):
        wl = r["Workload_Type"]
        tasks.append(Task(
            tid=i,
            src_node=dev_to_node[r["Device_ID"]],
            base_exec_ms=float(r["Task_Execution_Time(ms)"]),
            size_mb=float(r["Memory_Usage(MB)"]) / 1024.0,   # MB proxy for payload
            net_latency_ms=float(r["Network_Latency(ms)"]),
            jitter_ms=float(r["Jitter(ms)"]),
            deadline_ms=DEADLINE_MS.get(wl, 300.0),
            workload=wl,
            arrival_slot=int(arrival_slots[i]),
        ))
    # group tasks by arrival slot for fast access
    by_slot: list[list[Task]] = [[] for _ in range(n_slots)]
    for t in tasks:
        by_slot[t.arrival_slot].append(t)
    return tasks, by_slot, dev_to_node


#Energy
E_TX_PER_MB = 0.55      # Joules per MB transmitted (radio)
E_PROC_PER_MS = 0.012   # Joules per ms of local processing on a battery node


def transmission_energy(size_mb: float, hops: int) -> float:
    return E_TX_PER_MB * size_mb * max(hops, 0)


def processing_energy(exec_ms_on_node: float) -> float:
    return E_PROC_PER_MS * exec_ms_on_node


# All the metrices for the comparisions
@dataclass
class Metrics:
    name: str
    queue_samples: list = field(default_factory=list)   # per-slot total backlog
    per_node_load: np.ndarray | None = None             # tasks routed to each node
    latencies: list = field(default_factory=list)       # completed-task E2E latency
    deadline_total: int = 0
    deadline_miss: int = 0
    energy_consumed: float = 0.0                         # IoT+Edge Joules
    overflow_events: int = 0
    completed: int = 0
    cloud_tasks: int = 0
    routed_total: int = 0
    max_queue: float = 0.0

    def summary(self) -> dict:
        q = np.array(self.queue_samples) if self.queue_samples else np.array([0.0])
        lat = np.array(self.latencies) if self.latencies else np.array([0.0])
        load = self.per_node_load if self.per_node_load is not None else np.array([1.0])

        s = load.sum()
        jain = (s ** 2) / (len(load) * np.sum(load ** 2)) if np.sum(load ** 2) > 0 else 1.0
        return {
            "Algorithm": self.name,
            "Avg Queue Length": float(q.mean()),
            "Max Queue Length": float(self.max_queue),
            "Overflow Events": int(self.overflow_events),
            "Avg Latency (ms)": float(lat.mean()),
            "P95 Latency (ms)": float(np.percentile(lat, 95)),
            "Deadline Miss Ratio": (self.deadline_miss / self.deadline_total
                                    if self.deadline_total else 0.0),
            "Energy (J)": float(self.energy_consumed),
            "Cloud Spillover Frac": (self.cloud_tasks / self.routed_total
                                     if self.routed_total else 0.0),
            "Throughput (tasks/slot)": float(self.completed / max(len(self.queue_samples), 1)),
            "Jain Fairness": float(jain),
        }

from __future__ import annotations
import math
import numpy as np
from qsalb_core import Node, link_latency, transmission_energy, processing_energy

LAYER_RANK = {"IoT": 0, "Edge": 1, "Fog": 2, "Cloud": 3}
EPS = 1e-3


# helpers
def proc_ms(node: Node, task) -> float:
    return task.base_exec_ms / node.speed


def wait_ms(node: Node, task) -> float:
    return (node.queue / (node.mu_max + EPS)) * proc_ms(node, task)


def comm_ms(src: Node, dst: Node, task) -> float:
    if src.nid == dst.nid:
        return 0.0
    return link_latency(src.layer, dst.layer) + task.net_latency_ms + task.jitter_ms


def est_latency(src: Node, dst: Node, task) -> float:
    return comm_ms(src, dst, task) + wait_ms(dst, task) + proc_ms(dst, task)


def hops(src: Node, dst: Node) -> int:
    if src.nid == dst.nid:
        return 0
    return max(1, abs(LAYER_RANK[dst.layer] - LAYER_RANK[src.layer]))


def est_energy(src: Node, dst: Node, task) -> float:
    e = transmission_energy(task.size_mb, hops(src, dst)) if src.nid != dst.nid else 0.0
    if dst.is_battery:                       # processing on a battery node costs energy
        e += processing_energy(proc_ms(dst, task))
    return e


def feasible(node: Node, task, e_min: float = 50.0) -> bool:
    if node.queue >= node.q_max:
        return False
    if node.is_battery and node.energy <= e_min:
        return False
    return True


def candidate_set(nodes, layer_idx, src_node: int):
    cands = [src_node]
    cands += layer_idx["Edge"] + layer_idx["Fog"] + layer_idx["Cloud"]
    return [c for c in cands if feasible(nodes[c], None)  # quick queue/energy gate
            ]


class State:
    def __init__(self, nodes, layer_idx, pred_arrivals, weights):
        self.nodes = nodes
        self.layer_idx = layer_idx
        self.pred = pred_arrivals          # np.array predicted arrivals per node (or None)
        self.w = weights                   # dict: alpha,beta,gamma,kappa,eps_pred

    def feasible_candidates(self, src):
        out = [src] + self.layer_idx["Edge"] + self.layer_idx["Fog"] + self.layer_idx["Cloud"]
        return [c for c in out if feasible(self.nodes[c], None)]



# QSALB

class QSALB:
    name = "QSALB"

    def __init__(self, predict: bool = False):
        self.predict = predict

    def decide(self, st: State, src: int, task) -> int:
        nodes, w = st.nodes, st.w
        src_node = nodes[src]
        cloud_set = set(st.layer_idx["Cloud"])
        qi = nodes[src].queue + (w["eps_pred"] * st.pred[src] if (self.predict and st.pred is not None) else 0.0)

        best, best_score = src, math.inf
        for j in st.feasible_candidates(src):
            dst = nodes[j]
            qj = dst.queue + (w["eps_pred"] * st.pred[j] if (self.predict and st.pred is not None) else 0.0)
            drift = (qj - qi)
            D = est_latency(src_node, dst, task)
            E = est_energy(src_node, dst, task)
            C = 1.0 if j in cloud_set else 0.0
            score = (w["kappa"] * drift + w["alpha"] * D +
                     w["beta"] * E + w["gamma"] * C)
            if score < best_score:
                best_score, best = score, j
        return best

#LEO
class LEO:
    name = "LEO"
    def decide(self, st: State, src: int, task) -> int:
        return src                      # never offloads



#GMQ
class GMQ:
    name = "GMQ"
    def decide(self, st: State, src: int, task) -> int:
        cands = st.feasible_candidates(src)
        return min(cands, key=lambda j: (st.nodes[j].queue, -st.nodes[j].speed))

#LFO

class LFO:
    name = "LFO"
    def decide(self, st: State, src: int, task) -> int:
        s = st.nodes[src]
        cands = st.feasible_candidates(src)
        # nominal delay = communication + processing, WITHOUT dynamic queue wait
        return min(cands, key=lambda j: comm_ms(s, st.nodes[j], task)
                   + proc_ms(st.nodes[j], task))

# EAO
class EAO:
    name = "EAO"
    def decide(self, st: State, src: int, task) -> int:
        s = st.nodes[src]
        cands = st.feasible_candidates(src)
        # minimise battery energy; break ties by lower latency. Low-battery source
        # gets a strong penalty for keeping the task local.
        def cost(j):
            dst = st.nodes[j]
            e = est_energy(s, dst, task)
            if j == src and s.energy < 0.25 * s.energy_init:
                e += 100.0               # discourage draining an almost-empty device
            return (e, est_latency(s, dst, task))
        return min(cands, key=cost)

# DRL-O
class DRLO:
    name = "DRL-O"
    ACTIONS = ["IoT", "Edge", "Fog", "Cloud"]

    def __init__(self, alpha=0.3, gamma=0.9, eps=0.15, seed=0):
        self.lr, self.df, self.eps = alpha, gamma, eps
        self.rng = np.random.default_rng(seed)
        self.Q = np.zeros((3, len(self.ACTIONS)))   # 3 congestion buckets x 4 actions
        self._last = None

    def _bucket(self, st: State) -> int:
        loads = [st.nodes[j].queue / st.nodes[j].q_max
                 for j in st.layer_idx["Edge"] + st.layer_idx["Fog"]]
        m = float(np.mean(loads)) if loads else 0.0
        return 0 if m < 0.33 else (1 if m < 0.66 else 2)

    def decide(self, st: State, src: int, task) -> int:
        b = self._bucket(st)
        if self.rng.random() < self.eps:
            a = int(self.rng.integers(len(self.ACTIONS)))
        else:
            a = int(np.argmax(self.Q[b]))
        layer = self.ACTIONS[a]
        if layer == "IoT":
            dst = src
        else:
            pool = [j for j in st.layer_idx[layer] if feasible(st.nodes[j], None)]
            dst = min(pool, key=lambda j: st.nodes[j].queue) if pool else src
        # remember (state, action) to update once the reward is known
        self._last = (b, a)
        return dst

    def learn(self, reward: float, st: State):
        if self._last is None:
            return
        b, a = self._last
        nb = self._bucket(st)
        target = reward + self.df * np.max(self.Q[nb])
        self.Q[b, a] += self.lr * (target - self.Q[b, a])

# CFOP
class CFOP:
    name = "CFOP"
    def __init__(self, theta=0.7):
        self.theta = theta

    def decide(self, st: State, src: int, task) -> int:
        def loaded(j):
            return st.nodes[j].queue / st.nodes[j].q_max
        edges = [j for j in st.layer_idx["Edge"] if feasible(st.nodes[j], None)]
        if edges:
            e = min(edges, key=loaded)
            if loaded(e) < self.theta:
                return e
        fogs = [j for j in st.layer_idx["Fog"] if feasible(st.nodes[j], None)]
        if fogs:
            f = min(fogs, key=loaded)
            if loaded(f) < self.theta:
                return f
        cloud = [j for j in st.layer_idx["Cloud"] if feasible(st.nodes[j], None)]
        return cloud[0] if cloud else src


# Registry used by the runner
def all_policies():
    return {
        "QSALB":   QSALB(predict=False),
        "QSALB-P": QSALB(predict=True),     # QSALB with predictive enhancement
        "LEO":     LEO(),
        "GMQ":     GMQ(),
        "LFO":     LFO(),
        "EAO":     EAO(),
        "DRL-O":   DRLO(),
        "CFOP":    CFOP(),
    }
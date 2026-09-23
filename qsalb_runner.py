from __future__ import annotations
import copy
import numpy as np
from qsalb_core import (build_topology, load_tasks, Metrics,
                        transmission_energy, processing_energy)
from qsalb_policies import (State, est_latency, est_energy, comm_ms, wait_ms,
                            proc_ms, hops)


DEFAULT_WEIGHTS = dict(alpha=1.0,    # latency weight  (lambda in paper)
                       beta=0.6,     # energy weight   (phi)
                       gamma=8.0,    # cloud-cost weight(iota)
                       kappa=2.5,    # congestion weight(chi) on drift term
                       eps_pred=0.4) # prediction influence (epsilon)


def run_policy(policy, by_slot, n_slots, topo, weights=DEFAULT_WEIGHTS,
               predict=False, seed=0):
    nodes, layer_idx = topo
    m = Metrics(name=getattr(policy, "name", "policy"))
    m.per_node_load = np.zeros(len(nodes))
    n_nodes = len(nodes)

    pred = np.zeros(n_nodes)
    ewma_beta = 0.5
    cloud_set = set(layer_idx["Cloud"])
    is_drlo = hasattr(policy, "learn")

    for t in range(n_slots):
        arrivals_this_slot = np.zeros(n_nodes)
        st = State(nodes, layer_idx, pred if predict else None, weights)

        # ARRIVAL + OFFLOADING DECISIONS
        for task in by_slot[t]:
            src = task.src_node
            m.deadline_total += 1

            dst = policy.decide(st, src, task)
            dnode, snode = nodes[dst], nodes[src]

            # overflow if destination buffer is full at enqueue time
            if dnode.queue >= dnode.q_max:
                m.overflow_events += 1
                m.deadline_miss += 1            # dropped task misses its deadline
                if is_drlo:
                    policy.learn(-5.0, st)
                continue

            # realized latency estimate at the moment of dispatch
            lat = est_latency(snode, dnode, task)
            m.latencies.append(lat)
            if lat > task.deadline_ms:
                m.deadline_miss += 1

            # energy
            tx = transmission_energy(task.size_mb, hops(snode, dnode)) if src != dst else 0.0
            pe = processing_energy(proc_ms(dnode, task)) if dnode.is_battery else 0.0
            if snode.is_battery:
                snode.energy = max(snode.energy - tx, 0.0)
                m.energy_consumed += tx
            if dnode.is_battery:
                dnode.energy = max(dnode.energy - pe, 0.0)
                m.energy_consumed += pe

            # enqueue
            dnode.queue += 1
            arrivals_this_slot[dst] += 1
            m.per_node_load[dst] += 1
            m.routed_total += 1
            if dst in cloud_set:
                m.cloud_tasks += 1

            # DRL-O
            if is_drlo:
                r = -(lat / 200.0)
                if lat > task.deadline_ms:
                    r -= 2.0
                r -= 0.001 * (tx + pe)
                policy.learn(r, st)

        # (Q_j(t+1) = max(Q_j - mu_j, 0))
        for nd in nodes:
            served = min(nd.mu_max, nd.queue)
            nd.queue = max(nd.queue - nd.mu_max, 0.0)
            m.completed += served

        # 
        pred = ewma_beta * pred + (1 - ewma_beta) * arrivals_this_slot
        total_backlog = sum(nd.queue for nd in nodes)
        m.queue_samples.append(total_backlog)
        m.max_queue = max(m.max_queue, total_backlog)

    return m


def fresh_topo(seed=0, **kw):
    rng = np.random.default_rng(seed)
    return build_topology(rng=rng, **kw)

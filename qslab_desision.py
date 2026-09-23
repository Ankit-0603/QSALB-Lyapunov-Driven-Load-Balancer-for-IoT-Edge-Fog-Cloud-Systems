import sys
import math
import pandas as pd

CSV_IN  = "Multi_Tier_IoT_Resource_Allocation_Dataset.csv"
CSV_OUT = "QSALB_Decisions.csv"

def build_network():
    nodes = []

    # 20 IoT devices
    for i in range(20):
        nodes.append({"name": f"IoT{i+1}",  "layer": "IoT",
                      "speed": 1.0, "mu_max": 1, "q_max": 12,
                      "queue": 0, "energy": 1000.0, "is_battery": True})
        
    # 8 Edge servers 2-3 times faster than IOT
    for i in range(8):
        nodes.append({"name": f"Edge{i+1}", "layer": "Edge",
                      "speed": 2.5, "mu_max": 3, "q_max": 40,
                      "queue": 0, "energy": 8000.0, "is_battery": True})
        
    # 3 Fog servers
    for i in range(3):
        nodes.append({"name": f"Fog{i+1}",  "layer": "Fog",
                      "speed": 5.0, "mu_max": 8, "q_max": 120,
                      "queue": 0, "energy": math.inf, "is_battery": False})
        
    # 1 Cloud
    nodes.append({"name": "Cloud1", "layer": "Cloud",
                  "speed": 10.0, "mu_max": 30, "q_max": 100000,
                  "queue": 0, "energy": math.inf, "is_battery": False})
    return nodes


LINK_LATENCY = {
    ("IoT",  "IoT"):    0.0,  
    ("IoT",  "Edge"):   8.0,
    ("IoT",  "Fog"):   30.0,
    ("IoT",  "Cloud"): 70.0,
    ("Edge", "Edge"):   4.0,
    ("Edge", "Fog"):   18.0,
    ("Edge", "Cloud"): 60.0,
    ("Fog",  "Fog"):    6.0,
    ("Fog",  "Cloud"): 55.0,
}

def get_link_latency(src_layer, dst_layer):
    """Look up the base link delay between two layers."""
    return LINK_LATENCY.get((src_layer, dst_layer),
           LINK_LATENCY.get((dst_layer, src_layer), 40.0))



DEADLINE_MS = {
    "Video Processing": 120.0,   # tight - live video
    "Network Traffic":  150.0,   # tight
    "Image Processing": 300.0,   # medium
    "Data Analytics":   500.0,   # loose
}

def make_task_from_row(row, device_to_index):
    """Convert one CSV row into a task dictionary."""
    return {
        "device"        : row["Device_ID"],
        "src_index"     : device_to_index[row["Device_ID"]],   # 0..19
        "workload"      : row["Workload_Type"],
        "exec_ms"       : float(row["Task_Execution_Time(ms)"]),
        "size_mb"       : float(row["Memory_Usage(MB)"]) / 1024.0,
        "net_latency"   : float(row["Network_Latency(ms)"]),
        "jitter"        : float(row["Jitter(ms)"]),
        "deadline"      : DEADLINE_MS.get(row["Workload_Type"], 300.0),
    }


#Delay and Energy

def processing_time(node, task):
    """T_proc = c_k / f_j   (Eq. 3.3): compute time depends on node speed."""
    return task["exec_ms"] / node["speed"]

def waiting_time(node, task):
    """T_wait = Q_j / (mu_j + epsilon)  * proc_time (Eq. 3.4).
    Estimates how long this task will wait in the destination's queue."""
    return (node["queue"] / (node["mu_max"] + 0.001)) * processing_time(node, task)

def communication_delay(src_node, dst_node, task):
    """T_comm = link_latency + net_latency + jitter (Eq. 3.2/4.2).
    Zero if executed locally on the source device."""
    if src_node["name"] == dst_node["name"]:
        return 0.0
    return get_link_latency(src_node["layer"], dst_node["layer"]) \
           + task["net_latency"] + task["jitter"]

def total_latency(src_node, dst_node, task):
    """End-to-end delay = communication + waiting + processing (Eq. 3.6)."""
    return communication_delay(src_node, dst_node, task) \
         + waiting_time(dst_node, task) \
         + processing_time(dst_node, task)

def energy_cost(src_node, dst_node, task):
    """Battery energy charged for this decision (Eq. 3.8).
    Transmission: 0.55 J per MB per hop. Processing: 0.012 J per ms."""
    layer_order = {"IoT": 0, "Edge": 1, "Fog": 2, "Cloud": 3}
    if src_node["name"] == dst_node["name"]:
        hops = 0
    else:
        hops = max(1, abs(layer_order[dst_node["layer"]] - layer_order[src_node["layer"]]))
    e_tx   = 0.55  * task["size_mb"] * hops if hops > 0 else 0.0
    e_proc = 0.012 * processing_time(dst_node, task) if dst_node["is_battery"] else 0.0
    return e_tx + e_proc



# THE QSALB DRIFT-PLUS-PENALTY RULE (Eq. 3.11/4.10)


# ALPHA = 1.0    # latency weight
# BETA  = 0.6    # energy weight
# GAMMA = 8.0    # cloud-cost weight
# KAPPA = 2.5    # congestion (drift) weight

ALPHA = 0.083
BETA  = 0.050
GAMMA = 0.661
KAPPA = 0.207

def is_feasible(node, task):
    #node will accept the tast if there is battery left
    if node["queue"] >= node["q_max"]:
        return False
    if node["is_battery"] and node["energy"] <= 50.0:
        return False
    return True

def qsalb_decide(nodes, src_index, task, verbose=False):
#Returns the index of the chosen destination node, and the details of the scoring for every candidate (to display).
    src_node = nodes[src_index]

    candidates = [src_index]
    candidates += [i for i, n in enumerate(nodes) if n["layer"] == "Edge"]
    candidates += [i for i, n in enumerate(nodes) if n["layer"] == "Fog"]
    candidates += [i for i, n in enumerate(nodes) if n["layer"] == "Cloud"]

    best_score = math.inf
    best_index = src_index
    all_scores = []            # for display

    for j in candidates:
        dst_node = nodes[j]

        if not is_feasible(dst_node, task):
            all_scores.append({"node": dst_node["name"], "layer": dst_node["layer"],
                               "score": None, "reason": "infeasible"})
            continue


        drift_term    = dst_node["queue"] - src_node["queue"]  #(Eq. 4.11)
        latency_term  = total_latency(src_node, dst_node, task)
        energy_term   = energy_cost(src_node, dst_node, task)
        cloud_term    = 1.0 if dst_node["layer"] == "Cloud" else 0.0

        #( Eq. 3.11 / 4.10) 
        score = (KAPPA * drift_term
               + ALPHA * latency_term
               + BETA  * energy_term
               + GAMMA * cloud_term)

        all_scores.append({
            "node": dst_node["name"], "layer": dst_node["layer"],
            "drift": drift_term, "latency": latency_term,
            "energy": energy_term, "cloud": cloud_term,
            "score": score, "reason": None,
        })

        if score < best_score:
            best_score = score
            best_index = j

    return best_index, all_scores

#decision for all tasks

# def leo_decide(nodes, src_index, task):
#     return src_index

def main():
    n_show = 1000
    show_details = False
    if len(sys.argv) > 1:
        try:
            n_show = int(sys.argv[1])
        except ValueError:
            n_show = 1000
    if len(sys.argv) > 2 and sys.argv[2].lower() == "details":
        show_details = True

    #read dataset
    df = pd.read_csv(CSV_IN)
    print(f"\nLoaded {len(df)} tasks from {CSV_IN}\n")

    # mapping devices
    device_list = sorted(df["Device_ID"].unique(), key=lambda x: int(x[1:]))
    device_to_index = {d: i for i, d in enumerate(device_list)}

    nodes = build_network()

#processing tasks
    print("=" * 110)
    print(f"  QSALB TASK-BY-TASK DECISIONS  (showing {min(n_show, len(df))} of {len(df)} tasks)")
    print("=" * 110)
    print(f"{'#':>4} | {'Device':>6} | {'Workload':<17} | {'Path':<18} | "
          f"{'Dest.':<7} | {'Proc':>6} | {'Comm':>6} | {'Wait':>6} | "
          f"{'Latency':>8} | {'Deadline':>8} | {'Met':<3}")
    print("-" * 110)

    results = []
    tier_counts = {"IoT": 0, "Edge": 0, "Fog": 0, "Cloud": 0}
    deadlines_met = 0

    for idx, row in df.iterrows():
        task = make_task_from_row(row, device_to_index)
        src_index = task["src_index"]

        # dst_index = leo_decide(nodes, src_index, task) #for LEO
        dst_index, all_scores = qsalb_decide(nodes, src_index, task)

        src_node = nodes[src_index]
        dst_node = nodes[dst_index]


        proc = processing_time(dst_node, task)
        comm = communication_delay(src_node, dst_node, task)
        wait = waiting_time(dst_node, task)
        total = proc + comm + wait
        met = total <= task["deadline"]


        if src_index == dst_index:
            path = f"{src_node['layer']} (local)"
        else:
            path = f"{src_node['layer']} -> {dst_node['layer']}"

        tier_counts[dst_node["layer"]] += 1
        if met:
            deadlines_met += 1

        # Printing decisions
        if idx < n_show:
            print(f"{idx+1:>4} | {task['device']:>6} | {task['workload']:<17} | "
                  f"{path:<18} | {dst_node['name']:<7} | {proc:>6.1f} | {comm:>6.1f} | "
                  f"{wait:>6.1f} | {total:>8.1f} | {task['deadline']:>8.0f} | "
                  f"{'YES' if met else 'NO':<3}")

            if show_details:
                print("       Candidate scores (lower = better):")

            #FOR LEO
            # if show_details:
            #     print("\nDecision Reason:")
            #     print("Local Execution Only (LEO)")

                for cs in all_scores:
                    if cs["score"] is None:
                        print(f"         {cs['node']:<7} ({cs['layer']:<5})  [infeasible]")
                    else:
                        winner = "  <-- CHOSEN" if cs["node"] == dst_node["name"] else ""
                        print(f"         {cs['node']:<7} ({cs['layer']:<5}) "
                              f"drift={cs['drift']:>6.2f}  latency={cs['latency']:>6.2f}  "
                              f"energy={cs['energy']:>5.2f}  cloud={cs['cloud']:>3.1f}  "
                              f"|  SCORE = {cs['score']:>7.2f}{winner}")
                print()

        # Trying to print CSV
        results.append({
            "Task_Number":     idx + 1,
            "Device_ID":       task["device"],
            "Workload_Type":   task["workload"],
            "Source_Node":     src_node["name"],
            "Destination_Node": dst_node["name"],
            "Destination_Layer": dst_node["layer"],
            "Offloading_Path": path,
            "Processing_Time_ms":  round(proc, 2),
            "Communication_ms":    round(comm, 2),
            "Queue_Wait_ms":       round(wait, 2),
            "Total_Latency_ms":    round(total, 2),
            "Deadline_ms":         task["deadline"],
            "Deadline_Met":        "Yes" if met else "No",
        })

        if dst_node["queue"] < dst_node["q_max"]:
            dst_node["queue"] += 1

        if (idx + 1) % 20 == 0:
            for n in nodes:
                n["queue"] = max(n["queue"] - n["mu_max"], 0)

    print("-" * 110)

    # saving csv for output
    pd.DataFrame(results).to_csv(CSV_OUT, index=False)

    # all the other datas
    total = len(df)
    print(f"\n{'='*70}")
    print(f"  SUMMARY OF QSALB DECISIONS FOR ALL {total} TASKS")
    print(f"{'='*70}")
    print("\n  Tasks processed per layer (where QSALB sent them):\n")
    for layer in ["IoT", "Edge", "Fog", "Cloud"]:
        c = tier_counts[layer]
        pct = 100 * c / total
        bar = "#" * int(pct / 2)
        print(f"    {layer:>6}:  {c:>5} tasks  ({pct:5.1f}%)  {bar}")
    print(f"\n  Deadlines met:    {deadlines_met:>5}  ({100*deadlines_met/total:.1f}%)")
    print(f"  Deadlines missed: {total-deadlines_met:>5}  ({100*(total-deadlines_met)/total:.1f}%)")
    print(f"\n  Full per-task results saved to: {CSV_OUT}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
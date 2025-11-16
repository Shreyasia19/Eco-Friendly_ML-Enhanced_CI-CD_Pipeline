#!/usr/bin/env python3

import os, time, json, random, math
import requests
from kubernetes import client, config, utils

# ---------------- CONFIG ----------------
PROM_URL = os.environ.get("PROM_URL", "http://127.0.0.1:9090")
NAMESPACE = os.environ.get("NAMESPACE", "default")
DEPLOYMENT = os.environ.get("DEPLOYMENT", "eco-ci-app")
PUSHGATEWAY = os.environ.get("PUSHGATEWAY_URL", "http://127.0.0.1:9091")
KUBECONFIG = os.environ.get("KUBECONFIG", None)

ALPHA = float(os.environ.get("ALPHA", 0.7))  # weight for build duration
BETA  = float(os.environ.get("BETA", 0.3))   # weight for CPU

SPACE = {
    "replicas": (1, 4),
    "cpu_request": (0.1, 0.5),
    "concurrency": (1, 4)
}

POP_SIZE = 8
MAX_ITERS = 12

# ---------------- PROMETHEUS HELPERS ----------------
def prometheus_query(query):
    """Query Prometheus and return JSON results with retry + longer timeout"""
    url = PROM_URL.rstrip("/") + "/api/v1/query"
    for attempt in range(3):
        try:
            r = requests.get(url, params={"query": query}, timeout=30)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "success":
                return data["data"]["result"]
        except Exception as e:
            print(f"⚠️ Prometheus query failed (try {attempt+1}/3): {e}")
            time.sleep(3)
    print("❌ Prometheus query failed after 3 attempts.")
    return None

def get_metric_scalar(query):
    res = prometheus_query(query)
    if not res:
        return None
    vals = []
    for entry in res:
        try:
            vals.append(float(entry["value"][1]))
        except:
            pass
    return sum(vals) / len(vals) if vals else None

def fetch_current_metrics():
    bd_q = 'avg_over_time(ci_build_duration_seconds[30m])'
    cpu_q = f'avg(rate(container_cpu_usage_seconds_total{{pod=~"{DEPLOYMENT}.*"}}[1m]))'
    mem_q = f'avg_over_time(container_memory_usage_bytes{{pod=~"{DEPLOYMENT}.*"}}[30m])'

    build_dur = get_metric_scalar(bd_q) or 300.0
    cpu = get_metric_scalar(cpu_q) or 0.5
    mem = get_metric_scalar(mem_q) or 0.0

    return {"build_duration": build_dur, "cpu": cpu, "memory": mem}

# ---------------- OBJECTIVE FUNCTION ----------------
def normalize(val, lo, hi):
    return 0.0 if hi == lo else (val - lo) / (hi - lo)

def objective_from_metrics(metrics, hist_ranges):
    dur_n = normalize(metrics["build_duration"], *hist_ranges["build_duration"])
    cpu_n = normalize(metrics["cpu"], *hist_ranges["cpu"])
    return ALPHA * dur_n + BETA * cpu_n

# ---------------- KUBERNETES HELPERS ----------------
def k8s_client():
    try:
        config.load_incluster_config()
        print("✅ Loaded in-cluster config")
    except:
        config.load_kube_config()
        print("✅ Loaded local kubeconfig")
    return client.AppsV1Api()

def patch_deployment_params(api, replicas, cpu_request):
    body = {
        "spec": {
            "replicas": int(replicas),
            "template": {
                "spec": {
                    "containers": [{
                        "name": DEPLOYMENT,
                        "resources": {"requests": {"cpu": str(cpu_request)}}
                    }]
                }
            }
        }
    }
    api.patch_namespaced_deployment(name=DEPLOYMENT, namespace=NAMESPACE, body=body)
    print(f"🔧 Patched deployment: replicas={replicas}, cpu_request={cpu_request:.3f}")

# ---------------- OPTIMIZATION LOOP ----------------
def mbo_optimize():
    hist_ranges = {"build_duration": (50, 900), "cpu": (0.01, 2.0)}
    api = k8s_client()

    # --- Initial population ---
    pop = [
        {
            "replicas": random.randint(*SPACE["replicas"]),
            "cpu": random.uniform(*SPACE["cpu_request"]),
            "concurrency": random.randint(*SPACE["concurrency"])
        }
        for _ in range(POP_SIZE)
    ]

    evaluated = []
    for ind in pop:
        patch_deployment_params(api, ind["replicas"], ind["cpu"])
        time.sleep(8)
        m = fetch_current_metrics()
        score = objective_from_metrics(m, hist_ranges)
        evaluated.append((ind, score, m))
        print("Init eval:", ind, f"→ score={score:.4f}", m)

    best = min(evaluated, key=lambda x: x[1])
    print(f"🏁 Initial best: {best[0]} → {best[1]:.4f}")

    # --- Iterative optimization ---
    for it in range(MAX_ITERS):
        print(f"\n=== Iteration {it+1}/{MAX_ITERS} ===")
        new_pop = []
        for ind, _, _ in evaluated:
            cand = ind.copy()
            cand["replicas"] = max(SPACE["replicas"][0],
                                   min(SPACE["replicas"][1], cand["replicas"] + random.choice([-1, 0, 1])))
            cand["cpu"] = max(SPACE["cpu_request"][0],
                              min(SPACE["cpu_request"][1], cand["cpu"] * (1 + random.uniform(-0.2, 0.2))))
            cand["concurrency"] = max(SPACE["concurrency"][0],
                                      min(SPACE["concurrency"][1], cand["concurrency"] + random.choice([-1, 0, 1])))
            new_pop.append(cand)

        new_evaluated = []
        for ind in new_pop:
            patch_deployment_params(api, ind["replicas"], ind["cpu"])
            time.sleep(8)
            m = fetch_current_metrics()
            score = objective_from_metrics(m, hist_ranges)
            new_evaluated.append((ind, score, m))
            print("Eval:", ind, f"→ score={score:.4f}", m)

        combined = evaluated + new_evaluated
        combined.sort(key=lambda x: x[1])
        evaluated = combined[:POP_SIZE]
        if evaluated[0][1] < best[1]:
            best = evaluated[0]
            print("🌟 New best found:", best[0], f"→ {best[1]:.4f}")

    # --- Final result ---
    print("\n✅ Optimization finished.")
    print(f"🏆 Best configuration → replicas={best[0]['replicas']}, cpu={best[0]['cpu']:.3f}")
    print(f"📈 Best objective score = {best[1]:.4f}")

    # Optional: push to Pushgateway
    if PUSHGATEWAY:
        try:
            payload = f"# TYPE mbo_best objective\nmbo_best{{}} {best[1]}\n"
            requests.post(PUSHGATEWAY + "/metrics/job/mbo", data=payload)
            print(f"📤 Pushed final score to Pushgateway at {PUSHGATEWAY}")
        except Exception as e:
            print(f"⚠️ Could not push to Pushgateway: {e}")

    return best

if __name__ == "__main__":
    res = mbo_optimize()
    print("\nOptimizer finished successfully:", res)

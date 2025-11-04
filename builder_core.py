# builder_core.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, Any, List, Optional, Tuple

from kernel import Graph, Evaluator, EvalParams, Metrics
from rules_pgr_base import upsert_threshold_guard
from search import search, SearchConfig
from compiler import compile_rules_from_pgr, CompileContext

# ---------- Types & hooks ----------

# A golden task = (initial graph, evaluator params)
GoldenTask = Tuple[Graph, EvalParams]

# Domain hook: returns a list of golden tasks
GoldenSuiteFn = Callable[[], List[GoldenTask]]

# Domain hook: provenance miner -> list of numeric samples (e.g., candidate thresholds)
# The "steps" are Provenance.steps: [{ "rule": str, "metrics": {cost, feasible, extras{...}} }, ...]
ProvenanceMiner = Callable[[List[Dict[str, Any]]], List[float]]

# Acceptance policy: given aggregates before/after, decide True/False
AcceptPolicy = Callable[[Dict[str, Any], Dict[str, Any]], bool]

@dataclass
class GuardEditSpec:
    """What guard to upsert (generic P/G/R schema fields)."""
    rule_name: str
    var: str
    key: str
    op: str = "<"
    epsilon: float = 0.0   # small margin to add to the chosen threshold

# ---------- Generic utilities ----------

def reduce_threshold(samples: List[float], epsilon: float = 0.0, reducer: str = "median") -> Optional[float]:
    if not samples:
        return None
    if reducer == "median":
        import statistics
        t = statistics.median(samples)
    elif reducer == "mean":
        t = sum(samples) / len(samples)
    else:
        raise ValueError(f"Unknown reducer: {reducer}")
    return float(t) + float(epsilon)

def run_golden_suite(
    rules: List, evaluator: Evaluator, suite: List[GoldenTask], cfg: SearchConfig
) -> List[Metrics]:
    out: List[Metrics] = []
    for g0, ep in suite:
        best_g, best_m, _ = search(g0, rules, evaluator, ep, cfg)
        out.append(best_m)
    return out

def aggregate_metrics(results: List[Metrics]) -> Dict[str, Any]:
    if not results:
        return {"feasible_count": 0, "avg_cost": float("inf"), "n": 0}
    feas = sum(1 for r in results if r.feasible)
    avg_cost = sum(r.cost for r in results) / len(results)
    return {"feasible_count": feas, "avg_cost": avg_cost, "n": len(results)}

def default_accept_policy(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    # Accept if feasibility count increases OR avg_cost drops by a meaningful margin
    return (after["feasible_count"] > before["feasible_count"]) or (after["avg_cost"] <= before["avg_cost"] - 1.0)

# ---------- Main routine ----------

def propose_and_eval_guard(
    rg: Graph,
    compile_ctx: CompileContext,
    evaluator: Evaluator,
    golden_suite_fn: GoldenSuiteFn,
    miner: ProvenanceMiner,
    guard_spec: GuardEditSpec,
    cfg: SearchConfig,
    reducer: str = "median",
    accept_policy: AcceptPolicy = default_accept_policy,
):
    """
    1) Compile current rule-graph → rules
    2) On the first golden task, run search & collect provenance
    3) Mine provenance → threshold samples → pick threshold
    4) Evaluate golden suite before/after applying guard → accept?
    Returns: (threshold, accepted_flag, provenance, agg_before, agg_after)
    """
    # Compile current rules
    rules0 = compile_rules_from_pgr(rg, compile_ctx)

    # Gather provenance from the first task
    suite = golden_suite_fn()
    if not suite:
        raise ValueError("Golden suite is empty.")
    g0, ep0 = suite[0]
    _, _, prov = search(g0, rules0, evaluator, ep0, cfg)

    # Mine threshold candidates
    samples = miner(prov.steps)
    threshold = reduce_threshold(samples, epsilon=guard_spec.epsilon, reducer=reducer)
    if threshold is None:
        return None, None, prov, None, None

    # Evaluate before
    res_before = run_golden_suite(rules0, evaluator, suite, cfg)
    agg_before = aggregate_metrics(res_before)

    # Apply guard edit
    upsert_threshold_guard(
        rg,
        rule_name=guard_spec.rule_name,
        var=guard_spec.var,
        key=guard_spec.key,
        op=guard_spec.op,
        value=threshold,
    )

    # Recompile and evaluate after
    rules1 = compile_rules_from_pgr(rg, compile_ctx)
    res_after = run_golden_suite(rules1, evaluator, suite, cfg)
    agg_after = aggregate_metrics(res_after)

    accepted = accept_policy(agg_before, agg_after)
    return threshold, accepted, prov, agg_before, agg_after


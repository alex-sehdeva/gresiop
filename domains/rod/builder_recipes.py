# domains/rod/builder_recipes.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from kernel import Graph, EvalParams
from builder_core import GuardEditSpec, GoldenSuiteFn, ProvenanceMiner

# --- Guard spec: only increase length when x.length < max_len ---
ROD_LEN_GUARD = GuardEditSpec(
    rule_name="IncreaseLength",
    var="x",
    key="length",
    op="<",
    epsilon=0.05,
)

# --- Provenance miner: look for IncreaseLength(...) steps that improved cost and extract prevL ---
def rod_prevL_miner(steps: List[Dict[str, Any]]) -> List[float]:
    out: List[float] = []
    prev_cost = None
    for s in steps:
        rule = s.get("rule", "")
        m = s.get("metrics", {})
        cost = m.get("cost", None)
        if cost is None:
            continue
        improved = (prev_cost is not None) and (prev_cost - cost > 0)
        prev_cost = cost
        if improved and rule.startswith("IncreaseLength(") and "prevL=" in rule:
            try:
                frag = rule.split("prevL=")[1]
                prevL = float(frag.split(")")[0])
                out.append(prevL)
            except Exception:
                pass
    return out

# --- Golden suite for rods (tiny factory) ---
def make_initial_rod(len1=1.0, th1=0.8, mat1="aluminum") -> Graph:
    g=Graph(); g.add_node("rod","Assembly",name="rod-1")
    g.add_node("seg1","Segment",length=float(len1),thickness=float(th1),material=mat1); g.add_edge("rod","has","seg1")
    return g

def golden_suite_rod() -> List[Tuple[Graph, EvalParams]]:
    # Note: if your EvalParams is a RodParams subclass, import it and use that here.
    return [
        (make_initial_rod(1.0,0.8,"aluminum"), EvalParams(extras={"load":10.0})),
        (make_initial_rod(1.2,0.7,"aluminum"), EvalParams(extras={"load":9.0})),
        (make_initial_rod(0.8,0.9,"steel"),    EvalParams(extras={"load":11.0})),
        (make_initial_rod(1.5,0.6,"aluminum"), EvalParams(extras={"load":10.0})),
    ]

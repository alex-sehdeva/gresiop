# eval_rod.py (example domain)
from dataclasses import dataclass
from typing import Dict, Any
from kernel import Graph, Evaluator, EvalParams, Metrics

@dataclass
class RodParams(EvalParams):
    target_length: float = 4.0
    stress_limit: float = 1.0
    lam_len: float = 30.0
    lam_str: float = 30.0
    materials: Dict[str, Dict[str, float]] = None  # {"aluminum":{"density":1.0,"strength":1.0}, ...}

class RodEvaluator(Evaluator):
    def evaluate(self, g: Graph, p: RodParams) -> Metrics:
        mats = p.materials or {"aluminum":{"density":1.0,"strength":1.0},
                               "steel":{"density":2.6,"strength":2.2}}
        length=weight=strength=0.0
        for nid in g.find("Segment"):
            pr = g.props(nid)
            L = float(pr["length"]); T = float(pr["thickness"]); M = pr["material"]
            length += L
            weight += L*T*mats[M]["density"]
            strength += T*mats[M]["strength"]
        stress = p.extras.get("load", 10.0) / max(strength, 1e-6)
        feasible = (length >= p.target_length) and (stress <= p.stress_limit)
        penalty = p.lam_len*max(0.0, p.target_length - length) + p.lam_str*max(0.0, stress - p.stress_limit)
        cost = weight + 0.5*stress + 0.05*len(g.find("Segment")) + penalty
        return Metrics(cost=cost, feasible=feasible, extras={"length":length, "stress":stress, "weight":weight})


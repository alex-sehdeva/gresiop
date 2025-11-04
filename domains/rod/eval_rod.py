# domains/rod/eval_rod.py
from dataclasses import dataclass
from typing import Dict, Any
from kernel import Graph, Evaluator, EvalParams, Metrics

@dataclass
class RodParams(EvalParams):
    target_length: float = 4.0
    stress_limit: float = 1.0
    lam_len: float = 30.0
    lam_str: float = 30.0
    materials: Dict[str, Dict[str, float]] | None = None  # {"aluminum":{"density":...,"strength":...}, ...}

class RodEvaluator(Evaluator):
    def evaluate(self, g: Graph, p: EvalParams) -> Metrics:
        # robust to EvalParams or RodParams
        mats = getattr(p, "materials", None) or {
            "aluminum": {"density": 1.0, "strength": 1.0},
            "steel":    {"density": 2.6, "strength": 2.2},
        }
        target_length = getattr(p, "target_length", 4.0)
        stress_limit  = getattr(p, "stress_limit", 1.0)
        lam_len       = getattr(p, "lam_len", 30.0)
        lam_str       = getattr(p, "lam_str", 30.0)
        load          = (getattr(p, "extras", {}) or {}).get("load", 10.0)

        length = weight = strength = 0.0
        for nid in g.find("Segment"):
            pr = g.props(nid)
            L = float(pr["length"]); T = float(pr["thickness"]); M = pr["material"]
            length  += L
            weight  += L * T * mats[M]["density"]
            strength+= T * mats[M]["strength"]

        stress   = load / max(strength, 1e-6)
        feasible = (length >= target_length) and (stress <= stress_limit)
        penalty  = lam_len * max(0.0, target_length - length) + lam_str * max(0.0, stress - stress_limit)
        cost     = weight + 0.5 * stress + 0.05 * len(g.find("Segment")) + penalty

        return Metrics(cost=cost, feasible=feasible, extras={"length": length, "stress": stress, "weight": weight})


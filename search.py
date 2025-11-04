from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List, Tuple, Optional
import json, random

from kernel import Graph, RuleFn, RuleResult, EvalParams, Evaluator, Metrics

# ---------------------------
# Provenance
# ---------------------------

@dataclass
class Provenance:
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, desc: str, metrics: Metrics) -> None:
        # Store a JSONable dict (avoid dataclass objects directly)
        self.steps.append({
            "rule": desc,
            "metrics": {
                "cost": metrics.cost,
                "feasible": metrics.feasible,
                "extras": dict(metrics.extras or {})
            }
        })

    def dump(self, path: str) -> None:
        with open(path, "w") as f:
            for i, s in enumerate(self.steps):
                f.write(f"Step {i+1}: {s['rule']}\n")
                f.write(json.dumps(s["metrics"], indent=2) + "\n\n")


# ---------------------------
# Hooks & Config
# ---------------------------

# Map a graph to a dedup/novelty signature
SignatureFn = Callable[[Graph], str]

# Score a candidate using its Metrics (lower is better)
Scorer = Callable[[Metrics], float]

# Stopping predicate given the current best Metrics
StopPredicate = Callable[[Metrics], bool]

@dataclass
class SearchConfig:
    iters: int = 120
    beam_width: int = 16
    random_perturb: float = 0.02
    novelty_bonus: float = 0.30          # subtract this if graph is novel
    dedupe_beam: bool = True             # keep at most one per signature in a beam step
    seed: Optional[int] = None           # set for reproducibility
    # Optional hooks (defaults provided below)
    signature_fn: Optional[SignatureFn] = None
    scorer: Optional[Scorer] = None
    stop_pred: Optional[StopPredicate] = None


# ---------------------------
# Default hooks (domain-free)
# ---------------------------

def default_signature_fn(g: Graph) -> str:
    # Use the kernel’s canonical, order-insensitive hash
    return g.signature()

def default_scorer(m: Metrics) -> float:
    return m.cost

def default_stop_pred(m: Metrics) -> bool:
    # Domain-free: stop when the evaluator says it's feasible
    return bool(m.feasible)


# ---------------------------
# Search
# ---------------------------

def search(
    initial: Graph,
    rules: List[RuleFn],
    evaluator: Evaluator,
    params: EvalParams,
    cfg: SearchConfig
) -> Tuple[Graph, Metrics, Provenance]:
    """
    Generic beam search with novelty bonus and memoized evaluations.

    - signature_fn: controls dedup/novelty (default: Graph.signature()).
    - scorer: maps Metrics -> float (lower is better; default: cost).
    - stop_pred: early stop when True on current best (default: feasible).
    """
    # Wire defaults
    signature_fn = cfg.signature_fn or default_signature_fn
    scorer       = cfg.scorer       or default_scorer
    stop_pred    = cfg.stop_pred    or default_stop_pred

    if cfg.seed is not None:
        random.seed(cfg.seed)

    prov = Provenance()
    seen_signatures: set[str] = set()
    memo: Dict[str, Metrics] = {}

    def score_tuple(g: Graph, m: Metrics, desc: str):
        sig = signature_fn(g)
        novelty = cfg.novelty_bonus * (0 if sig in seen_signatures else 1)
        return (scorer(m) - novelty + cfg.random_perturb * random.random(), g, m, desc, sig)

    # Seed beam
    m0 = evaluator.evaluate(initial, params)
    beam: List[Tuple[float, Graph, Metrics, str, str]] = [score_tuple(initial, m0, "init")]
    prov.log("init", m0)
    best = beam[0]

    # Main loop
    for _ in range(cfg.iters):
        candidates: List[Tuple[float, Graph, Metrics, str, str]] = []

        for _, g, _, _, _ in beam:
            for r in rules:
                results = r(g)
                for rr in results:
                    sig = signature_fn(rr.new_graph)
                    if sig in memo:
                        m = memo[sig]
                    else:
                        m = evaluator.evaluate(rr.new_graph, params)
                        memo[sig] = m
                    candidates.append(score_tuple(rr.new_graph, m, rr.desc))

        if not candidates:
            break

        # Rank and select next beam
        candidates.sort(key=lambda t: t[0])

        next_beam: List[Tuple[float, Graph, Metrics, str, str]] = []
        if cfg.dedupe_beam:
            sigs_next: set[str] = set()
            for c in candidates:
                if c[4] in sigs_next:
                    continue
                next_beam.append(c)
                sigs_next.add(c[4])
                if len(next_beam) >= cfg.beam_width:
                    break
            seen_signatures |= sigs_next
        else:
            next_beam = candidates[:cfg.beam_width]
            seen_signatures |= {c[4] for c in next_beam}

        beam = next_beam
        b0 = beam[0]
        if b0[2].cost < best[2].cost:
            best = b0

        # Log the current best of this iteration
        prov.log(b0[3], b0[2])

        # Early stop if satisfied
        if stop_pred(best[2]):
            break

    # Return best graph/metrics and full provenance
    return best[1], best[2], prov


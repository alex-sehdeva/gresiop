from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Callable, Protocol, Mapping, Optional
import json
import hashlib

# ---------------------------
# Graph: minimal & general
# ---------------------------

class Graph:
    """
    A tiny, typed property graph:
      - nodes: id -> {"type": <str>, "props": {…}}
      - edges: (src_id, edge_type, dst_id)
    This is intentionally small so the same object can represent
    both artifacts and rewrite rules.
    """
    def __init__(self) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str, str]] = []

    # CRUD
    def add_node(self, nid: str, ntype: str, **props: Any) -> None:
        self.nodes[nid] = {"type": ntype, "props": dict(props)}

    def add_edge(self, src: str, etype: str, dst: str) -> None:
        self.edges.append((src, etype, dst))

    def has_node(self, nid: str) -> bool:
        return nid in self.nodes

    def find(self, ntype: str) -> List[str]:
        """All node ids whose node['type'] == ntype."""
        return [nid for nid, n in self.nodes.items() if n["type"] == ntype]

    def props(self, nid: str) -> Dict[str, Any]:
        return self.nodes[nid]["props"]

    def set_props(self, nid: str, **updates: Any) -> None:
        self.nodes[nid]["props"].update(updates)

    def neighbors(self, nid: str, etype: Optional[str] = None) -> List[str]:
        """Outbound neighbors via edges of type etype (or all types if None)."""
        if etype is None:
            return [dst for src, _, dst in self.edges if src == nid]
        return [dst for src, e, dst in self.edges if src == nid and e == etype]

    def clone(self) -> "Graph":
        g = Graph()
        g.nodes = {k: {"type": v["type"], "props": dict(v["props"])} for k, v in self.nodes.items()}
        g.edges = list(self.edges)
        return g

    # IO / signatures
    def to_json(self) -> Dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges}

    @staticmethod
    def from_json(obj: Mapping[str, Any]) -> "Graph":
        g = Graph()
        g.nodes = {k: {"type": v["type"], "props": dict(v["props"])} for k, v in obj["nodes"].items()}
        g.edges = [tuple(e) for e in obj["edges"]]
        return g

    def signature(self) -> str:
        """
        Canonical, order-insensitive hash of node types/props and edges.
        Useful for memoization/novelty in search. Avoids domain assumptions.
        """
        node_tuples = []
        for nid in sorted(self.nodes):
            n = self.nodes[nid]
            # sort props for stability
            props_tuple = tuple(sorted((k, _jsonish(v)) for k, v in n["props"].items()))
            node_tuples.append((nid, n["type"], props_tuple))
        edge_tuples = sorted(self.edges)
        payload = json.dumps({"n": node_tuples, "e": edge_tuples}, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _jsonish(v: Any) -> Any:
    """Make values JSON-stable for signatures (tuples→lists, sets→sorted lists, etc.)."""
    if isinstance(v, dict):
        return {k: _jsonish(v2) for k, v2 in sorted(v.items())}
    if isinstance(v, (list, tuple)):
        return [_jsonish(x) for x in v]
    if isinstance(v, set):
        return [_jsonish(x) for x in sorted(v)]
    return v


# ---------------------------
# Rules (domain-agnostic)
# ---------------------------

@dataclass
class RuleResult:
    new_graph: Graph
    desc: str  # human/debug string (provenance)

# A rule takes a graph and returns zero or more candidate graphs.
RuleFn = Callable[[Graph], List[RuleResult]]


# ---------------------------
# Evaluator interface
# ---------------------------

@dataclass
class Metrics:
    """
    Minimal evaluator output. 'extras' can carry domain fields
    (e.g., {"length":…, "stress":…} or {"latency_ms":…, "sla_viol":…}).
    """
    cost: float
    feasible: bool
    extras: Dict[str, Any] = field(default_factory=dict)


class Evaluator(Protocol):
    """
    Plug-in interface for domain scoring. Implement evaluate(graph, params)→Metrics.
    """
    def evaluate(self, g: Graph, params: "EvalParams") -> Metrics: ...


@dataclass
class EvalParams:
    """
    Free-form parameter bag for the evaluator (targets, weights, penalties, etc.).
    Keep this generic; domain modules subclass/extend as needed.
    """
    # You can keep arbitrary keys in `extras` to avoid kernel churn.
    extras: Dict[str, Any] = field(default_factory=dict)


# ---------------------------
# Default no-op evaluator
# ---------------------------

class NullEvaluator:
    """
    Safe default: everything is 'feasible' and zero-cost.
    Useful for wiring tests and for problems where you only care about structure
    and will compute costs elsewhere.
    """
    def evaluate(self, g: Graph, params: EvalParams) -> Metrics:
        return Metrics(cost=0.0, feasible=True, extras={})


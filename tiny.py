# Minimal "builder" kernel in ~250 lines
# (G, R, E, S, IO, P): Graph, Rules, Evaluator, Search, IO(SVG), Provenance
#
# Toy domain: build a rod by composing segments to reach a target length
# while keeping stress under a limit given a load. Rules modify the graph;
# evaluator computes metrics; search picks the next rewrite greedily with
# a small beam. Provenance keeps full steps.
#
# Files produced:
# - /mnt/data/rod.svg               (simple drawing of the best design)
# - /mnt/data/provenance.txt        (human-readable provenance log)
# - /mnt/data/best_design.json      (graph JSON of the best design)
#
# You can rerun/modify the parameters at the bottom.

from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Callable, Optional
import json
import math
import random

# -------------------------------
# G: Very small typed-graph store
# -------------------------------

class Graph:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}  # id -> {type, props}
        self.edges: List[Tuple[str, str, str]] = [] # (src, type, dst)

    def add_node(self, nid: str, ntype: str, **props):
        self.nodes[nid] = {"type": ntype, "props": dict(props)}

    def add_edge(self, src: str, etype: str, dst: str):
        self.edges.append((src, etype, dst))

    def find(self, ntype: str) -> List[str]:
        return [nid for nid, n in self.nodes.items() if n["type"] == ntype]

    def clone(self) -> "Graph":
        g = Graph()
        g.nodes = {k: {"type": v["type"], "props": dict(v["props"])} for k, v in self.nodes.items()}
        g.edges = list(self.edges)
        return g

    def to_json(self) -> Dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges}

# ----------------------------------------
# IO: Minimal SVG emitter for the rod model
# ----------------------------------------

def export_svg_rod(g: Graph, path: str):
    # Layout: draw segments in a row from x=0
    segments = []
    for nid in g.find("Segment"):
        p = g.nodes[nid]["props"]
        segments.append((nid, p["length"], p["thickness"], p["material"]))
    # sort for stable layout (by id)
    segments.sort(key=lambda t: t[0])
    x = 10
    y = 40
    hscale = 80  # length to pixels
    vscale = 12  # thickness to pixels
    width = 40 + int(sum(s[1] for s in segments) * hscale)
    height = 120

    def mat_color(m):
        return {"aluminum": "#9bb7d4", "steel": "#666666"}.get(m, "#cccccc")

    rects = []
    for _, length, thick, mat in segments:
        w = length * hscale
        h = thick * vscale
        y0 = y - h // 2
        rects.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" '
                     f'rx="6" ry="6" fill="{mat_color(mat)}" stroke="#222" stroke-width="1"/>')
        x += w + 4

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="white"/>
  <text x="10" y="18" font-family="monospace" font-size="12">Rod design</text>
  {''.join(rects)}
</svg>'''
    with open(path, "w") as f:
        f.write(svg)

# -----------------------------------
# E: Evaluator for the rod toy domain
# -----------------------------------

DENSITY = {"aluminum": 1.0, "steel": 2.6}   # relative units
STRENGTH = {"aluminum": 1.0, "steel": 2.2}  # relative tensile capacity per thickness unit

@dataclass
class EvalParams:
    load: float = 10.0          # external load (arbitrary units)
    target_length: float = 4.0   # required minimum total length
    stress_limit: float = 1.0    # maximum allowed stress

def evaluate(g: Graph, ep: EvalParams) -> Dict[str, Any]:
    length = 0.0
    area = 0.0
    weight = 0.0
    strength_scale = 0.0
    for nid in g.find("Segment"):
        p = g.nodes[nid]["props"]
        L = float(p["length"])
        T = float(p["thickness"])
        M = p["material"]
        length += L
        area += T
        weight += L * T * DENSITY[M]
        strength_scale += T * STRENGTH[M]

    stress = ep.load / max(strength_scale, 1e-6)
    feasible = (length >= ep.target_length) and (stress <= ep.stress_limit)

    # Cost: prefer feasible; then lower (weight + stress) and fewer segments
    nseg = len(g.find("Segment"))
    cost = (0 if feasible else 1000) + weight + 0.5 * stress + 0.05 * nseg

    return {
        "length": length,
        "stress": stress,
        "weight": weight,
        "segments": nseg,
        "feasible": feasible,
        "cost": cost
    }

# -------------------
# R: Rewrite machinery
# -------------------

@dataclass
class RuleResult:
    new_graph: Graph
    desc: str

RuleFn = Callable[[Graph], List[RuleResult]]

def rule_add_segment(base_len=0.8, base_thick=0.8, material="aluminum") -> RuleFn:
    def apply(g: Graph) -> List[RuleResult]:
        ng = g.clone()
        nid = f"seg{len(ng.find('Segment'))+1}"
        ng.add_node(nid, "Segment", length=base_len, thickness=base_thick, material=material)
        ng.add_edge("rod", "has", nid)
        return [RuleResult(ng, f"AddSegment({base_len:.2f},{base_thick:.2f},{material})")]
    return apply

def rule_increase_length(delta=0.5) -> RuleFn:
    def apply(g: Graph) -> List[RuleResult]:
        outs = []
        for nid in g.find("Segment"):
            ng = g.clone()
            ng.nodes[nid]["props"]["length"] += delta
            outs.append(RuleResult(ng, f"IncreaseLength({nid},+{delta})"))
        return outs
    return apply

def rule_increase_thickness(delta=0.3) -> RuleFn:
    def apply(g: Graph) -> List[RuleResult]:
        outs = []
        for nid in g.find("Segment"):
            ng = g.clone()
            ng.nodes[nid]["props"]["thickness"] += delta
            outs.append(RuleResult(ng, f"IncreaseThickness({nid},+{delta})"))
        return outs
    return apply

def rule_swap_material() -> RuleFn:
    def apply(g: Graph) -> List[RuleResult]:
        outs = []
        for nid in g.find("Segment"):
            ng = g.clone()
            m = ng.nodes[nid]["props"]["material"]
            ng.nodes[nid]["props"]["material"] = "steel" if m == "aluminum" else "aluminum"
            outs.append(RuleResult(ng, f"SwapMaterial({nid})"))
        return outs
    return apply

def rule_remove_shortest(min_keep=1) -> RuleFn:
    """Remove the shortest segment if > min_keep remain (cheap simplifier)."""
    def apply(g: Graph) -> List[RuleResult]:
        segs = g.find("Segment")
        if len(segs) <= min_keep:
            return []
        # find shortest
        shortest = min(segs, key=lambda nid: g.nodes[nid]["props"]["length"])
        ng = g.clone()
        del ng.nodes[shortest]
        ng.edges = [e for e in ng.edges if e[2] != shortest]
        return [RuleResult(ng, f"RemoveShortest({shortest})")]
    return apply

# ------------------------------
# S: Small greedy/beam scheduler
# ------------------------------

@dataclass
class SearchConfig:
    iters: int = 40
    beam_width: int = 6
    random_perturb: float = 0.05  # tiny jitter to break ties

@dataclass
class Provenance:
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, desc: str, metrics: Dict[str, Any]):
        self.steps.append({"rule": desc, "metrics": dict(metrics)})

    def dump(self, path: str):
        with open(path, "w") as f:
            for i, s in enumerate(self.steps):
                f.write(f"Step {i+1}: {s['rule']}\n")
                f.write(json.dumps(s["metrics"], indent=2) + "\n\n")

def search(initial: Graph, rules: List[RuleFn], ep: EvalParams, sc: SearchConfig):
    # Beam holds (cost, graph, metrics, last_rule)
    def score(m): return m["cost"] + sc.random_perturb * random.random()

    beam: List[Tuple[float, Graph, Dict[str, Any], str]] = []
    m0 = evaluate(initial, ep)
    beam.append((score(m0), initial, m0, "init"))
    prov = Provenance()
    prov.log("init", m0)

    best = (m0["cost"], initial, m0, "init")

    for _ in range(sc.iters):
        candidates: List[Tuple[float, Graph, Dict[str, Any], str]] = []
        # expand current beam
        for _, g, _, _ in beam:
            for r in rules:
                for rr in r(g):
                    m = evaluate(rr.new_graph, ep)
                    s = score(m)
                    candidates.append((s, rr.new_graph, m, rr.desc))
        if not candidates:
            break
        # prune
        candidates.sort(key=lambda t: t[0])
        beam = candidates[:sc.beam_width]
        # update best and provenance with the top pick
        b0 = beam[0]
        if b0[2]["cost"] < best[2]["cost"]:
            best = b0
        prov.log(b0[3], b0[2])
        # early stop if feasible and cost not improving much
        if best[2]["feasible"] and best[2]["cost"] <= 0.9 + 1e-6:
            break

    return best[1], best[2], prov

# ------------------------------
# Bootstrap an initial rod graph
# ------------------------------

def make_initial_rod() -> Graph:
    g = Graph()
    g.add_node("rod", "Assembly", name="rod-1")
    # start with one small aluminum segment
    g.add_node("seg1", "Segment", length=1.0, thickness=0.8, material="aluminum")
    g.add_edge("rod", "has", "seg1")
    return g

# ------------------------------
# Run a demo search and emit files
# ------------------------------

if __name__ == "__main__":
    random.seed(7)
    initial = make_initial_rod()

    ep = EvalParams(load=10.0, target_length=4.0, stress_limit=1.0)
    sc = SearchConfig(iters=45, beam_width=6)

    # Rule portfolio (mix exploration & simplification)
    rules = [
        rule_add_segment(0.8, 0.8, "aluminum"),
        rule_increase_length(0.6),
        rule_increase_thickness(0.3),
        rule_swap_material(),
        rule_remove_shortest(min_keep=1),
    ]

    best_graph, best_metrics, prov = search(initial, rules, ep, sc)

    # Export artifacts
    export_svg_rod(best_graph, "/mnt/data/rod.svg")
    prov.dump("/mnt/data/provenance.txt")
    with open("/mnt/data/best_design.json", "w") as f:
        json.dump(best_graph.to_json(), f, indent=2)

    print("Best metrics:", best_metrics)
    print("Files: /mnt/data/rod.svg, /mnt/data/provenance.txt, /mnt/data/best_design.json")


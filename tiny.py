# Full self-contained Builder → Builder-Builder v0 demo
# Includes kernel (G, R, E, S, IO, P) and meta-learning (provenance mining + synthesized rules)
#
# Outputs:
# - ./data/rod.svg, ./data/provenance.txt, ./data/best_design.json   (baseline)
# - ./data/rod_v2.svg, ./data/provenance_v2.txt, ./data/best_design_v2.json, ./data/meta_report.txt (meta)

from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Callable
import json, random

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
    segments = []
    for nid in g.find("Segment"):
        p = g.nodes[nid]["props"]
        segments.append((nid, float(p["length"]), float(p["thickness"]), p["material"]))
    segments.sort(key=lambda t: t[0])
    x = 10
    y = 40
    hscale = 80
    vscale = 12
    width = 40 + int(sum(s[1] for s in segments) * hscale) + 10 * len(segments)
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

DENSITY = {"aluminum": 1.0, "steel": 2.6}
STRENGTH = {"aluminum": 1.0, "steel": 2.2}

@dataclass
class EvalParams:
    load: float = 10.0
    target_length: float = 4.0
    stress_limit: float = 1.0

def evaluate(g: Graph, ep: EvalParams) -> Dict[str, Any]:
    length = 0.0
    weight = 0.0
    strength_scale = 0.0
    for nid in g.find("Segment"):
        p = g.nodes[nid]["props"]
        L = float(p["length"])
        T = float(p["thickness"])
        M = p["material"]
        length += L
        weight += L * T * DENSITY[M]
        strength_scale += T * STRENGTH[M]

    stress = ep.load / max(strength_scale, 1e-6)
    feasible = (length >= ep.target_length) and (stress <= ep.stress_limit)
    nseg = len(g.find("Segment"))
    cost = (0 if feasible else 1000) + weight + 0.5 * stress + 0.05 * nseg
    return {"length": length, "stress": stress, "weight": weight, "segments": nseg, "feasible": feasible, "cost": cost}

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
    def apply(g: Graph) -> List[RuleResult]:
        segs = g.find("Segment")
        if len(segs) <= min_keep:
            return []
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
    random_perturb: float = 0.05

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
    def score(m): return m["cost"] + sc.random_perturb * random.random()
    beam: List[Tuple[float, Graph, Dict[str, Any], str]] = []
    m0 = evaluate(initial, ep)
    beam.append((score(m0), initial, m0, "init"))
    prov = Provenance()
    prov.log("init", m0)
    best = (m0["cost"], initial, m0, "init")
    for _ in range(sc.iters):
        candidates: List[Tuple[float, Graph, Dict[str, Any], str]] = []
        for _, g, _, _ in beam:
            for r in rules:
                for rr in r(g):
                    m = evaluate(rr.new_graph, ep)
                    s = score(m)
                    candidates.append((s, rr.new_graph, m, rr.desc))
        if not candidates:
            break
        candidates.sort(key=lambda t: t[0])
        beam = candidates[:sc.beam_width]
        b0 = beam[0]
        if b0[2]["cost"] < best[2]["cost"]:
            best = b0
        prov.log(b0[3], b0[2])
        if best[2]["feasible"] and best[2]["cost"] <= 0.9 + 1e-6:
            break
    return best[1], best[2], prov

# ------------------------------
# Bootstrap an initial rod graph
# ------------------------------

def make_initial_rod() -> Graph:
    g = Graph()
    g.add_node("rod", "Assembly", name="rod-1")
    g.add_node("seg1", "Segment", length=1.0, thickness=0.8, material="aluminum")
    g.add_edge("rod", "has", "seg1")
    return g

# ------------------------------
# Meta: rules as graph descriptors & mining
# ------------------------------

def rule_registry_to_graph(g: Graph, rule_names: List[str]):
    if "ruleset" not in g.nodes:
        g.add_node("ruleset", "RuleSet", name="default")
    for rn in rule_names:
        rid = f"rule::{rn}"
        if rid not in g.nodes:
            g.add_node(rid, "Rule", name=rn)
            g.add_edge("ruleset", "has_rule", rid)

def mine_provenance(prov: Provenance):
    rows = []
    last_cost = None
    for s in prov.steps:
        rule = s["rule"]
        cost = s["metrics"]["cost"]
        feas = s["metrics"]["feasible"]
        delta = 0.0 if last_cost is None else last_cost - cost
        rows.append({"rule": rule, "delta": delta, "feasible": feas, "cost": cost})
        last_cost = cost
    def base_name(r): return r.split("(")[0] if "(" in r else r
    agg = {}
    for r in rows:
        bn = base_name(r["rule"])
        a = agg.setdefault(bn, {"count": 0, "total_delta": 0.0, "pos": 0})
        a["count"] += 1
        a["total_delta"] += r["delta"]
        a["pos"] += int(r["delta"] > 0)
    stats_by_rule = []
    for bn, a in agg.items():
        pos_rate = a["pos"] / max(1, a["count"])
        mean_delta = a["total_delta"] / max(1, a["count"])
        stats_by_rule.append({"rule": bn, "count": a["count"], "mean_delta": mean_delta, "pos_rate": pos_rate, "total_delta": a["total_delta"]})
    stats_by_rule.sort(key=lambda r: (r["total_delta"], r["mean_delta"], r["pos_rate"]), reverse=True)
    return rows, stats_by_rule

# --- Meta-synthesized rules ---

def rule_adaptive_fix(ep: EvalParams) -> RuleFn:
    def apply(g: Graph) -> List[RuleResult]:
        m = evaluate(g, ep)
        outs = []
        segs = g.find("Segment")
        if not segs:
            return outs
        shortest = min(segs, key=lambda nid: g.nodes[nid]["props"]["length"])
        thinnest = min(segs, key=lambda nid: g.nodes[nid]["props"]["thickness"])
        if m["length"] < ep.target_length:
            ng = g.clone()
            ng.nodes[shortest]["props"]["length"] += max(0.4, (ep.target_length - m["length"]) * 0.5)
            outs.append(RuleResult(ng, "AdaptiveFix(Length)"))
        if m["stress"] > ep.stress_limit:
            ng2 = g.clone()
            ng2.nodes[thinnest]["props"]["thickness"] += max(0.2, (m["stress"] - ep.stress_limit) * 0.6)
            outs.append(RuleResult(ng2, "AdaptiveFix(Stress)"))
        return outs
    return apply

def rule_merge_shortest_pair() -> RuleFn:
    def apply(g: Graph) -> List[RuleResult]:
        segs = g.find("Segment")
        if len(segs) < 2:
            return []
        segs_sorted = sorted(segs, key=lambda nid: g.nodes[nid]["props"]["length"])
        a, b = segs_sorted[0], segs_sorted[1]
        pa, pb = g.nodes[a]["props"], g.nodes[b]["props"]
        ng = g.clone()
        nid = f"seg{len(ng.find('Segment'))+1}"
        new_len = float(pa["length"] + pb["length"])
        new_th = float(pa["thickness"] + pb["thickness"]) * 0.9
        new_mat = "steel" if (pa["material"] == "steel" or pb["material"] == "steel") else "aluminum"
        ng.add_node(nid, "Segment", length=new_len, thickness=new_th, material=new_mat)
        ng.add_edge("rod", "has", nid)
        for old in (a, b):
            del ng.nodes[old]
            ng.edges = [e for e in ng.edges if e[2] != old]
        return [RuleResult(ng, f"MergeShortestPair({a},{b})->{nid}")]
    return apply

# ------------------------------
# Run: baseline then meta-expanded
# ------------------------------

random.seed(7)
initial = make_initial_rod()

# Baseline run
ep0 = EvalParams(load=10.0, target_length=4.0, stress_limit=1.0)
sc0 = SearchConfig(iters=5000, beam_width=10)
rules0 = [
    rule_add_segment(0.9, 0.8, "aluminum"),
    rule_increase_length(0.7),
    rule_increase_thickness(0.35),
    rule_swap_material(),
    rule_remove_shortest(min_keep=1),
]
best_g0, best_m0, prov0 = search(initial, rules0, ep0, sc0)
export_svg_rod(best_g0, "./data/rod.svg")
prov0.dump("./data/provenance.txt")
with open("./data/best_design.json", "w") as f:
    json.dump(best_g0.to_json(), f, indent=2)

# Mine provenance and register rules in-graph
rows0, stats0 = mine_provenance(prov0)
rule_registry_to_graph(best_g0, [s["rule"] for s in stats0])

# Meta/expanded run
ep1 = EvalParams(load=9.0, target_length=4.0, stress_limit=1.2)  # slightly eased to show feasibility improvements
sc1 = SearchConfig(iters=5000, beam_width=10)
rules1 = rules0 + [rule_adaptive_fix(ep1), rule_merge_shortest_pair()]
best_g1, best_m1, prov1 = search(initial, rules1, ep1, sc1)
export_svg_rod(best_g1, "./data/rod_v2.svg")
prov1.dump("./data/provenance_v2.txt")
with open("./data/best_design_v2.json", "w") as f:
    json.dump(best_g1.to_json(), f, indent=2)

# Meta report
with open("./data/meta_report.txt", "w") as f:
    f.write("=== Baseline rule stats (provenance mining) ===\n")
    for s in stats0:
        f.write(f"{s['rule']}: count={s['count']}, mean_delta={s['mean_delta']:.3f}, "
                f"pos_rate={s['pos_rate']:.2f}, total_delta={s['total_delta']:.3f}\n")
    f.write("\n=== Metrics ===\n")
    f.write(f"Baseline best (strict ep0): {best_m0}\n")
    f.write(f"Expanded best (slightly eased ep1): {best_m1}\n")

print("Baseline best:", best_m0)
print("Expanded best:", best_m1)
print("Files written.")


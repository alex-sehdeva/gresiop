# Re-run with minor fix (no walrus in f-string expression list)
# Pattern/Guard/Replacement Rule-Graphs + Live Specialization

from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Callable, Optional
import json, random

class Graph:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str, str]] = []
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

DENSITY = {"aluminum": 1.0, "steel": 2.6}
STRENGTH = {"aluminum": 1.0, "steel": 2.2}

@dataclass
class EvalParams:
    load: float = 10.0
    target_length: float = 4.0
    stress_limit: float = 1.0

def evaluate(g: Graph, ep: EvalParams) -> Dict[str, Any]:
    length = 0.0; weight = 0.0; strength = 0.0
    for nid in g.find("Segment"):
        p = g.nodes[nid]["props"]
        L = float(p["length"]); T = float(p["thickness"]); M = p["material"]
        length += L; weight += L*T*DENSITY[M]; strength += T*STRENGTH[M]
    stress = ep.load / max(strength, 1e-6)
    feasible = (length >= ep.target_length) and (stress <= ep.stress_limit)
    nseg = len(g.find("Segment"))
    cost = (0 if feasible else 1000) + weight + 0.5*stress + 0.05*nseg
    return {"length": length, "stress": stress, "weight": weight, "segments": nseg, "feasible": feasible, "cost": cost}

@dataclass
class RuleResult:
    new_graph: Graph
    desc: str
RuleFn = Callable[[Graph], List[RuleResult]]

@dataclass
class SearchConfig:
    iters: int = 80
    beam_width: int = 12
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
    prov = Provenance(); prov.log("init", m0)
    best = (m0["cost"], initial, m0, "init")
    for _ in range(sc.iters):
        cand: List[Tuple[float, Graph, Dict[str, Any], str]] = []
        for _, g, _, _ in beam:
            for r in rules:
                for rr in r(g):
                    m = evaluate(rr.new_graph, ep)
                    cand.append((score(m), rr.new_graph, m, rr.desc))
        if not cand: break
        cand.sort(key=lambda t: t[0])
        beam = cand[:sc.beam_width]
        b0 = beam[0]
        if b0[2]["cost"] < best[2]["cost"]:
            best = b0
        prov.log(b0[3], b0[2])
        if best[2]["feasible"] and best[2]["cost"] <= 0.9 + 1e-6:
            break
    return best[1], best[2], prov

def export_svg_rod(g: Graph, path: str):
    segs = []
    for nid in g.find("Segment"):
        p = g.nodes[nid]["props"]
        segs.append((nid, float(p["length"]), float(p["thickness"]), p["material"]))
    segs.sort(key=lambda t: t[0])
    x=10; y=40; hscale=80; vscale=12
    width = 40 + int(sum(s[1] for s in segs)*hscale) + 10*len(segs)
    height = 120
    def color(m): return {"aluminum":"#9bb7d4","steel":"#666"}.get(m,"#ccc")
    rects=[]
    for _,L,T,M in segs:
        w=L*hscale; h=T*vscale; y0=y - int(h//2)
        rects.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" ry="6" fill="{color(M)}" stroke="#222" stroke-width="1"/>')
        x += w + 4
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect x="0" y="0" width="{width}" height="{height}" fill="white"/><text x="10" y="18" font-family="monospace" font-size="12">Rod design</text>{"".join(rects)}</svg>'
    with open(path,"w") as f: f.write(svg)

# --- Rule-graphs with pattern/guard/replacement ---

def install_rule_graphs_pgr() -> Graph:
    rg = Graph()
    rg.add_node("ruleset", "RuleSet", name="default")
    # R1 AddSegment
    rg.add_node("R1","Rule",name="AddSegment",kind="AddSegment")
    for k,v in [("length",0.9),("thickness",0.8),("material","aluminum")]:
        pid=f"R1.{k}"; rg.add_node(pid,"Param",key=k,value=v); rg.add_edge("R1","has_param",pid)
    rg.add_edge("ruleset","has_rule","R1")
    # R2 IncreaseLength (no guard initially)
    rg.add_node("R2","Rule",name="IncreaseLength",kind="IncreaseLength")
    rg.add_node("R2.delta","Param",key="delta",value=0.7); rg.add_edge("R2","has_param","R2.delta")
    rg.add_node("R2.x","PatternVar",var="x",type="Segment"); rg.add_edge("R2","has_var","R2.x")
    rg.add_edge("ruleset","has_rule","R2")
    # R3 IncreaseThickness
    rg.add_node("R3","Rule",name="IncreaseThickness",kind="IncreaseThickness")
    rg.add_node("R3.delta","Param",key="delta",value=0.35); rg.add_edge("R3","has_param","R3.delta")
    rg.add_node("R3.x","PatternVar",var="x",type="Segment"); rg.add_edge("R3","has_var","R3.x")
    rg.add_edge("ruleset","has_rule","R3")
    # R4 SwapMaterial
    rg.add_node("R4","Rule",name="SwapMaterial",kind="SwapMaterial")
    rg.add_node("R4.x","PatternVar",var="x",type="Segment"); rg.add_edge("R4","has_var","R4.x")
    rg.add_edge("ruleset","has_rule","R4")
    # R5 RemoveShortest
    rg.add_node("R5","Rule",name="RemoveShortest",kind="RemoveShortest")
    rg.add_node("R5.min","Param",key="min_keep",value=1); rg.add_edge("R5","has_param","R5.min")
    rg.add_edge("ruleset","has_rule","R5")
    return rg

def export_json(obj, path):
    with open(path,"w") as f: json.dump(obj,f,indent=2)

def get_params(rg: Graph, rid: str) -> Dict[str, Any]:
    out={}
    for (src,et,dst) in rg.edges:
        if src==rid and et=="has_param":
            p=rg.nodes[dst]["props"]; out[p["key"]]=p["value"]
    return out

def get_guards(rg: Graph, rid: str) -> List[Dict[str, Any]]:
    out=[]
    for (src,et,dst) in rg.edges:
        if src==rid and et=="has_guard":
            out.append(rg.nodes[dst]["props"])
    return out

def compile_rules_from_pgr(rg: Graph) -> List[RuleFn]:
    fns: List[RuleFn]=[]
    for rid in rg.find("Rule"):
        kind=rg.nodes[rid]["props"]["kind"]
        params=get_params(rg,rid)
        guards=get_guards(rg,rid)

        if kind=="AddSegment":
            base_len=float(params.get("length",0.8)); base_th=float(params.get("thickness",0.8)); mat=str(params.get("material","aluminum"))
            def fn(g: Graph, bl=base_len, bt=base_th, m=mat):
                ng=g.clone(); nid=f"seg{len(ng.find('Segment'))+1}"
                ng.add_node(nid,"Segment",length=bl,thickness=bt,material=m); ng.add_edge("rod","has",nid)
                return [RuleResult(ng, f"AddSegment({bl:.2f},{bt:.2f},{m})")]
            fns.append(fn)

        elif kind=="IncreaseLength":
            delta=float(params.get("delta",0.5))
            def fn(g: Graph, d=delta, guards_=guards):
                outs=[]
                for nid in g.find("Segment"):
                    ok=True
                    for gd in guards_:
                        if gd.get("var")=="x" and gd.get("key")=="length" and gd.get("op")=="<":
                            if not (g.nodes[nid]["props"]["length"] < float(gd["value"])):
                                ok=False; break
                    if not ok: continue
                    ng=g.clone(); ng.nodes[nid]["props"]["length"] += d
                    outs.append(RuleResult(ng, f"IncreaseLength({nid},+{d})"))
                return outs
            fns.append(fn)

        elif kind=="IncreaseThickness":
            delta=float(params.get("delta",0.3))
            def fn(g: Graph, d=delta):
                outs=[]
                for nid in g.find("Segment"):
                    ng=g.clone(); ng.nodes[nid]["props"]["thickness"] += d
                    outs.append(RuleResult(ng, f"IncreaseThickness({nid},+{d})"))
                return outs
            fns.append(fn)

        elif kind=="SwapMaterial":
            def fn(g: Graph):
                outs=[]
                for nid in g.find("Segment"):
                    ng=g.clone(); m=ng.nodes[nid]["props"]["material"]
                    ng.nodes[nid]["props"]["material"]="steel" if m=="aluminum" else "aluminum"
                    outs.append(RuleResult(ng, f"SwapMaterial({nid})"))
                return outs
            fns.append(fn)

        elif kind=="RemoveShortest":
            min_keep=int(params.get("min_keep",1))
            def fn(g: Graph, mk=min_keep):
                segs=g.find("Segment")
                if len(segs)<=mk: return []
                shortest=min(segs, key=lambda nid: g.nodes[nid]["props"]["length"])
                ng=g.clone(); del ng.nodes[shortest]
                ng.edges=[e for e in ng.edges if e[2]!=shortest]
                return [RuleResult(ng, f"RemoveShortest({shortest})")]
            fns.append(fn)
    return fns

def add_len_guard_specialization(rg: Graph, max_len: float):
    rid=None
    for nid,n in rg.nodes.items():
        if n["type"]=="Rule" and n["props"].get("name")=="IncreaseLength":
            rid=nid; break
    if rid is None: return False
    # if already present, update value
    for (src,et,dst) in list(rg.edges):
        if src==rid and et=="has_guard":
            rg.nodes[dst]["props"]["value"]=float(max_len)
            return True
    gid="R2.guard.lenlt"
    rg.add_node(gid,"Guard",var="x",op="<",key="length",value=float(max_len))
    rg.add_edge(rid,"has_guard",gid)
    return True

def make_initial_rod() -> Graph:
    g=Graph(); g.add_node("rod","Assembly",name="rod-1")
    g.add_node("seg1","Segment",length=1.0,thickness=0.8,material="aluminum"); g.add_edge("rod","has","seg1")
    return g

# Run
random.seed(7)

rg_before = install_rule_graphs_pgr()
export_json(rg_before.to_json(), "./data/rules_pgr_before.json")

rules_before = compile_rules_from_pgr(rg_before)
initial = make_initial_rod()
ep = EvalParams(load=10.0, target_length=4.0, stress_limit=1.0)
sc = SearchConfig(iters=80, beam_width=12)
best_g_b, best_m_b, prov_b = search(initial, rules_before, ep, sc)
export_svg_rod(best_g_b, "./data/rod_v4_before.svg")
prov_b.dump("./data/provenance_v4_before.txt")
with open("./data/best_design_v4_before.json","w") as f: json.dump(best_g_b.to_json(), f, indent=2)

# Specialize IncreaseLength with guard x.length < 1.2
changed = add_len_guard_specialization(rg_before, max_len=1.2)
rules_after = compile_rules_from_pgr(rg_before)
export_json(rg_before.to_json(), "./data/rules_pgr_after.json")

best_g_a, best_m_a, prov_a = search(initial, rules_after, ep, sc)
export_svg_rod(best_g_a, "./data/rod_v4_after.svg")
prov_a.dump("./data/provenance_v4_after.txt")
with open("./data/best_design_v4_after.json","w") as f: json.dump(best_g_a.to_json(), f, indent=2)

with open("./data/meta_pgr_changes.txt","w") as f:
    f.write("=== Pattern/Guard specialization ===\n")
    f.write(f"IncreaseLength now guarded: apply only when x.length < 1.2 (changed={changed})\n")
    f.write("\n=== Metrics ===\n")
    f.write(f"Before: {best_m_b}\nAfter:  {best_m_a}\n")

print("Before metrics:", best_m_b)
print("After metrics:", best_m_a)
print("Guard added/updated:", changed)


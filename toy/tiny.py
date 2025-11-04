# Provenance-driven guard selection + Golden-set acceptance
# --------------------------------------------------------
# This extends the P/G/R rule-graph system:
# - Logs per-application context for IncreaseLength, including prev length
# - Mines the provenance to compute a median prev-length where IncreaseLength
#   yielded positive cost improvements
# - Sets the guard max_len to that median (plus a small epsilon)
# - Evaluates on a small "golden set" of tasks; accepts the change only if the
#   aggregate cost improves (or feasibility count increases)
#
# Artifacts:
# - ./data/meta_guard_selection.txt
# - ./data/rules_pgr_auto_before.json
# - ./data/rules_pgr_auto_after.json
# - ./data/golden_results_before.json
# - ./data/golden_results_after.json

from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Callable, Optional
import json, random, statistics

# -------------------------------
# Minimal kernel and domain
# -------------------------------

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
    iters: int = 90
    beam_width: int = 12
    random_perturb: float = 0.05

@dataclass
class Provenance:
    steps: List[Dict[str, Any]] = field(default_factory=list)
    def log(self, desc: str, metrics: Dict[str, Any], extra: Optional[Dict[str, Any]] = None):
        rec = {"rule": desc, "metrics": dict(metrics)}
        if extra: rec["extra"] = extra
        self.steps.append(rec)
    def dump(self, path: str):
        with open(path, "w") as f:
            for i, s in enumerate(self.steps):
                f.write(f"Step {i+1}: {s['rule']}\n")
                f.write(json.dumps(s.get("metrics", {}), indent=2) + "\n")
                if "extra" in s:
                    f.write("extra: " + json.dumps(s["extra"]) + "\n")
                f.write("\n")

# -------------------------------
# Rule-graphs with P/G/R
# -------------------------------

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

def add_len_guard(rg: Graph, max_len: float):
    rid=None
    for nid,n in rg.nodes.items():
        if n["type"]=="Rule" and n["props"].get("name")=="IncreaseLength":
            rid=nid; break
    if rid is None: return False
    # update if exists
    for (src,et,dst) in list(rg.edges):
        if src==rid and et=="has_guard":
            rg.nodes[dst]["props"]["value"]=float(max_len)
            return True
    gid="R2.guard.lenlt"
    rg.add_node(gid,"Guard",var="x",op="<",key="length",value=float(max_len))
    rg.add_edge(rid,"has_guard",gid)
    return True

# ----------------------------------
# Compile rule-graphs to executable
# ----------------------------------

def compile_rules_from_pgr(rg: Graph, prov_hook: Optional[Provenance] = None) -> List[RuleFn]:
    fns: List[RuleFn]=[]
    for rid in rg.find("Rule"):
        kind=rg.nodes[rid]["props"]["kind"]
        params=get_params(rg,rid)
        guards=get_guards(rg,rid)

        if kind=="AddSegment":
            bl=float(params.get("length",0.8)); bt=float(params.get("thickness",0.8)); m=str(params.get("material","aluminum"))
            def fn(g: Graph, bl=bl, bt=bt, m=m):
                ng=g.clone(); nid=f"seg{len(ng.find('Segment'))+1}"
                ng.add_node(nid,"Segment",length=bl,thickness=bt,material=m); ng.add_edge("rod","has",nid)
                return [RuleResult(ng, f"AddSegment({bl:.2f},{bt:.2f},{m})")]
            fns.append(fn)

        elif kind=="IncreaseLength":
            d=float(params.get("delta",0.5))
            def fn(g: Graph, d=d, guards_=guards, hook=prov_hook):
                outs=[]
                for nid in g.find("Segment"):
                    # guard checks
                    ok=True
                    for gd in guards_:
                        if gd.get("var")=="x" and gd.get("key")=="length" and gd.get("op")=="<":
                            if not (g.nodes[nid]["props"]["length"] < float(gd["value"])):
                                ok=False; break
                    if not ok: continue
                    prevL = float(g.nodes[nid]["props"]["length"])
                    ng=g.clone(); ng.nodes[nid]["props"]["length"] = prevL + d
                    desc=f"IncreaseLength({nid},+{d},prevL={prevL:.3f})"
                    outs.append(RuleResult(ng, desc))
                return outs
            fns.append(fn)

        elif kind=="IncreaseThickness":
            d=float(params.get("delta",0.3))
            def fn(g: Graph, d=d):
                outs=[]
                for nid in g.find("Segment"):
                    prevT=float(g.nodes[nid]["props"]["thickness"])
                    ng=g.clone(); ng.nodes[nid]["props"]["thickness"] = prevT + d
                    outs.append(RuleResult(ng, f"IncreaseThickness({nid},+{d},prevT={prevT:.3f})"))
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
            mk=int(params.get("min_keep",1))
            def fn(g: Graph, mk=mk):
                segs=g.find("Segment")
                if len(segs)<=mk: return []
                shortest=min(segs, key=lambda nid: g.nodes[nid]["props"]["length"])
                ng=g.clone(); del ng.nodes[shortest]
                ng.edges=[e for e in ng.edges if e[2]!=shortest]
                return [RuleResult(ng, f"RemoveShortest({shortest})")]
            fns.append(fn)
    return fns

# ----------------------------------
# Search that captures per-step desc
# ----------------------------------

def search_capture(initial: Graph, rules: List[RuleFn], ep: EvalParams, sc: SearchConfig):
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

# ----------------------------------
# Golden set eval
# ----------------------------------

def make_initial_rod(len1=1.0, th1=0.8, mat1="aluminum") -> Graph:
    g=Graph(); g.add_node("rod","Assembly",name="rod-1")
    g.add_node("seg1","Segment",length=float(len1),thickness=float(th1),material=mat1); g.add_edge("rod","has","seg1")
    return g

def golden_suite():
    # A few varied initial states & evaluator params
    tasks = [
        (make_initial_rod(1.0,0.8,"aluminum"), EvalParams(load=10.0, target_length=4.0, stress_limit=1.0)),
        (make_initial_rod(1.2,0.7,"aluminum"), EvalParams(load=9.0, target_length=4.0, stress_limit=1.1)),
        (make_initial_rod(0.8,0.9,"steel"),    EvalParams(load=11.0, target_length=4.0, stress_limit=1.0)),
        (make_initial_rod(1.5,0.6,"aluminum"), EvalParams(load=10.0, target_length=4.0, stress_limit=1.0)),
    ]
    return tasks

def run_suite(rules: List[RuleFn], sc: SearchConfig):
    out=[]
    for g0, ep in golden_suite():
        best_g, best_m, _ = search_capture(g0, rules, ep, sc)
        out.append(best_m)
    return out

def aggregate_results(results):
    feas = sum(1 for r in results if r["feasible"])
    avg_cost = sum(r["cost"] for r in results) / len(results)
    return {"feasible_count": feas, "avg_cost": avg_cost, "n": len(results)}

# ----------------------------------
# Provenance mining to choose guard
# ----------------------------------

def choose_guard_from_provenance(prov: Provenance, epsilon: float = 0.05) -> Optional[float]:
    # For each step where rule is IncreaseLength and delta cost positive, capture prevL from desc
    prev_cost = None
    samples = []
    for s in prov.steps:
        rule = s["rule"]
        cost = s["metrics"]["cost"]
        delta = 0.0 if prev_cost is None else prev_cost - cost
        prev_cost = cost
        if rule.startswith("IncreaseLength(") and "prevL=" in rule and delta > 0:
            try:
                # parse prevL from desc
                frag = rule.split("prevL=")[1]
                prevL = float(frag.split(")")[0])
                samples.append(prevL)
            except Exception:
                pass
    if not samples:
        return None
    med = statistics.median(samples)
    return med + epsilon

# ----------------------------------
# RUN: baseline → mine → propose guard → golden eval → accept or reject
# ----------------------------------

random.seed(11)

# Build rule-graph and compile
rg = install_rule_graphs_pgr()
export_json(rg.to_json(), "./data/rules_pgr_auto_before.json")
rules0 = compile_rules_from_pgr(rg)

# Baseline: run one task to gather provenance (we'll use task 0)
g0, ep0 = golden_suite()[0]
sc = SearchConfig(iters=90, beam_width=12)
best_g_b, best_m_b, prov_b = search_capture(g0, rules0, ep0, sc)

# Choose guard from provenance
max_len = choose_guard_from_provenance(prov_b, epsilon=0.05)

# Evaluate rules0 on golden set
res_before = run_suite(rules0, sc)
agg_before = aggregate_results(res_before)

accepted = False
guard_value_used = None

if max_len is not None:
    # Propose: set guard to max_len
    add_len_guard(rg, max_len=max_len)
    export_json(rg.to_json(), "./data/rules_pgr_auto_after.json")
    rules1 = compile_rules_from_pgr(rg)

    # Evaluate on golden set
    res_after = run_suite(rules1, sc)
    agg_after = aggregate_results(res_after)

    # Accept if feasibility improves OR avg cost decreases by >= 1.0
    if (agg_after["feasible_count"] > agg_before["feasible_count"]) or (agg_after["avg_cost"] <= agg_before["avg_cost"] - 1.0):
        accepted = True
        guard_value_used = max_len
        # keep after results
        export_json(res_after, "./data/golden_results_after.json")
    else:
        # revert
        export_json(rg.to_json(), "./data/rules_pgr_auto_after.json")  # still export for inspection
        export_json(res_after, "./data/golden_results_after.json")
else:
    # No signal; still emit placeholder after to keep UX consistent
    export_json(rg.to_json(), "./data/rules_pgr_auto_after.json")
    rules1 = rules0
    res_after = run_suite(rules1, sc)
    agg_after = aggregate_results(res_after)
    export_json(res_after, "./data/golden_results_after.json")

# Export baseline results
export_json(res_before, "./data/golden_results_before.json")

# Meta log
with open("./data/meta_guard_selection.txt","w") as f:
    f.write("=== Provenance-Driven Guard Selection ===\n")
    f.write(f"Derived guard max_len from baseline provenance: {max_len}\n")
    f.write(f"Accepted into rule-graph: {accepted}\n")
    f.write("\n=== Golden Set Aggregates ===\n")
    f.write(f"Before: {agg_before}\n")
    f.write(f"After:  {agg_after}\n")

print("Derived guard:", max_len, "Accepted:", accepted)
print("Golden before:", agg_before)
print("Golden after: ", agg_after)

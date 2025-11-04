# domains/rod/rule_handlers.py (rod-specific)
from __future__ import annotations
from typing import Dict, Any, List, Callable
from kernel import Graph, RuleResult, RuleFn
from rule_handlers_std import REGISTRY_STD as STD

# Optional: material constants can live in the rod domain, not kernel
STRENGTH = {"aluminum": 1.0, "steel": 2.2}

def _new_seg_id(g: Graph) -> str:
    # simple monotone id based on existing "Segment" count
    return f"seg{len(g.find('Segment'))+1}"

def handle_AddSegment(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    bl = float(params.get("length", 0.8))
    bt = float(params.get("thickness", 0.8))
    m  = str(params.get("material", "aluminum"))

    def fn(g: Graph) -> List[RuleResult]:
        # no vars needed; guard is global (always true)
        if not guard_pred(g, {}):
            return []
        ng = g.clone()
        nid = _new_seg_id(ng)
        ng.add_node(nid, "Segment", length=bl, thickness=bt, material=m)
        ng.add_edge("rod", "has", nid)
        return [RuleResult(ng, f"AddSegment({bl:.2f},{bt:.2f},{m})")]
    return fn

def handle_IncreaseLength(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    d = float(params.get("delta", 0.5))

    def fn(g: Graph) -> List[RuleResult]:
        outs: List[RuleResult] = []
        # Simple per-node binding for x:Segment
        envs = match_var_bindings_rod(g, vars_spec)
        for env in envs:
            x = env["x"]
            if not guard_pred(g, env):
                continue
            prevL = float(g.props(x)["length"])
            ng = g.clone()
            ng.props(x)["length"] = prevL + d
            outs.append(RuleResult(ng, f"IncreaseLength({x},+{d},prevL={prevL:.3f})"))
        return outs
    return fn

def handle_IncreaseThickness(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    d = float(params.get("delta", 0.3))

    def fn(g: Graph) -> List[RuleResult]:
        outs: List[RuleResult] = []
        envs = match_var_bindings_rod(g, vars_spec)
        for env in envs:
            x = env["x"]
            if not guard_pred(g, env):
                continue
            prevT = float(g.props(x)["thickness"])
            ng = g.clone()
            ng.props(x)["thickness"] = prevT + d
            outs.append(RuleResult(ng, f"IncreaseThickness({x},+{d},prevT={prevT:.3f})"))
        return outs
    return fn

def handle_SwapMaterial(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    def fn(g: Graph) -> List[RuleResult]:
        outs: List[RuleResult] = []
        envs = match_var_bindings_rod(g, vars_spec)
        for env in envs:
            x = env["x"]
            if not guard_pred(g, env):
                continue
            ng = g.clone()
            m = ng.props(x)["material"]
            ng.props(x)["material"] = "steel" if m == "aluminum" else "aluminum"
            outs.append(RuleResult(ng, f"SwapMaterial({x})"))
        return outs
    return fn

def handle_RemoveShortest(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    mk = int(params.get("min_keep", 1))

    def fn(g: Graph) -> List[RuleResult]:
        segs = g.find("Segment")
        if len(segs) <= mk:
            return []
        # No binding needed; it's a global rule
        # (If you want a bound version, you can require a PatternVar and check it's the min)
        shortest = min(segs, key=lambda nid: g.props(nid)["length"])
        env = {"x": shortest} if any(v.get("var")=="x" for v in vars_spec) else {}
        if not guard_pred(g, env):
            return []
        ng = g.clone()
        del ng.nodes[shortest]
        ng.edges = [e for e in ng.edges if e[2] != shortest]
        return [RuleResult(ng, f"RemoveShortest({shortest})")]
    return fn

def handle_AdaptiveFix(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    al  = float(params.get("alpha_len", 0.5))
    ast = float(params.get("alpha_str", 0.6))

    def fn(g: Graph) -> List[RuleResult]:
        segs = g.find("Segment")
        if not segs:
            return []
        outs: List[RuleResult] = []

        shortest = min(segs, key=lambda nid: g.props(nid)["length"])
        thinnest = min(segs, key=lambda nid: g.props(nid)["thickness"])

        # Conservative length gap proxy (target 4.0 is a domain decision; you can pass it via params if desired)
        total_len = sum(float(g.props(s)["length"]) for s in segs)
        need_len  = max(0.0, 4.0 - total_len)
        if need_len > 0:
            env = {"x": shortest} if any(v.get("var")=="x" for v in vars_spec) else {}
            if guard_pred(g, env):
                ng = g.clone()
                bump = max(0.4, al * need_len)
                ng.props(shortest)["length"] += bump
                outs.append(RuleResult(ng, f"AdaptiveFix(Length,+{bump:.2f})"))

        # Stress proxy via material strength × thickness
        scale = sum(float(g.props(s)["thickness"]) * STRENGTH[g.props(s)["material"]] for s in segs)
        target_scale = 10.0 / 1.0
        if scale < target_scale:
            env = {"x": thinnest} if any(v.get("var")=="x" for v in vars_spec) else {}
            if guard_pred(g, env):
                ng2 = g.clone()
                bump2 = max(0.2, ast * (target_scale - scale) / max(1.0, len(segs)))
                ng2.props(thinnest)["thickness"] += bump2
                outs.append(RuleResult(ng2, f"AdaptiveFix(Stress,+{bump2:.2f})"))

        return outs
    return fn

# --- tiny var matcher for rod (relies only on type=Segment) ---
def match_var_bindings_rod(g: Graph, vars_spec: List[Dict[str, Any]]):
    envs: List[Dict[str, str]] = [ {} ]
    for vs in vars_spec:
        vname = vs.get("var")
        vtype = vs.get("type")
        if not vname or not vtype:
            return []
        cands = g.find(vtype)
        if not cands:
            return []
        new_envs = []
        for env in envs:
            for nid in cands:
                if nid in env.values():
                    continue
                e2 = dict(env); e2[vname] = nid
                new_envs.append(e2)
        envs = new_envs
    return envs

# --- registry exposed to the compiler ---
REGISTRY = {
    "AddSegment":       handle_AddSegment,
    "IncreaseLength":   handle_IncreaseLength,
    "IncreaseThickness":handle_IncreaseThickness,
    "AdaptiveFix":      handle_AdaptiveFix,
    "SwapMaterial":     handle_SwapMaterial,
    "RemoveShortest":   handle_RemoveShortest,
    # std kinds (reusable across domains):
    **STD,
}


# rule_handlers_std.py
from __future__ import annotations
from typing import Dict, Any, List, Callable
from kernel import Graph, RuleFn, RuleResult

# tiny helpers
def _props(g: Graph, nid: str) -> Dict[str, Any]:
    return g.nodes[nid]["props"]

def _match_vars(g: Graph, vars_spec: List[Dict[str, Any]]):
    # Cartesian product over var:type filters; avoids reusing same node by default
    envs: List[Dict[str, str]] = [ {} ]
    for vs in vars_spec:
        vname, vtype = vs.get("var"), vs.get("type")
        cands = g.find(vtype) if (vname and vtype) else []
        new_envs = []
        for env in envs:
            for nid in cands:
                if nid in env.values():  # no self reuse by default
                    continue
                e2 = dict(env); e2[vname] = nid
                new_envs.append(e2)
        envs = new_envs
        if not envs:
            break
    return envs

# ---------------------
# Standard handlers
# ---------------------

def AddNode_handler(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    """
    Params:
      type: str (required)
      props: dict (optional)
      parent: node id or None
      edge_type: str (if parent set)
    """
    ntype = params.get("type")
    nprops = dict(params.get("props", {}))
    parent = params.get("parent")
    etype  = params.get("edge_type", "has")

    def fn(g: Graph) -> List[RuleResult]:
        if not ntype: return []
        if not guard_pred(g, {}): return []
        ng = g.clone()
        nid = f"{ntype.lower()}{len(ng.find(ntype))+1}"
        ng.add_node(nid, ntype, **nprops)
        if parent:
            ng.add_edge(parent, etype, nid)
        return [RuleResult(ng, f"AddNode({ntype},{nprops})")]
    return fn

def AddEdge_handler(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    """
    Params:
      src_var: str (pattern var name) or literal node id via src_id
      dst_var: str (pattern var name) or literal node id via dst_id
      etype: str
    """
    src_var, dst_var = params.get("src_var"), params.get("dst_var")
    src_id,  dst_id  = params.get("src_id"), params.get("dst_id")
    etype = params.get("etype", "link")

    def fn(g: Graph) -> List[RuleResult]:
        outs: List[RuleResult] = []
        envs = _match_vars(g, vars_spec) if (src_var or dst_var) else [{}]
        for env in envs:
            src = env.get(src_var) if src_var else src_id
            dst = env.get(dst_var) if dst_var else dst_id
            if not src or not dst: continue
            if not guard_pred(g, env): continue
            ng = g.clone()
            ng.add_edge(src, etype, dst)
            outs.append(RuleResult(ng, f"AddEdge({src},{etype},{dst})"))
        return outs
    return fn

def SetProp_handler(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    """
    Params:
      var: str (pattern var name)
      key: str
      value: any
    """
    var, key, value = params.get("var"), params.get("key"), params.get("value")

    def fn(g: Graph) -> List[RuleResult]:
        outs: List[RuleResult] = []
        envs = _match_vars(g, vars_spec)
        for env in envs:
            x = env.get(var)
            if not x: continue
            if not guard_pred(g, env): continue
            prev = _props(g, x).get(key)
            ng = g.clone()
            ng.nodes[x]["props"][key] = value
            outs.append(RuleResult(ng, f"SetProp({x},{key}={value},prev={prev})"))
        return outs
    return fn

def IncProp_handler(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    """
    Params:
      var: str (pattern var name)
      key: str
      delta: float
    """
    var, key = params.get("var"), params.get("key")
    delta = float(params.get("delta", 0.0))

    def fn(g: Graph) -> List[RuleResult]:
        outs: List[RuleResult] = []
        envs = _match_vars(g, vars_spec)
        for env in envs:
            x = env.get(var)
            if not x: continue
            if not guard_pred(g, env): continue
            prev = float(_props(g, x).get(key, 0.0))
            ng = g.clone()
            ng.nodes[x]["props"][key] = prev + delta
            outs.append(RuleResult(ng, f"IncProp({x},{key},+{delta},prev={prev:.3f})"))
        return outs
    return fn

def DeleteArgMin_handler(rg, rid, params, vars_spec, guard_pred) -> RuleFn:
    """
    Params:
      type: str
      key: str
      min_keep: int (default 0)
    """
    ntype = params.get("type")
    key   = params.get("key")
    mk    = int(params.get("min_keep", 0))

    def fn(g: Graph) -> List[RuleResult]:
        nodes = g.find(ntype) if ntype else []
        if len(nodes) <= mk: return []
        shortest = min(nodes, key=lambda nid: _props(g, nid).get(key, 0.0))
        env = {"x": shortest}  # let guards target x if they want
        if not guard_pred(g, env): return []
        ng = g.clone()
        del ng.nodes[shortest]
        ng.edges = [e for e in ng.edges if e[0] != shortest and e[2] != shortest]
        return [RuleResult(ng, f"DeleteArgMin({ntype},{key} -> {shortest})")]
    return fn

# Export a registry others can import
REGISTRY_STD = {
    "AddNode":        AddNode_handler,
    "AddEdge":        AddEdge_handler,
    "SetProp":        SetProp_handler,
    "IncProp":        IncProp_handler,
    "DeleteArgMin":   DeleteArgMin_handler,
}


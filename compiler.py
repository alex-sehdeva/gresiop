# compiler.py (domain-agnostic)
from __future__ import annotations
from typing import Dict, Any, List, Callable, Tuple, Optional
from dataclasses import dataclass

from kernel import Graph, RuleFn, RuleResult
from rules_pgr_base import get_params, get_vars, get_guards

# -------------------------------
# Guard machinery (generic)
# -------------------------------

def _op_eval(lhs: Any, op: str, rhs: Any) -> bool:
    if op == "<":   return lhs <  rhs
    if op == "<=":  return lhs <= rhs
    if op == ">":   return lhs >  rhs
    if op == ">=":  return lhs >= rhs
    if op == "==":  return lhs == rhs
    if op == "!=":  return lhs != rhs
    if op == "in":    return lhs in rhs
    if op == "notin": return lhs not in rhs
    if op == "exists": return bool(lhs) is True
    raise ValueError(f"Unsupported guard op: {op}")

def make_guard_predicate(guards: List[Dict[str, Any]]) -> Callable[[Graph, Dict[str,str]], bool]:
    """
    Build a predicate f(g, env) -> bool
    env maps pattern var names -> node ids the rule plans to bind.
    Each guard has props: {var, key, op, value}.
    """
    if not guards:
        return lambda g, env: True

    def pred(g: Graph, env: Dict[str, str]) -> bool:
        for gd in guards:
            var  = gd.get("var")
            key  = gd.get("key")
            op   = gd.get("op")
            rhs  = gd.get("value")
            if var is None:
                # allow non-var guards in the future (global switches)
                lhs = None
            else:
                nid = env.get(var)
                if nid is None or not g.has_node(nid):
                    return False
                lhs = g.props(nid).get(key, None)
            try:
                if not _op_eval(lhs, op, rhs):
                    return False
            except Exception:
                return False
        return True

    return pred


# -------------------------------
# Pattern helpers (still generic)
# -------------------------------

def match_var_bindings(g: Graph, vars_spec: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Very simple matcher: for each PatternVar {var, type}, produce all bindings
    where node['type'] == type. Cartesian product across vars.
    Domain-specific matching (e.g., topology) belongs in handlers.
    """
    pools: List[List[Tuple[str, str]]] = []  # list of (var_name, node_id) options
    for vs in vars_spec:
        vname = vs.get("var")
        vtype = vs.get("type")
        if not vname or not vtype:
            return []
        cands = [(vname, nid) for nid in g.find(vtype)]
        if not cands:
            return []
        pools.append(cands)

    # Cartesian product
    envs: List[Dict[str, str]] = [ {} ]
    for pool in pools:
        new_envs = []
        for env in envs:
            for (vname, nid) in pool:
                if nid in env.values():  # avoid same node reused by default
                    continue
                e2 = dict(env); e2[vname] = nid
                new_envs.append(e2)
        envs = new_envs
    return envs


# -------------------------------
# Handler registry interface
# -------------------------------

# A handler compiles ONE rule node into a RuleFn.
# It is passed all the information the domain could need.
Handler = Callable[[Graph, str, Dict[str, Any], List[Dict[str, Any]], Callable[[Graph, Dict[str,str]], bool]], RuleFn]

@dataclass
class CompileContext:
    registry: Dict[str, Handler]  # kind -> handler


# -------------------------------
# Compiler
# -------------------------------

def compile_rules_from_pgr(rg: Graph, ctx: CompileContext) -> List[RuleFn]:
    """
    Walk all nodes of type 'Rule' in the rules-graph and compile them with the
    domain-provided handler registry. Completely domain-agnostic.
    """
    fns: List[RuleFn] = []

    for rid, node in rg.nodes.items():
        if node["type"] != "Rule":
            continue
        props  = node["props"]
        kind   = props.get("kind")
        if not kind:
            continue

        params = get_params(rg, rid)          # dict
        vars_  = get_vars(rg, rid)            # list of {var, type}
        guards = get_guards(rg, rid)          # list of {var, key, op, value}
        guard_pred = make_guard_predicate(guards)

        handler = ctx.registry.get(kind)
        if handler is None:
            # No handler for this kind; ignore silently or raise depending on policy.
            # Raising is usually helpful during development:
            raise ValueError(f"No handler registered for kind='{kind}' (rule id: {rid})")

        fn = handler(rg, rid, params, vars_, guard_pred)
        fns.append(fn)

    return fns


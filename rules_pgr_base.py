# rules_pgr_base.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from kernel import Graph

# Edge labels (kept explicit so you can evolve)
HAS_RULE   = "has_rule"
HAS_PARAM  = "has_param"
HAS_VAR    = "has_var"
HAS_GUARD  = "has_guard"
HAS_BODY   = "has_body"    # optional: for composite rules/macro bodies
REFers     = "ref"         # optional: generic reference

# ---- Creation helpers (domain-agnostic) ----

def add_ruleset(rg: Graph, rid: str = "ruleset", **props: Any) -> str:
    rg.add_node(rid, "RuleSet", **({"name": "default"} | props))
    return rid

def add_rule(rg: Graph, rule_id: str, *, name: str, kind: str, **props: Any) -> str:
    rg.add_node(rule_id, "Rule", name=name, kind=kind, **props)
    rg.add_edge("ruleset", HAS_RULE, rule_id)
    return rule_id

def add_param(rg: Graph, rule_id: str, key: str, value: Any) -> str:
    nid = f"{rule_id}.param.{key}"
    rg.add_node(nid, "Param", key=key, value=value)
    rg.add_edge(rule_id, HAS_PARAM, nid)
    return nid

def add_var(rg: Graph, rule_id: str, var: str, vtype: str) -> str:
    nid = f"{rule_id}.var.{var}"
    rg.add_node(nid, "PatternVar", var=var, type=vtype)
    rg.add_edge(rule_id, HAS_VAR, nid)
    return nid

def add_guard(rg: Graph, rule_id: str, *, var: str, key: str, op: str, value: Any) -> str:
    """Generic atomic guard: op in {<,<=,>,>=,==,!=,in,notin,exists} (you decide in compiler)."""
    gid = f"{rule_id}.guard.{var}.{key}.{op}"
    rg.add_node(gid, "Guard", var=var, key=key, op=op, value=value)
    rg.add_edge(rule_id, HAS_GUARD, gid)
    return gid

# ---- Query helpers (domain-agnostic) ----

def get_params(rg: Graph, rule_id: str) -> Dict[str, Any]:
    out = {}
    for (src, et, dst) in rg.edges:
        if src == rule_id and et == HAS_PARAM:
            p = rg.nodes[dst]["props"]
            out[p["key"]] = p["value"]
    return out

def get_vars(rg: Graph, rule_id: str) -> List[Dict[str, Any]]:
    out = []
    for (src, et, dst) in rg.edges:
        if src == rule_id and et == HAS_VAR:
            out.append(rg.nodes[dst]["props"])
    return out

def get_guards(rg: Graph, rule_id: str) -> List[Dict[str, Any]]:
    out = []
    for (src, et, dst) in rg.edges:
        if src == rule_id and et == HAS_GUARD:
            out.append(rg.nodes[dst]["props"])
    return out

# Convenience: set/replace a threshold guard without domain assumptions
def upsert_threshold_guard(
    rg: Graph, *, rule_name: str, var: str, key: str, op: str, value: Any
) -> bool:
    rid = find_rule_id_by_name(rg, rule_name)
    if not rid: return False
    # update existing?
    for (src, et, dst) in list(rg.edges):
        if src == rid and et == HAS_GUARD:
            gp = rg.nodes[dst]["props"]
            if gp.get("var")==var and gp.get("key")==key and gp.get("op")==op:
                rg.nodes[dst]["props"]["value"] = value
                return True
    add_guard(rg, rid, var=var, key=key, op=op, value=value)
    return True

def find_rule_id_by_name(rg: Graph, name: str) -> Optional[str]:
    for nid, n in rg.nodes.items():
        if n["type"]=="Rule" and n["props"].get("name")==name:
            return nid
    return None


from typing import Dict, Any, List, Tuple
from kernel import Graph

def install_rule_graphs_pgr() -> Graph:
    rg = Graph()
    rg.add_node("ruleset", "RuleSet", name="default")
    # AddSegment
    rg.add_node("R1","Rule",name="AddSegment",kind="AddSegment")
    for k,v in [("length",0.9),("thickness",0.8),("material","aluminum")]:
        pid=f"R1.{k}"; rg.add_node(pid,"Param",key=k,value=v); rg.add_edge("R1","has_param",pid)
    rg.add_edge("ruleset","has_rule","R1")
    # AddBigSegment
    rg.add_node("R1b","Rule",name="AddBigSegment",kind="AddSegment")
    for k,v in [("length",1.6),("thickness",0.9),("material","aluminum")]:
        pid=f"R1b.{k}"; rg.add_node(pid,"Param",key=k,value=v); rg.add_edge("R1b","has_param",pid)
    rg.add_edge("ruleset","has_rule","R1b")
    # IncreaseLength
    rg.add_node("R2","Rule",name="IncreaseLength",kind="IncreaseLength")
    rg.add_node("R2.delta","Param",key="delta",value=0.7); rg.add_edge("R2","has_param","R2.delta")
    rg.add_node("R2.x","PatternVar",var="x",type="Segment"); rg.add_edge("R2","has_var","R2.x")
    rg.add_edge("ruleset","has_rule","R2")
    # IncreaseThickness
    rg.add_node("R3","Rule",name="IncreaseThickness",kind="IncreaseThickness")
    rg.add_node("R3.delta","Param",key="delta",value=0.35); rg.add_edge("R3","has_param","R3.delta")
    rg.add_node("R3.x","PatternVar",var="x",type="Segment"); rg.add_edge("R3","has_var","R3.x")
    rg.add_edge("ruleset","has_rule","R3")
    # AdaptiveFix
    rg.add_node("R6","Rule",name="AdaptiveFix",kind="AdaptiveFix")
    rg.add_node("R6.x","PatternVar",var="x",type="Segment"); rg.add_edge("R6","has_var","R6.x")
    rg.add_node("R6.al","Param",key="alpha_len",value=0.5); rg.add_edge("R6","has_param","R6.al")
    rg.add_node("R6.as","Param",key="alpha_str",value=0.6); rg.add_edge("R6","has_param","R6.as")
    rg.add_edge("ruleset","has_rule","R6")
    # SwapMaterial
    rg.add_node("R4","Rule",name="SwapMaterial",kind="SwapMaterial")
    rg.add_node("R4.x","PatternVar",var="x",type="Segment"); rg.add_edge("R4","has_var","R4.x")
    rg.add_edge("ruleset","has_rule","R4")
    # RemoveShortest
    rg.add_node("R5","Rule",name="RemoveShortest",kind="RemoveShortest")
    rg.add_node("R5.min","Param",key="min_keep",value=1); rg.add_edge("R5","has_param","R5.min")
    rg.add_edge("ruleset","has_rule","R5")
    return rg

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
    for (src,et,dst) in list(rg.edges):
        if src==rid and et=="has_guard":
            rg.nodes[dst]["props"]["value"]=float(max_len)
            return True
    gid="R2.guard.lenlt"
    rg.add_node(gid,"Guard",var="x",op="<",key="length",value=float(max_len))
    rg.add_edge(rid,"has_guard",gid)
    return True

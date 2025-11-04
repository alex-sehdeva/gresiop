# miners.py
from __future__ import annotations
import re
from typing import Dict, Any, List

def mine_prev_value(steps: List[Dict[str, Any]], rule_name: str, prev_key: str = "prev", require_improvement: bool = True) -> List[float]:
    """
    Extract numbers from rule desc like: IncProp(x,length,+0.5,prev=1.234)
    rule_name: 'IncProp' or any prefix before '('
    prev_key:  the key next to the numeric value in the desc (e.g., 'prev' or 'prevL')
    """
    out: List[float] = []
    pat = re.compile(rf"^{re.escape(rule_name)}\([^)]*{re.escape(prev_key)}=([0-9eE\.\-]+)\)")
    for s in steps:
        desc = s.get("rule","")
        if not desc.startswith(rule_name + "("): continue
        if require_improvement and not (s.get("delta_cost", 0) and s["delta_cost"] > 0):
            continue
        m = pat.search(desc)
        if m:
            try: out.append(float(m.group(1)))
            except: pass
    return out


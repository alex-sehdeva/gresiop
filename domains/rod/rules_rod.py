# rules_rod.py
from kernel import Graph
from rules_pgr_base import (
    add_ruleset, add_rule, add_param, add_var, add_guard
)

def install_rules_rod() -> Graph:
    rg = Graph()
    add_ruleset(rg, "ruleset", name="rod-default")

    # AddSegment (template)
    r1 = add_rule(rg, "R1", name="AddSegment", kind="AddSegment")
    add_param(rg, r1, "length",   0.9)
    add_param(rg, r1, "thickness",0.8)
    add_param(rg, r1, "material", "aluminum")

    # AddBigSegment (macro template)
    r1b = add_rule(rg, "R1b", name="AddBigSegment", kind="AddSegment")
    add_param(rg, r1b, "length",   1.6)
    add_param(rg, r1b, "thickness",0.9)
    add_param(rg, r1b, "material", "aluminum")

    # IncreaseLength (pattern var x:Segment; guards can be added later)
    r2 = add_rule(rg, "R2", name="IncreaseLength", kind="IncreaseLength")
    add_param(rg, r2, "delta", 0.7)
    add_var  (rg, r2, "x", "Segment")
    # (guard added later by meta; e.g., length < some_max)

    # IncreaseThickness
    r3 = add_rule(rg, "R3", name="IncreaseThickness", kind="IncreaseThickness")
    add_param(rg, r3, "delta", 0.35)
    add_var  (rg, r3, "x", "Segment")

    # AdaptiveFix (domain-y but still just params/vars — compiler decides behavior)
    r6 = add_rule(rg, "R6", name="AdaptiveFix", kind="AdaptiveFix")
    add_var  (rg, r6, "x", "Segment")
    add_param(rg, r6, "alpha_len", 0.5)
    add_param(rg, r6, "alpha_str", 0.6)

    # SwapMaterial
    r4 = add_rule(rg, "R4", name="SwapMaterial", kind="SwapMaterial")
    add_var  (rg, r4, "x", "Segment")

    # RemoveShortest
    r5 = add_rule(rg, "R5", name="RemoveShortest", kind="RemoveShortest")
    add_param(rg, r5, "min_keep", 1)

    return rg


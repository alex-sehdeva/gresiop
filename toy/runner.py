import json, os
from kernel import Graph, EvalParams
from rules_pgr import install_rule_graphs_pgr
from compiler import compile_rules_from_pgr
from search import search, SearchConfig
from builder_builder import propose_and_eval_guard

def export_svg_rod(g: Graph, path: str):
    segs=[]
    for nid in g.find("Segment"):
        p=g.nodes[nid]["props"]
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

def make_initial_rod(len1=1.0, th1=0.8, mat1="aluminum") -> Graph:
    g=Graph(); g.add_node("rod","Assembly",name="rod-1")
    g.add_node("seg1","Segment",length=float(len1),thickness=float(th1),material=mat1); g.add_edge("rod","has","seg1")
    return g

def run_all(outdir: str):
    os.makedirs(outdir, exist_ok=True)
    rg = install_rule_graphs_pgr()
    with open(os.path.join(outdir,"rules_before.json"),"w") as f: json.dump(rg.to_json(), f, indent=2)
    rules = compile_rules_from_pgr(rg)

    g0 = make_initial_rod()
    ep = EvalParams(load=10.0, target_length=4.0, stress_limit=1.0, lam_len=30.0, lam_str=30.0)
    sc = SearchConfig(iters=120, beam_width=16, novelty_bonus=0.3)
    best_g, best_m, prov = search(g0, rules, ep, sc)
    export_svg_rod(best_g, os.path.join(outdir,"rod_before.svg"))
    with open(os.path.join(outdir,"best_metrics_before.json"),"w") as f: json.dump(best_m, f, indent=2)

    max_len, accept, prov_used, agg_before, agg_after = propose_and_eval_guard(rg, rules, sc, make_initial_rod)

    if max_len is not None and accept:
        rules = compile_rules_from_pgr(rg)
        best_g2, best_m2, prov2 = search(g0, rules, ep, sc)
        export_svg_rod(best_g2, os.path.join(outdir,"rod_after.svg"))
        with open(os.path.join(outdir,"best_metrics_after.json"),"w") as f: json.dump(best_m2, f, indent=2)
    else:
        export_svg_rod(best_g, os.path.join(outdir,"rod_after.svg"))
        with open(os.path.join(outdir,"best_metrics_after.json"),"w") as f: json.dump(best_m, f, indent=2)

    with open(os.path.join(outdir,"rules_after.json"),"w") as f: json.dump(rg.to_json(), f, indent=2)

    meta = {
        "derived_guard": max_len,
        "accepted": accept,
        "golden_before": agg_before,
        "golden_after": agg_after
    }
    with open(os.path.join(outdir,"meta.json"),"w") as f: json.dump(meta, f, indent=2)
    return outdir

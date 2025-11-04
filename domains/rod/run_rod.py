# domains/rod/run_rod.py
from __future__ import annotations
import os
from compiler import CompileContext
from runner_core import run_all
from search import SearchConfig

# domain bits
from domains.rod.rules_rod import install_rules_rod
from domains.rod.rule_handlers import REGISTRY as ROD_REGISTRY
from domains.rod.eval_rod import RodEvaluator, RodParams
from domains.rod.builder_recipes import golden_suite_rod, rod_prevL_miner, ROD_LEN_GUARD

# --- exporter for rods (SVG) ---
def export_svg_rod(g, path: str):
    segs=[]
    for nid in g.find("Segment"):
        p = g.props(nid)
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
    with open(path, "w") as f: f.write(svg)

# --- initial task for 'before' run ---
def pick_initial_task():
    # mirrors first item in golden suite but you can choose differently
    from domains.rod.builder_recipes import make_initial_rod
    g0 = make_initial_rod(1.0, 0.8, "aluminum")
    # RodParams can include target_length, stress_limit, lam_* etc.
    p0 = RodParams(extras={"load": 10.0})
    return g0, p0

def main(outdir: str = "artifacts/rod"):
    os.makedirs(outdir, exist_ok=True)

    # Compile context (domain handler registry)
    ctx = CompileContext(registry=ROD_REGISTRY)

    # Evaluator + search config
    evaluator = RodEvaluator()
    sc = SearchConfig(iters=120, beam_width=16, novelty_bonus=0.3, seed=7)

    run_all(
        outdir=outdir,
        rules_installer=install_rules_rod,
        compile_ctx=ctx,
        evaluator=evaluator,
        pick_initial_task=pick_initial_task,
        exporter=export_svg_rod,
        search_cfg=sc,
        golden_suite_fn=golden_suite_rod,
        miner=rod_prevL_miner,
        guard_spec=ROD_LEN_GUARD,
        reducer="median",
    )

if __name__ == "__main__":
    main()


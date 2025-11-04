# runner_core.py
from __future__ import annotations
import json, os
from dataclasses import dataclass
from typing import Callable, List, Tuple, Dict, Any, Optional

from kernel import Graph, Evaluator, EvalParams, Metrics
from compiler import compile_rules_from_pgr, CompileContext
from search import search, SearchConfig
from builder_core import propose_and_eval_guard

from registry import append_provenance_jsonl

# Hook types
RulesInstaller   = Callable[[], Graph]               # seeds a rule-graph
Exporter         = Callable[[Graph, str], None]      # writes a visualization/file
InitialTaskFn    = Callable[[], Tuple[Graph, EvalParams]]

@dataclass
class RunArtifacts:
    dir: str
    best_before_path: str
    best_after_path: str
    rules_before_path: str
    rules_after_path: str
    meta_path: str

def run_all(
    outdir: str,
    rules_installer: RulesInstaller,
    compile_ctx: CompileContext,
    evaluator: Evaluator,
    pick_initial_task: InitialTaskFn,       # e.g., lambda: (make_initial_*, params)
    exporter: Optional[Exporter],           # may be None if no viz
    search_cfg: SearchConfig,
    # builder-builder hooks:
    golden_suite_fn,                        # returns List[(Graph, EvalParams)]
    miner,                                  # provenance miner -> List[float]
    guard_spec,                             # GuardEditSpec
    reducer: str = "median",
    *,
    domain: str = "generic",
    ruleset_name: Optional[str] = None,
    telemetry: bool = True,
):
    os.makedirs(outdir, exist_ok=True)

    # 1) Seed rules
    rg = rules_installer()
    rules = compile_rules_from_pgr(rg, compile_ctx)
    rules_before_path = os.path.join(outdir, "rules_before.json")
    with open(rules_before_path, "w") as f:
        json.dump(rg.to_json(), f, indent=2)

    # 2) Baseline search on a chosen initial task
    g0, ep0 = pick_initial_task()
    best_g, best_m, prov = search(g0, rules, evaluator, ep0, search_cfg)
    best_before_path = os.path.join(outdir, "best_metrics_before.json")
    with open(best_before_path, "w") as f:
        json.dump({"cost": best_m.cost, "feasible": best_m.feasible, "extras": best_m.extras}, f, indent=2)
    if exporter:
        exporter(best_g, os.path.join(outdir, "artifact_before.svg"))

    # 2a) telemetry
    best_g, best_m, prov = search(g0, rules, evaluator, ep0, search_cfg)
    if telemetry:
        from registry import append_provenance_jsonl
        append_provenance_jsonl(
            outdir,
            domain=domain,
            ruleset_name=ruleset_name or getattr(rules_installer, "__name__", "unknown"),
            steps=prov.steps,
        )

    # 3) Meta: propose guard from provenance and A/B on golden suite
    threshold, accepted, prov_used, agg_before, agg_after = propose_and_eval_guard(
        rg=rg,
        compile_ctx=compile_ctx,
        evaluator=evaluator,
        golden_suite_fn=golden_suite_fn,
        miner=miner,
        guard_spec=guard_spec,
        cfg=search_cfg,
        reducer=reducer,
    )

    # 4) If accepted, recompile and re-run baseline for symmetry
    if threshold is not None and accepted:
        rules2 = compile_rules_from_pgr(rg, compile_ctx)
        best_g2, best_m2, _ = search(g0, rules2, evaluator, ep0, search_cfg)
        best_after = {"cost": best_m2.cost, "feasible": best_m2.feasible, "extras": best_m2.extras}
        if exporter:
            exporter(best_g2, os.path.join(outdir, "artifact_after.svg"))
    else:
        # no change accepted; mirror 'before' for consistency
        best_after = {"cost": best_m.cost, "feasible": best_m.feasible, "extras": best_m.extras}
        if exporter:
            exporter(best_g, os.path.join(outdir, "artifact_after.svg"))

    # 5) Persist rule-graph & meta
    rules_after_path = os.path.join(outdir, "rules_after.json")
    with open(rules_after_path, "w") as f:
        json.dump(rg.to_json(), f, indent=2)

    meta = {
        "derived_threshold": threshold,
        "accepted": bool(accepted),
        "golden_before": agg_before,
        "golden_after": agg_after
    }
    meta_path = os.path.join(outdir, "meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    best_after_path = os.path.join(outdir, "best_metrics_after.json")
    with open(best_after_path, "w") as f:
        json.dump(best_after, f, indent=2)

    return RunArtifacts(
        dir=outdir,
        best_before_path=best_before_path,
        best_after_path=best_after_path,
        rules_before_path=rules_before_path,
        rules_after_path=rules_after_path,
        meta_path=meta_path,
    )


# Builder / Builder-Builder Architecture
*Version 0.3 – November 2025*

This document describes the overall architecture of the **Builder** and **Builder-Builder** framework.
It explains how the core components, domain adapters, search process, and meta-learning loops fit together,
and how to extend the system to new engineering domains.

---

## 1. Purpose and Vision

The goal of this framework is to create *self-improving engineering systems*:
builders that construct candidate designs under evaluators,
and *builder-builders* that refine the builders themselves by observing provenance
and learning new rules or thresholds.

The design follows a minimal-abstraction philosophy:
few core data types (`Graph`, `Rule`, `Evaluator`, `Metrics`, `SearchConfig`) compose into
rich behaviors through *rule graphs* and *meta-loops*.

---

## 2. High-Level Overview

```
┌──────────────────────┐
│   Domain Runner      │  e.g. domains/rod/run_rod.py
└────────┬─────────────┘
         │ calls
         ▼
┌──────────────────────┐
│   runner_core.run_all│  – orchestrates full cycle
└────────┬─────────────┘
         │ uses
         ▼
┌───────────────────────────────────────┐
│  Core Engine Components               │
│   • kernel.py – Graph & types         │
│   • compiler.py – rule compiler       │
│   • search.py – beam search engine    │
│   • builder_core.py – builder-builder │
└───────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────┐
│  Domain Packages (e.g. domains/rod)       │
│   • rules_rod.py – seed rule graph        │
│   • rule_handlers.py – rule handlers      │
│   • eval_rod.py – evaluator               │
│   • builder_recipes.py – miners & guards  │
│   • adapter.py – optional vocab mapping   │
└───────────────────────────────────────────┘
```

All telemetry is logged into `artifacts/<domain>/rule_telemetry.jsonl`
and can be aggregated across domains for meta-analysis.

---

## 3. Core Modules

### 3.1 `kernel.py`
Defines the universal **graph model** and data contracts like `Graph`, `EvalParams`, `Metrics`, and `RuleResult`.

### 3.2 `rules_pgr_base.py`
Defines the *Program/Graph/Rule* (P/G/R) schema for declarative rule graphs.

### 3.3 `compiler.py`
Translates a rule graph into executable `RuleFn` callables. Uses domain-specific or standard registries.

### 3.4 `rule_handlers_std.py`
A *standard library* of reusable rule kinds (`AddNode`, `AddEdge`, `IncProp`, etc.).

### 3.5 `search.py`
Implements **beam search** with provenance tracking for iterative design improvement.

### 3.6 `builder_core.py`
Implements the *Builder-Builder* loop that proposes and evaluates new guards.

### 3.7 `runner_core.py`
Domain-agnostic orchestration of the full build + meta-build pipeline.

### 3.8 `registry.py`
Logs provenance telemetry (`rule_telemetry.jsonl`) for global rule usefulness aggregation.

---

## 4. Domain Packages

Each domain (e.g. `rod`, `pcb`) defines:
- rules
- evaluators
- miners
- adapters
- runners

All other logic is shared across domains.

---

## 5. Execution Flow

1. Compile rule graph → functions.  
2. Run search → best design.  
3. Log provenance.  
4. Mine provenance → new thresholds.  
5. Rerun golden suite → accept/reject update.  
6. Export artifacts & telemetry.

---

## 6. Cross-Domain Reuse

Shared components:
- Rule handlers (via `rule_handlers_std`)
- Provenance miners
- Evaluator scaffolding
- Runner core + telemetry

Each domain remains a thin adapter layer over the shared core.

---

## 7. Next Directions

- Parameter tuning (not just guard updates)
- Shared global telemetry hub (~/.builderlab/telemetry)
- Learned rule embeddings for transfer
- Multi-objective optimization
- Visual dashboard for provenance evolution

---

*End of Document*

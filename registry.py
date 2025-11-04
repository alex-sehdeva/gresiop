# registry.py
from __future__ import annotations
import json, os, datetime
from typing import List, Dict, Any

def append_provenance_jsonl(outdir: str, domain: str, ruleset_name: str, steps: List[Dict[str, Any]]):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "rule_telemetry.jsonl")
    meta = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "domain": domain,
        "ruleset": ruleset_name,
    }
    with open(path, "a", encoding="utf-8") as f:
        for s in steps:
            row = dict(meta); row.update(s)
            f.write(json.dumps(row) + "\n")


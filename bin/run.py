"""
Universal domain runner.

Usage:
  python -m bin.run --domain rod --outdir artifacts/rod --iters 120 --beam-width 16 --novelty-bonus 0.3 --seed 7
  python -m bin.run --list

It dynamically imports domains.<domain>.run_<domain> and calls its `main(...)`,
passing only the arguments it accepts (signature introspection).
"""
from __future__ import annotations
import argparse, importlib, inspect, pkgutil, sys
from typing import Dict, Any

def discover_domains() -> Dict[str, str]:
    """Return map: domain_name -> module_path for run_<domain>.py files."""
    found = {}
    try:
        pkg = importlib.import_module("domains")
    except Exception:
        return found
    pkgpath = pkg.__path__  # type: ignore[attr-defined]
    for _, modname, ispkg in pkgutil.iter_modules(pkgpath):
        if not ispkg:
            continue
        run_mod = f"domains.{modname}.run_{modname}"
        try:
            importlib.import_module(run_mod)
            found[modname] = run_mod
        except Exception:
            pass
    return found

def coerce_kwargs_for(func, cand_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Filter cand_kwargs to only those accepted by func, with correct names."""
    sig = inspect.signature(func)
    accepted = {}
    for k, v in cand_kwargs.items():
        if k in sig.parameters:
            accepted[k] = v
    return accepted

def main(argv=None):
    parser = argparse.ArgumentParser(prog="bin.run", description="Domain runner dispatcher")
    parser.add_argument("--domain", "-d", help="Domain to run (e.g., rod)")
    parser.add_argument("--outdir", "-o", default="artifacts/run", help="Output directory")
    parser.add_argument("--iters", type=int, default=None, help="Search iterations override (optional)")
    parser.add_argument("--beam-width", type=int, default=None, help="Beam width override (optional)")
    parser.add_argument("--novelty-bonus", type=float, default=None, help="Novelty bonus override (optional)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (optional)")
    parser.add_argument("--list", action="store_true", help="List available domains and exit")

    args = parser.parse_args(argv)

    domains = discover_domains()
    if args.list or not args.domain:
        if not domains:
            print("No domains discovered. Make sure you have a 'domains' package with subpackages like 'rod' containing run_rod.py")
        else:
            print("Available domains:")
            for k, v in sorted(domains.items()):
                print(f"  - {k}  ({v})")
        if not args.domain:
            return 0

    if args.domain not in domains:
        print(f"Domain '{args.domain}' not found. Use --list to see available domains.", file=sys.stderr)
        return 2

    run_mod_path = domains[args.domain]
    mod = importlib.import_module(run_mod_path)
    if not hasattr(mod, "main"):
        print(f"Module {run_mod_path} has no 'main' function.", file=sys.stderr)
        return 3

    raw_kwargs = {
        "outdir": args.outdir,
        "iters": args.iters,
        "beam_width": args.beam_width,
        "novelty_bonus": args.novelty_bonus,
        "seed": args.seed,
    }
    raw_kwargs = {k: v for k, v in raw_kwargs.items() if v is not None}

    main_fn = getattr(mod, "main")
    kwargs = coerce_kwargs_for(main_fn, raw_kwargs)

    return int(bool(main_fn(**kwargs)))

if __name__ == "__main__":
    raise SystemExit(main())

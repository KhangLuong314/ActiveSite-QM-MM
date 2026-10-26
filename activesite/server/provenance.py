"""Number provenance for chat replies (AGENTS.md rule 2: never fabricate a number).

Every quantity with a unit in a chat reply (kcal/mol, Å, K, ps, fs) must either appear in the run context the
reply was built from (stats, cards, report, prep, MD stability) or be a fixed method setting (a threshold or
input parameter, not a result). Anything else is marked in the reply so a reader can see it did not come from a
run. This applies to the rule-based answers and to Nemotron replies alike.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

FLAG = " ⚠ not from a run"

# Method settings, not results: pocket contact <= 4.0 A, clash floor 1.8 A, H-bond 3.3 A, pocket radius 8.0 A,
# Mg first shell 2.8 A, GMAX limit 10.0 kcal/mol/A, pH 7.4, MD 1.0 fs step, 1 ps, 300 K target, 1000 steps.
METHOD_SETTINGS = {298.15, 4.0, 1.8, 3.3, 8.0, 2.8, 10.0, 7.4, 1.0, 300.0, 1000.0, 100.0, 2.0, 12.0, 5.0, 6.0}

UNIT = r"(?:kcal/mol(?:/Å)?|kcal\s*mol-1|Å|K\b|ps\b|fs\b)"
QUANTITY = re.compile(r"(?<![\w.])([-+−]?\d[\d,]*(?:\.\d+)?)(\s*(?:±\s*[\d.]+\s*)?)(" + UNIT + ")")
NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _to_float(text: str) -> float | None:
    try:
        return float(text.replace("−", "-").replace(",", ""))
    except ValueError:
        return None


def context_numbers(ctx: Dict[str, Any]) -> List[float]:
    """Every number that appears anywhere in the run context (JSON values and report text)."""
    blob = json.dumps({k: ctx.get(k) for k in ("stats", "result", "cards", "prep", "md_stability", "report_markdown")},
                      default=str)
    return [float(m) for m in NUMBER.findall(blob)]


def _supported(value: float, known: List[float]) -> bool:
    if abs(value) in METHOD_SETTINGS:
        return True
    return any(abs(value - k) <= max(0.01, abs(k) * 1e-3) or abs(abs(value) - abs(k)) <= max(0.01, abs(k) * 1e-3)
               for k in known)


def guard(reply: str, ctx: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Mark every unit-bearing number that is neither in the run context nor a method setting."""
    known = context_numbers(ctx)
    flagged: List[str] = []

    def mark(m: re.Match) -> str:
        value = _to_float(m.group(1))
        if value is None or _supported(value, known):
            return m.group(0)
        flagged.append(m.group(0).strip())
        return m.group(0) + FLAG

    return QUANTITY.sub(mark, reply), flagged

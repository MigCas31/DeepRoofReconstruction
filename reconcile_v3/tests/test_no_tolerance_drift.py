"""Grep reconcile_v3/ for float literals in the tolerance range outside constants.py.

Keeps the "one source of truth for thresholds" invariant. Allow-listed
literals are angles, probabilities, and epsilons far outside the
distance-tolerance range.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
FLOAT_RE = re.compile(r"(?<![\w.])(\d+\.\d+)")

TOL_LOW, TOL_HIGH = 0.01, 2.0
ALLOWED = {
    "0.1",
    "0.4",
    "0.5",
    "1.0",
    "1e-4",
    "1e-6",
}


def _python_sources() -> list[Path]:
    return [
        p
        for p in PKG.rglob("*.py")
        if "tests" not in p.parts and p.name != "constants.py"
    ]


def test_no_tolerance_drift():
    offenders: list[str] = []
    for path in _python_sources():
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if "#" in line:
                line = line.split("#", 1)[0]
            for match in FLOAT_RE.finditer(line):
                text = match.group(1)
                if text in ALLOWED:
                    continue
                try:
                    value = float(text)
                except ValueError:
                    continue
                if TOL_LOW <= value <= TOL_HIGH:
                    offenders.append(f"{path.relative_to(PKG)}:{lineno} -> {text}")
    assert not offenders, (
        "Distance-tolerance literals must live in reconcile_v3/constants.py. "
        "Offenders:\n  " + "\n  ".join(offenders)
    )

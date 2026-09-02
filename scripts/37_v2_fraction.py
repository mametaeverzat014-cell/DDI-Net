#!/usr/bin/env python
"""Derive the 8-configuration fraction of the frozen 32-configuration grid.

The preregistered grid is a full 2^5 factorial over five binary axes. Cutting it
to 8 is a preregistration amendment (docs/V2_PREREGISTRATION_AMENDMENT_FRACTION.md),
and the rule below is what that amendment declares. It is stated in terms of the
frozen YAML alone, so it can be re-derived by anyone without seeing any result.

Rule
----
A 2^(5-2) fractional factorial. Axes are coded from the frozen YAML: the
first-listed level of each axis is -1, the second is +1.

    A = bio_dim        (64  -> -1, 128 -> +1)
    B = dropout_bio    (0.1 -> -1, 0.3 -> +1)
    C = dropout_pair   (0.1 -> -1, 0.2 -> +1)
    D = lr             (1e-3 -> -1, 3e-4 -> +1)
    E = batch_size     (256 -> -1, 512 -> +1)

A, B, C run as a full factorial (8 points); the remaining two axes are generated

    D = -A*B        E = -A*C

The negative signs anchor the fraction at the reference corner (-,-,-,-,-),
i.e. the first-listed level of every axis. That anchor is fixed by the frozen
YAML's own ordering, not by any observed metric.

Consequence, stated plainly: the defining relation is I = -ABD = -ACE = BCDE,
so the design is resolution III. All five main effects are estimable, but each
is aliased with one or two two-factor interactions:

    A = -BD = -CE      B = -AD      C = -AE      D = -AB      E = -AC

That aliasing is the price of the cut and cannot be removed at 8 runs with five
factors: resolution III is the maximum available for 2^(5-2).
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

#: Axis order is fixed here and must match the frozen YAML's key order.
AXES = ["bio_dim", "dropout_bio", "dropout_pair", "lr", "batch_size"]


def load_levels() -> dict[str, list]:
    grid = yaml.safe_load((ROOT / "configs" / "v2_preregistered.yaml").read_text())
    levels = grid["hparam_search"]["grid"]
    for axis in AXES:
        if len(levels[axis]) != 2:
            raise ValueError(f"axis {axis} is not binary: {levels[axis]}")
    return levels


def fraction() -> list[dict]:
    """The 8 configurations, in a deterministic order."""
    levels = load_levels()
    chosen = []
    for a, b, c in itertools.product((-1, 1), repeat=3):
        d = -a * b
        e = -a * c
        code = dict(zip(AXES, (a, b, c, d, e)))
        chosen.append({axis: levels[axis][0 if code[axis] < 0 else 1]
                       for axis in AXES} | {"_code": code})
    return chosen


def main() -> int:
    chosen = fraction()
    if len(chosen) != 8:
        print(f"STOP: expected 8 configurations, derived {len(chosen)}")
        return 1
    keys = {tuple(c[a] for a in AXES) for c in chosen}
    if len(keys) != 8:
        print("STOP: derived configurations are not distinct")
        return 1

    print(f"{'bio_dim':>8} {'drop_bio':>9} {'drop_pair':>10} {'lr':>8} {'batch':>6}   code")
    for c in chosen:
        code = "".join("+" if c["_code"][a] > 0 else "-" for a in AXES)
        print(f"{c['bio_dim']:8d} {c['dropout_bio']:9g} {c['dropout_pair']:10g} "
              f"{c['lr']:8g} {c['batch_size']:6d}   {code}")

    # Every axis must appear at both levels exactly four times: a balanced
    # fraction is the whole point, and an unbalanced one would silently
    # confound an axis with the choice of fraction.
    print()
    for axis in AXES:
        counts = {}
        for c in chosen:
            counts[c[axis]] = counts.get(c[axis], 0) + 1
        ok = sorted(counts.values()) == [4, 4]
        print(f"{axis:14s} {counts}  {'сбалансирована' if ok else 'НЕ СБАЛАНСИРОВАНА'}")
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

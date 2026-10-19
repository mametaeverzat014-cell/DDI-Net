#!/usr/bin/env python3
"""Generate web/src/data/v3facts.json from the DDI-Net 3.0 measurement reports.

The site's rule since v2: no scientific number is typed by hand. The three
DDI-Net 3.0 diagnostics live in reports/v3_*.json, written by scripts/61-63;
this tool copies the figures the site quotes, and tests/test_v3_site_facts.py
asserts the committed file equals a fresh regeneration.

    python3 web/tools/build_v3_facts.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "src" / "data" / "v3facts.json"


def build() -> dict:
    rep = ROOT / "reports"
    direction = json.loads((rep / "v3_tdc_direction_audit.json").read_text())
    seeds = json.loads((rep / "v3_seed_disagreement.json").read_text())
    cov = json.loads((rep / "v3_coverage_reliability.json").read_text())
    return {
        "direction_audit": {
            "source": "reports/v3_tdc_direction_audit.json",
            "verified_threshold": direction["verified_threshold"],
            "n_records": direction["n_records"],
            "records_by_status": direction["records_by_status"],
            "pk_types": {
                k: {f: v[f] for f in ("template", "n_informative", "n_consistent", "n_reversed", "consistency", "status")}
                for k, v in direction["pk_types"].items()
            },
        },
        "seed_disagreement": {
            "source": "reports/v3_seed_disagreement.json",
            "views": {
                v: {f: r[f] for f in ("n_pairs", "auroc_sd_detects_error", "auroc_sd_detects_error_ci95",
                                      "auroc_margin_detects_error", "spearman_sd_abs_error")}
                for v, r in seeds["views"].items()
            },
        },
        "coverage_reliability": {
            "source": "reports/v3_coverage_reliability.json",
            "views": cov["views"],
        },
    }


def main() -> None:
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Internal consistency audit for the DDI-Net manuscript.

Checks, in order:

1. **Numeric claims.** Every headline value asserted in the manuscript is
   compared against ``FACTS.json``, which ``build_tables.py`` derives from the
   frozen tag. A mismatch is an error, not a warning.
2. **Label discipline.** Confirmatory/exploratory labels, the number of seeds,
   the selected config ID, the Holm family size and the dataset counts must
   appear as stated.
3. **Dangerous phrases.** Clinical, causal and patient-specific language is
   flagged for manual review in context. Flagging is deliberately noisy: the
   point is to force a human to look at each occurrence, not to auto-approve.
4. **Citations.** Every ``[key]`` cited in the manuscript must exist in
   ``references.bib``, and every bib entry should be cited somewhere.

Exit code 0 only if there are no errors.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE / "DDI_NET_ISEF_RESEARCH_PAPER.md"
FACTS = json.loads((HERE / "FACTS.json").read_text())
RAW = PAPER.read_text()

#: Substring checks run against a normalised copy: line wrapping must not hide a
#: phrase, and the manuscript uses typographic minus (U+2212) and non-breaking
#: spaces where a naive ASCII match would fail. Normalising here rather than
#: forcing ASCII into the prose keeps the manuscript typographically correct.
TEXT = re.sub(r"\s+", " ", RAW.replace("−", "-").replace(" ", " "))

errors: list[str] = []
warnings: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        errors.append(f"{label}: {detail}")


def approx_in_text(value: float, decimals: int, *, text: str = TEXT) -> bool:
    """Is `value`, rounded to `decimals`, present in the manuscript text?

    Rounding rather than exact matching because the prose quotes values at
    display precision (0.8117) while the frozen file holds full precision
    (0.8117107056824635). Both must denote the same number.
    """
    return f"{value:.{decimals}f}" in text


# ------------------------------------------------------------ 1. model values
for key, decimals in [
    ("M4_pooled", 4), ("M4_s3", 4),
    ("M0_pooled", 4), ("M0_s3", 4),
    ("Dual_pooled", 4), ("Dual_s3", 4),
    ("BIO_RF_pooled", 4), ("degree_RF_pooled", 4),
    ("M4_shuffled_pooled", 4), ("M4_shuffled_s3", 4),
    ("M1_pooled", 4), ("M2_pooled", 4), ("M3_pooled", 4), ("M4_SUM_pooled", 4),
    ("M1_s3", 4), ("M2_s3", 4), ("M3_s3", 4), ("M4_SUM_s3", 4),
]:
    m = FACTS["models"][key]["mean"]
    check(f"mean {key}", approx_in_text(m, decimals),
          f"{m:.{decimals}f} not found in manuscript")
    check(f"n_seeds {key}", FACTS["models"][key]["n"] == 5,
          f"expected 5 seeds, got {FACTS['models'][key]['n']}")

for key in ["M4_pooled", "M4_s3", "M0_pooled", "Dual_s3", "degree_RF_pooled"]:
    s = FACTS["models"][key]["std"]
    check(f"std {key}", approx_in_text(s, 4), f"{s:.4f} not found in manuscript")

# -------------------------------------------------------------- 2. hypotheses
for hid, decimals in [("H-V2-1", 4), ("H-V2-2", 4), ("H-V2-3", 4),
                      ("H-V2-4", 4), ("H-V2-5", 4)]:
    h = FACTS["hypotheses"][hid]
    check(f"{hid} delta", approx_in_text(abs(h["delta_mean"]), decimals),
          f"|delta| {abs(h['delta_mean']):.{decimals}f} not in manuscript")
    check(f"{hid} ci_low", approx_in_text(h["ci95_low"], 4),
          f"CI low {h['ci95_low']:.4f} not in manuscript")
    check(f"{hid} ci_high", approx_in_text(h["ci95_high"], 4),
          f"CI high {h['ci95_high']:.4f} not in manuscript")

# Holm-adjusted p-values are quoted in scientific notation in the prose.
for hid, expected in [
    ("H-V2-1", "1.98 × 10⁻⁴"), ("H-V2-2", "6.56 × 10⁻⁴"),
    ("H-V2-3", "1.83 × 10⁻⁴"), ("H-V2-4", "1.67 × 10⁻⁵"),
]:
    check(f"{hid} holm p quoted", expected in TEXT,
          f"expected Holm p rendering {expected!r} absent")
    # and that rendering must actually match the frozen value
    mantissa, exponent = expected.split(" × 10")
    exp = int(exponent.replace("⁻", "-").translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")))
    quoted = float(mantissa) * 10 ** exp
    actual = FACTS["hypotheses"][hid]["holm_adjusted_p"]
    check(f"{hid} holm p value", abs(quoted - actual) / actual < 0.01,
          f"quoted {quoted:.3e} vs frozen {actual:.3e}")

check("H5 p quoted", "0.157" in TEXT, "H5 p-value 0.157 absent")
check("H5 labelled exploratory",
      FACTS["hypotheses"]["H-V2-5"]["status"] == "EXPLORATORY"
      and "exploratory" in TEXT.lower(), "H5 not labelled exploratory")
check("H5 not called failed",
      not re.search(r"H5[^.]{0,80}failed (confirmatory )?hypothesis", TEXT, re.I),
      "H5 described as a failed hypothesis")
check("H5 correct phrase", "not supported" in TEXT.lower()
      or "direction unsupported" in TEXT.lower(),
      "H5 unsupported-direction wording absent")

# Holm family size must be stated as five, never four.
check("Holm family = 5", "all five preregistered hypotheses" in TEXT,
      "manuscript does not state the Holm family is five")
check("Holm family not four",
      not re.search(r"Holm[^.]{0,60}four (confirmatory )?hypothes", TEXT, re.I),
      "manuscript describes a four-hypothesis Holm family")

# ------------------------------------------------------- 3. protocol constants
check("config id", FACTS["selected_config_id"] in TEXT, "selected config ID absent")
check("five seeds stated", "five seeds" in TEXT.lower(), "'five seeds' absent")
check("96 validation runs", "96 validation runs" in TEXT, "96 validation runs absent")
check("32 configurations", "32 configurations" in TEXT, "32 configurations absent")
check("no 8x3 fraction",
      "fractional replicate" not in TEXT and "8x3" not in TEXT and "8 × 3" not in TEXT,
      "superseded fractional grid mentioned in the manuscript")
check("test n pooled", f"{FACTS['test_n_pooled']:,}" in TEXT, "pooled test n absent")
check("test n s3", f"{FACTS['test_n_s3']:,}" in TEXT, "S3 test n absent")
check("dataset drugs", "1,705" in TEXT, "1,705 drugs absent")
check("dataset pairs", "191,392" in TEXT, "191,392 pairs absent")
check("S3 definition", "both" in TEXT and "zero interaction adjacency" in TEXT.lower()
      or "both drugs have zero" in TEXT.lower() or "both* drugs are unseen" in TEXT,
      "S3 definition not stated")

# ------------------------------------------------------------- 4. CONTROL E
check("control E variance",
      "zero variance" in TEXT.lower(), "CONTROL E zero-variance wording absent")
check("control E undefined",
      "undefined" in TEXT.lower() or "not identifiable" in TEXT.lower(),
      "CONTROL E identifiability wording absent")
check("control E train r2", "0.543" in TEXT, "CONTROL E train R^2 absent")
check("control E no false claim",
      not re.search(r"R²\s*=\s*0[^.]{0,60}(shows|proves|demonstrates)", TEXT),
      "manuscript interprets R^2 = 0 as evidence")
check("control E variance is zero in facts",
      FACTS["control_e"]["held_out_target_variance"] == 0.0
      and FACTS["control_e"]["identifiable"] is False,
      "FACTS disagrees about CONTROL E")

# ------------------------------------------------------------ 5. scaffold gap
check("scaffold not claimed",
      "not performed in the final study" in TEXT or "was not evaluated" in TEXT.lower(),
      "scaffold-disjoint gap not stated")
check("scaffold no result claimed",
      not re.search(r"scaffold-disjoint[^.]{0,40}(AUPRC|achieved|reached)", TEXT, re.I),
      "a scaffold-disjoint result appears to be claimed")

# -------------------------------------------------- 6. non-monotonic honesty
check("non-monotonic stated", "non-monotonic" in TEXT.lower(),
      "ablation ladder not described as non-monotonic")
check("M2 peak acknowledged",
      "M2" in TEXT and ("peak" in TEXT.lower() or "weakest of M1" in TEXT),
      "M2 outperforming M4 not acknowledged")
check("CONTROL C outperformance stated",
      "CONTROL C outperformed" in TEXT or "SUM aggregation reached" in TEXT,
      "CONTROL C beating the primary model not stated")

# ------------------------------------------------------- 7. dangerous phrases
DANGEROUS = {
    r"\bclinically safe\b": "prohibited clinical-safety claim",
    r"\bis safe\b": "safety claim",
    r"\bunsafe\b": "safety claim",
    r"\bproves\b": "causal/proof language",
    r"\bproven mechanism\b": "causal claim",
    r"\bdiagnos(is|es|e|ing)\b": "clinical claim",
    r"\brecommends? medication\b": "clinical recommendation",
    r"\bguarantees?\b": "overclaim",
    r"\bpersonalized risk\b": "patient-specific claim",
    r"\bpersonalised risk\b": "patient-specific claim",
    r"\bfor (children|elderly)\b": "age-specific capability claim",
    r"\bfully models? metabolism\b": "PK overclaim",
    r"\bclinically validated\b": "clinical validation claim",
}
for pattern, why in DANGEROUS.items():
    for m in re.finditer(pattern, TEXT, re.I):
        start = max(0, m.start() - 110)
        context = TEXT[start:m.end() + 110].replace("\n", " ")
        warnings.append(f"[{why}] ...{context}...")

# "causes" is checked separately: it is legitimate in negated form.
for m in re.finditer(r"\bcause[sd]?\b", TEXT, re.I):
    start = max(0, m.start() - 130)
    context = TEXT[start:m.end() + 130].replace("\n", " ")
    warnings.append(f"[causal language - verify negation] ...{context}...")

# ------------------------------------------------------------- 8. citations
bib = (HERE / "references.bib").read_text()
bib_keys = set(re.findall(r"@\w+\{([^,]+),", bib))
cited = set(re.findall(r"\[([a-z]+\d{4}[a-z]*)(?:,\s*[a-z]+\d{4}[a-z]*)*\]", TEXT))
cited |= {k.strip() for grp in re.findall(r"\[((?:[a-z]+\d{4}[a-z]*)(?:,\s*[a-z]+\d{4}[a-z]*)+)\]", TEXT)
          for k in grp.split(",")}
for key in sorted(cited):
    check(f"citation {key}", key in bib_keys, f"[{key}] cited but not in references.bib")
for key in sorted(bib_keys - cited):
    warnings.append(f"[bib] {key} present in references.bib but never cited")

# ----------------------------------------------------------------- reporting
print("=" * 78)
print("DDI-NET MANUSCRIPT CONSISTENCY AUDIT")
print("=" * 78)
print(f"frozen tag        : {FACTS['frozen_tag']}")
print(f"frozen commit     : {FACTS['frozen_commit']}")
print(f"numeric/label checks run : {checks}")
print(f"errors            : {len(errors)}")
print(f"phrases to review : {len(warnings)}")
print()

if errors:
    print("ERRORS")
    print("-" * 78)
    for e in errors:
        print(f"  FAIL  {e}")
    print()
else:
    print("All numeric and label checks passed.\n")

if warnings:
    print("FLAGGED FOR MANUAL REVIEW IN CONTEXT")
    print("-" * 78)
    for w in warnings:
        print(f"  ?  {w}")
    print()

sys.exit(1 if errors else 0)

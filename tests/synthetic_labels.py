"""Synthetic openFDA label responses shaped like the real ones that duplicate text.

SYNTHETIC TEST FIXTURES. Set IDs are all zeros, the manufacturer is "SYNTHETIC
TEST FIXTURE", and every sentence carries "[synthetic]". None of it is, or may be
presented as, a real label statement.

What they reproduce is a STRUCTURE seen in real labels:

* An older-format (non-PLR) label keeps its "Drug Interactions" subsection inside
  PRECAUTIONS, and openFDA also returns that same subsection as a separate
  `drug_interactions` field. A partner named there is therefore matched twice,
  once per field — the same sentence under two section names.
* The copy in one field may carry a heading prefix ("7 DRUG INTERACTIONS") the
  other lacks, so the two sentences overlap without being identical.
* A newer-format (PLR) label names the partner in two genuinely different places
  (a table row of CYP2C9 inhibitors, and a separate sentence), which must stay
  two findings.
"""

from __future__ import annotations

import json
import urllib.parse

FLUCONAZOLE_SET = "00000000-0000-0000-0000-0000000000f1"
WARFARIN_SET = "00000000-0000-0000-0000-0000000000a1"

_DI_SUBSECTION = (
    "Oral hypoglycemics: [synthetic] Clinically significant hypoglycemia may be precipitated by the use of "
    "fixturazole with oral hypoglycemic agents in this fixture. "
    "Coumarin-type anticoagulants: [synthetic] Prothrombin time may be increased in patients receiving "
    "concomitant fluconazole and warfarin in this test fixture, and bleeding events have been reported in "
    "association with increases in prothrombin time. "
    "[synthetic] Careful monitoring of prothrombin time in patients receiving fluconazole and warfarin is "
    "described in this fixture sentence. "
    "Phenytoin: [synthetic] Fixture sentence about another drug."
)


def _label(set_id: str, generic: str, effective: str, **sections) -> dict:
    return {
        "set_id": set_id, "id": set_id.replace("0000-0000", "1111-2222"), "version": "7",
        "effective_time": effective,
        **{k: [v] for k, v in sections.items()},
        "openfda": {"generic_name": [generic], "brand_name": ["SYNTHETIC"], "substance_name": [generic],
                    "product_type": ["HUMAN PRESCRIPTION DRUG"], "manufacturer_name": ["SYNTHETIC TEST FIXTURE"]},
    }


FLUCONAZOLE_OLD_FORMAT = _label(
    FLUCONAZOLE_SET, "FLUCONAZOLE", "20250301",
    warnings="WARNINGS [synthetic] Hepatic injury fixture sentence. Anaphylaxis fixture sentence.",
    precautions="PRECAUTIONS General: [synthetic] Fixture sentence. Drug Interactions: " + _DI_SUBSECTION,
    # openFDA's separate field: the same subsection, here with a heading prefix glued on.
    drug_interactions="7 DRUG INTERACTIONS " + _DI_SUBSECTION,
)

WARFARIN_PLR = _label(
    WARFARIN_SET, "WARFARIN SODIUM", "20240915",
    warnings_and_cautions=(
        "5.1 Hemorrhage [synthetic] Fixture sentence about bleeding risk. "
        "[synthetic] Drugs such as fluconazole that inhibit CYP2C9 are named in this separate fixture sentence."
    ),
    drug_interactions=(
        "7.2 CYP450 Interactions [synthetic] Table 2 fixture row — CYP2C9 inhibitors: amiodarone, capecitabine, "
        "cotrimoxazole, fluconazole, fluvastatin, metronidazole, miconazole, voriconazole"
    ),
)


class FakeLabelTransport:
    """Routes openFDA generic-name searches to the synthetic labels above."""

    def __init__(self, routes: dict[str, dict] | None = None):
        self.routes = routes or {
            'generic_name:"fluconazole"': FLUCONAZOLE_OLD_FORMAT,
            'generic_name:"warfarin"': WARFARIN_PLR,
        }
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.calls.append(url)
        decoded = urllib.parse.unquote(url)
        for key, label in self.routes.items():
            if key in decoded:
                return 200, json.dumps({"meta": {"results": {"total": 1}}, "results": [label]}).encode()
        return 404, json.dumps({"error": {"code": "NOT_FOUND", "message": "No matches found!"}}).encode()

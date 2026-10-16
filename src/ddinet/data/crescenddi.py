"""CRESCENDDI reference set -> compact, DrugBank-keyed index for the evidence layer.

Source: Kontsioti E, Maskell S, Dutta B, Pirmohamed M. A reference set of
clinically relevant adverse drug-drug interactions. Sci Data 9, 72 (2022).
https://doi.org/10.1038/s41597-022-01159-y. Data records as published in the
authors' repository https://github.com/elpidakon/CRESCENDDI (MIT License),
pinned to one commit and checked by SHA-256.

What a record says. A POSITIVE control is a drug pair documented as interacting
in all three compendia the authors used (BNF, Nov 2018; IBM Micromedex,
Sep 2018; ANSM Thesaurus, Sep 2019), with an adverse event (MedDRA preferred
term) that the authors mapped from the BNF and/or Micromedex interaction text.
A NEGATIVE control is a pair with an event judged unrelated to the pair.

What is deliberately NOT carried over:
* the compendia's severity and evidence ratings (BNF_SEV_LEVEL, ANSM_SEV_LEVEL,
  MICROMEDEX_SEV_LEVEL, BNF_EVID_LEVEL, MICROMEDEX_EVID_LEVEL). They are the
  editorial classifications of proprietary references; the app does not
  republish them;
* Data Record 3 (single-drug ADRs), partly derived from SIDER (CC BY-NC-SA);
* any text of the compendia (CRESCENDDI itself does not contain it).

Pipeline: fetch (pinned, checksummed) -> schema validation -> drug mapping to
the project's 1,705-drug universe (exact INN/curated-alias match only; no
fuzzy matching) -> self-pair removal -> de-duplication -> positive/negative
conflict removal -> deterministic gzip JSON + manifest.
"""

from __future__ import annotations

import gzip
import io
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .git_fetch import PinnedFiles, sha256_file

SCHEMA_VERSION = "crescenddi_index/v1"
POSITIVE = "Data Record 1 - Positive Controls.xlsx"
NEGATIVE = "Data Record 2 - Negative Controls.xlsx"
SPEC = PinnedFiles(
    key="crescenddi",
    repo_url="https://github.com/elpidakon/CRESCENDDI",
    commit="1734d7c12ac16e3df03c4a53cb40226f456c92c9",
    files={
        f"data_records/{POSITIVE}": "9e001a6ef078029c4fe7fa4addd4f0e4ad1255ac024d91c5cdbaec9cc07bc22a",
        f"data_records/{NEGATIVE}": "0d264662ebba4351e32d4942fb4c66b57f3d5e3b4060eae1ea347f91b006b894",
    },
)
SOURCE = {
    "name": "CRESCENDDI reference set of clinically relevant adverse drug-drug interactions",
    "citation": "Kontsioti E, Maskell S, Dutta B, Pirmohamed M. A reference set of clinically relevant adverse "
                "drug-drug interactions. Sci Data 9, 72 (2022). doi:10.1038/s41597-022-01159-y",
    "repository": SPEC.repo_url,
    "commit": SPEC.commit,
    "figshare": "https://doi.org/10.6084/m9.figshare.c.5481408",
    "license": "MIT License (authors' GitHub repository, which contains the data records); "
               "figshare licence not verified from the build environment",
    "underlying_sources": "BNF (Nov 2018), IBM Micromedex (Sep 2018), ANSM Thesaurus (Sep 2019); "
                          "events mapped to MedDRA by the authors (OHDSI Usagi)",
    "not_carried_over": "compendium severity and evidence ratings; single-drug Data Record 3; any compendium text",
}

POS_COLUMNS = {"DRUG_1_CONCEPT_NAME": str, "DRUG_2_CONCEPT_NAME": str, "EVENT_CONCEPT_NAME": str,
               "MDR_CODE": int, "EVENT_SOURCE": str}
NEG_COLUMNS = {"DRUG_1_CONCEPT_NAME": str, "DRUG_2_CONCEPT_NAME": str, "EVENT_CONCEPT_NAME": str,
               "MDR_CODE": int}
EVENT_SOURCES = {"BNF", "Micromedex", "BNF+Micromedex"}

Lookup = Callable[[str], tuple[str | None, str | None]]


class SchemaError(ValueError):
    """The spreadsheet does not have the published structure."""


@dataclass
class Row:
    set: str
    n1: str
    n2: str
    event: str
    code: int
    event_source: str | None
    row: int


@dataclass
class Report:
    rows_read: dict[str, int] = field(default_factory=dict)
    rejected: list[dict] = field(default_factory=list)


def _clean(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def validate(records: list[dict], kind: str, report: Report) -> list[Row]:
    """Check columns and values; keep valid rows, list the rest with a reason."""
    cols = POS_COLUMNS if kind == "positive" else NEG_COLUMNS
    if records:
        missing = [c for c in cols if c not in records[0]]
        if missing:
            raise SchemaError(f"{kind}: missing columns {missing}")
    out: list[Row] = []
    for i, r in enumerate(records):
        n1, n2, ev = _clean(r.get("DRUG_1_CONCEPT_NAME")), _clean(r.get("DRUG_2_CONCEPT_NAME")), _clean(r.get("EVENT_CONCEPT_NAME"))
        code_raw = r.get("MDR_CODE")
        src = _clean(r.get("EVENT_SOURCE")) if kind == "positive" else None
        reason = None
        if not (n1 and n2 and ev):
            reason = "missing drug or event name"
        else:
            try:
                code = int(code_raw)
                if not 10_000_000 <= code <= 99_999_999:
                    reason = f"MedDRA code out of range: {code_raw!r}"
            except (TypeError, ValueError):
                reason = f"MedDRA code not an integer: {code_raw!r}"
        if not reason and kind == "positive" and src not in EVENT_SOURCES:
            reason = f"unknown EVENT_SOURCE: {src!r}"
        if reason:
            report.rejected.append({"set": kind, "row": i + 2, "reason": reason})   # +2: header, 1-based
            continue
        out.append(Row(kind, n1, n2, ev, int(code_raw), src, i + 2))
    report.rows_read[kind] = len(records)
    return out


def build_index(positive: list[dict], negative: list[dict], lookup: Lookup) -> dict:
    """Validated, mapped, de-duplicated, conflict-free index (deterministic)."""
    report = Report()
    rows = validate(positive, "positive", report) + validate(negative, "negative", report)

    names = sorted({r.n1 for r in rows} | {r.n2 for r in rows}, key=str.lower)
    mapping: dict[str, tuple[str | None, str | None]] = {n: lookup(n) for n in names}
    unmapped = sorted(n for n, (d, _) in mapping.items() if d is None)

    stages = Counter()
    merged: dict[tuple, dict] = {}
    for r in rows:
        a, b = mapping[r.n1][0], mapping[r.n2][0]
        if a is None or b is None:
            stages[f"{r.set}_unmapped_drug"] += 1
            continue
        if a == b:
            stages[f"{r.set}_self_pair_after_mapping"] += 1
            continue
        da, db = sorted((a, b))
        key = (r.set, da, db, r.code)
        rec = merged.get(key)
        if rec is None:
            merged[key] = {"set": r.set, "drug_a": da, "drug_b": db, "event": r.event, "meddra_code": r.code,
                           "event_sources": [r.event_source] if r.event_source else [],
                           "names": sorted({r.n1, r.n2}, key=str.lower), "rows": [r.row]}
        else:
            stages[f"{r.set}_duplicate_collapsed"] += 1
            rec["rows"].append(r.row)
            for n in (r.n1, r.n2):
                if n not in rec["names"]:
                    rec["names"].append(n)
            if r.event_source and r.event_source not in rec["event_sources"]:
                rec["event_sources"].append(r.event_source)

    # The same pair and event as both a positive and a negative control is a
    # contradiction in the reference itself: keep neither.
    pos_keys = {k[1:] for k in merged if k[0] == "positive"}
    neg_keys = {k[1:] for k in merged if k[0] == "negative"}
    conflicts = sorted(pos_keys & neg_keys)
    for k in conflicts:
        merged.pop(("positive", *k))
        merged.pop(("negative", *k))

    records = sorted(merged.values(), key=lambda x: (x["set"], x["drug_a"], x["drug_b"], x["meddra_code"]))
    for x in records:
        x["rows"].sort()
        x["event_sources"].sort()
    how = Counter(h for d, h in mapping.values() if d)
    counts = Counter(x["set"] for x in records)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "records": records,
        "stats": {
            "rows_read": report.rows_read,
            "rows_rejected_by_schema": len(report.rejected),
            "drug_names": len(names),
            "drug_names_mapped": len(names) - len(unmapped),
            "mapping_method_counts": dict(sorted(how.items())),
            "unmapped_drug_names": unmapped,
            "dropped": dict(sorted(stages.items())),
            "positive_negative_conflicts_removed": len(conflicts),
            "records": dict(sorted(counts.items())),
            "distinct_pairs_positive": len({(x["drug_a"], x["drug_b"]) for x in records if x["set"] == "positive"}),
            "distinct_events_positive": len({x["meddra_code"] for x in records if x["set"] == "positive"}),
        },
        "rejected_rows": report.rejected,
    }


def read_xlsx(path: Path) -> list[dict]:
    import pandas as pd  # ingestion-only dependency (not in the lean image)
    df = pd.read_excel(path, dtype=object)
    return df.to_dict(orient="records")


def dumps_gz(payload: dict) -> bytes:
    """Deterministic gzip JSON (sorted keys, fixed mtime)."""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as f:
        f.write(raw)
    return buf.getvalue()


def write(payload: dict, out_dir: Path, inputs: dict[str, str], generated: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    blob = dumps_gz(payload)
    target = out_dir / "crescenddi_index_v1.json.gz"
    target.write_bytes(blob)
    manifest = {
        "manifest_version": 1,
        "dataset": "crescenddi",
        "schema_version": SCHEMA_VERSION,
        "generated": generated,
        "generator": "scripts/data/ingest_crescenddi.py",
        "source": SOURCE,
        "inputs": {rel: {"sha256": h} for rel, h in sorted(inputs.items())},
        "output": {"file": target.name, "sha256": sha256_file(target), "bytes": len(blob)},
        "stats": payload["stats"],
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return manifest


def load_index(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SchemaError(f"unexpected schema {payload.get('schema_version')!r}")
    return payload


def positives_by_pair(payload: dict) -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for x in payload["records"]:
        if x["set"] == "positive":
            out[(x["drug_a"], x["drug_b"])].append(x)
    return out

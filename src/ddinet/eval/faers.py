"""
Independent validation against openFDA FAERS adverse-event reports.

WHY THIS STEP EXISTS
--------------------
Everything up to here is internal validation: the model is scored against the
same kind of curated database it was trained on. That answers "does it
generalise to held-out drugs?" but not "does it correspond to anything that
happens to real patients?".

FAERS - the FDA Adverse Event Reporting System - is a genuinely independent
source. It is not a curated interaction database; it is millions of
spontaneous reports of things that went wrong. If pairs the model flags as
dangerous show a disproportionate co-reporting signal in FAERS, that is
evidence from a different kind of data entirely.

It also gives you a way to test the model's *apparent* false positives. Under
the positive-unlabelled framing (Step 1), a high-confidence "false positive"
may be a real but undocumented interaction. If those pairs carry a FAERS signal
at a higher rate than random undocumented pairs, that is the single most
compelling result this project can produce - the model finding something the
database has not yet recorded.

DISPROPORTIONALITY ANALYSIS
---------------------------
The standard pharmacovigilance tool. Build a 2x2 contingency table:

                        event present    event absent
    both drugs                a               b
    not both drugs            c               d

    PRR = [a/(a+b)] / [c/(c+d)]     proportional reporting ratio
    ROR = (a*d) / (b*c)             reporting odds ratio

The conventional signal threshold (EMA / Evans et al. 2001) is
``a >= 3 AND PRR >= 2 AND chi-square >= 4``. We report all three components so
a reader can apply a different threshold.

*** THE CAVEATS - DO NOT SKIP THESE IN YOUR WRITE-UP ***
--------------------------------------------------------
FAERS is a spontaneous reporting system. Every one of these is a real limit and
a judge who knows pharmacovigilance will test you on them:

1. **No denominator.** You cannot compute incidence or risk. Nobody knows how
   many patients took the combination without incident. Disproportionality is
   about *reporting*, not about *occurrence*.

2. **Reports are unverified and unadjudicated.** A report is someone's
   suspicion, not a confirmed causal finding.

3. **Notoriety bias.** Once an interaction is publicised, reporting of it
   spikes. So a strong FAERS signal for a well-known interaction partly
   reflects that it is well known - which makes FAERS agreement on *famous*
   pairs weak evidence and agreement on *obscure* pairs much stronger.

4. **Confounding by indication / co-prescription.** Two drugs prescribed
   together for the same severe condition will co-occur in reports of that
   condition's complications, with no interaction involved at all.

5. **Duplicates.** The same case can be submitted by a patient, a physician and
   a manufacturer. openFDA does not fully de-duplicate.

6. **Name matching is crude.** ``medicinalproduct`` is free text with brand
   names, misspellings and combination products. We query lower-cased generic
   names and accept that recall is imperfect - and we report the counts so the
   reader can see how thin the data is.

The honest framing is: **FAERS agreement is corroborating evidence, not proof.
Disproportionality is hypothesis-generating.** Say exactly that, and you will
be ahead of a good many published papers.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..data.download import RAW_DIR, USER_AGENT

OPENFDA_EVENT_URL = "https://api.fda.gov/drug/event.json"
CACHE_DIR = RAW_DIR / "openfda_faers" / "cache"


@dataclass
class Disproportionality:
    """A 2x2 disproportionality result for one drug pair (+ optional event)."""

    drug_a: str
    drug_b: str
    event: str
    a: int          # both drugs + event
    b: int          # both drugs, no event
    c: int          # not both drugs, event
    d: int          # neither
    prr: float
    ror: float
    ror_ci_low: float
    ror_ci_high: float
    chi2: float
    is_signal: bool

    def to_dict(self) -> dict:
        return asdict(self)


def disproportionality(
    a: int, b: int, c: int, d: int,
    *, drug_a: str = "", drug_b: str = "", event: str = "",
    min_reports: int = 3, prr_threshold: float = 2.0, chi2_threshold: float = 4.0,
) -> Disproportionality:
    """Compute PRR, ROR with a 95% CI, and the chi-square statistic.

    Haldane-Anscombe correction (add 0.5 to every cell) is applied *only* to the
    ROR when a cell is zero, which is the standard fix for an undefined odds
    ratio. The raw counts are reported unmodified, because the reader needs to
    see how sparse the data actually is - a "signal" resting on a=3 is very
    different from one resting on a=300.
    """
    n = a + b + c + d
    if n == 0:
        return Disproportionality(drug_a, drug_b, event, a, b, c, d,
                                  float("nan"), float("nan"), float("nan"),
                                  float("nan"), float("nan"), False)

    exposed = a + b
    unexposed = c + d
    prr = (
        (a / exposed) / (c / unexposed)
        if exposed > 0 and unexposed > 0 and c > 0
        else float("inf") if exposed > 0 and a > 0 else float("nan")
    )

    aa, bb, cc, dd = (float(a), float(b), float(c), float(d))
    if min(aa, bb, cc, dd) == 0:
        aa, bb, cc, dd = aa + 0.5, bb + 0.5, cc + 0.5, dd + 0.5
    ror = (aa * dd) / (bb * cc)
    se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    ror_lo = math.exp(math.log(ror) - 1.96 * se)
    ror_hi = math.exp(math.log(ror) + 1.96 * se)

    # Chi-square with Yates continuity correction.
    row1, row2 = a + b, c + d
    col1, col2 = a + c, b + d
    if min(row1, row2, col1, col2) == 0:
        chi2 = 0.0
    else:
        expected_a = row1 * col1 / n
        chi2 = (
            n * max(abs(a * d - b * c) - n / 2, 0) ** 2
            / (row1 * row2 * col1 * col2)
        )
        if expected_a <= 0:
            chi2 = 0.0

    is_signal = (a >= min_reports) and (prr >= prr_threshold) and (chi2 >= chi2_threshold)
    return Disproportionality(drug_a, drug_b, event, a, b, c, d,
                              float(prr), float(ror), float(ror_lo), float(ror_hi),
                              float(chi2), bool(is_signal))


class FAERSClient:
    """Cached, rate-limited openFDA client.

    Every distinct query is cached to disk, so a re-run costs zero requests and
    the analysis is reproducible offline once the cache is warm.

    ``offline=True`` serves only from cache and returns ``None`` on a miss - so
    the whole harness can be developed and tested on a network that blocks
    api.fda.gov, which is common on school and managed networks.
    """

    def __init__(
        self, cache_dir: Path | None = None, *,
        api_key: str | None = None, offline: bool = False,
    ) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.api_key = api_key or os.environ.get("DDINET_OPENFDA_KEY")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        # Without a key openFDA allows 240 requests/min; stay well inside it.
        self._recent: deque[float] = deque()
        self.n_requests = 0
        self.n_cache_hits = 0
        self.n_misses = 0

    def _throttle(self) -> None:
        now = time.monotonic()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        limit = 200 if not self.api_key else 1000
        if len(self._recent) >= limit:
            time.sleep(60 - (now - self._recent[0]) + 0.1)
        self._recent.append(time.monotonic())

    def _cache_path(self, key: str) -> Path:
        import hashlib

        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{digest}.json"

    def count_reports(self, search: str) -> int | None:
        """Number of FAERS reports matching an openFDA search expression.

        Returns ``None`` when the query cannot be answered (offline cache miss
        or a network failure) and ``0`` when openFDA genuinely reports no
        matches. Conflating those two would silently turn "we don't know" into
        "there is no signal", which is exactly the error this project keeps
        refusing to make.
        """
        path = self._cache_path(search)
        if path.exists():
            self.n_cache_hits += 1
            try:
                return json.loads(path.read_text())["count"]
            except (json.JSONDecodeError, KeyError):
                path.unlink()

        if self.offline:
            self.n_misses += 1
            return None

        params = {"search": search, "limit": 1}
        if self.api_key:
            params["api_key"] = self.api_key

        self._throttle()
        self.n_requests += 1
        try:
            resp = self.session.get(OPENFDA_EVENT_URL, params=params, timeout=30)
        except requests.RequestException:
            return None

        if resp.status_code == 404:
            # openFDA returns 404 for "no matches" - a real zero, worth caching.
            path.write_text(json.dumps({"count": 0}))
            return 0
        if resp.status_code != 200:
            return None
        try:
            total = int(resp.json()["meta"]["results"]["total"])
        except (ValueError, KeyError, TypeError):
            return None
        path.write_text(json.dumps({"count": total}))
        return total

    # -- query builders ----------------------------------------------------
    @staticmethod
    def _drug_clause(name: str) -> str:
        return f'patient.drug.medicinalproduct:"{name.lower()}"'

    @staticmethod
    def _event_clause(event: str) -> str:
        return f'patient.reaction.reactionmeddrapt:"{event.lower()}"'

    def pair_event_counts(
        self, drug_a: str, drug_b: str, event: str
    ) -> tuple[int, int, int, int] | None:
        """The four cells of the 2x2 table. ``None`` if any query fails.

        Four queries per pair. Cells c and d are derived by subtraction from
        totals rather than queried directly, because openFDA has no efficient
        NOT operator and the arithmetic is exact.
        """
        both = f"({self._drug_clause(drug_a)}+AND+{self._drug_clause(drug_b)})"
        n_both_event = self.count_reports(f"{both}+AND+{self._event_clause(event)}")
        n_both = self.count_reports(both)
        n_event = self.count_reports(self._event_clause(event))
        n_total = self.count_reports("_exists_:patient.drug.medicinalproduct")

        if None in (n_both_event, n_both, n_event, n_total):
            return None

        a = n_both_event
        b = max(n_both - n_both_event, 0)
        c = max(n_event - n_both_event, 0)
        d = max(n_total - a - b - c, 0)
        return a, b, c, d

    def analyse_pair(
        self, drug_a: str, drug_b: str, event: str
    ) -> Disproportionality | None:
        cells = self.pair_event_counts(drug_a, drug_b, event)
        if cells is None:
            return None
        a, b, c, d = cells
        return disproportionality(a, b, c, d, drug_a=drug_a, drug_b=drug_b, event=event)

    def stats(self) -> str:
        return (
            f"openFDA: {self.n_requests} requests, {self.n_cache_hits} cache hits, "
            f"{self.n_misses} unanswerable (offline)"
        )


#: Map DDI-Net's internal clinical-effect vocabulary onto MedDRA preferred terms
#: as they appear in FAERS. Hand-made and deliberately conservative: a wrong
#: mapping produces a spurious signal, which is worse than no signal.
EFFECT_TO_MEDDRA: dict[str, tuple[str, ...]] = {
    "bleeding": ("haemorrhage", "gastrointestinal haemorrhage", "haematoma"),
    "rhabdomyolysis": ("rhabdomyolysis", "myopathy", "blood creatine phosphokinase increased"),
    "myopathy": ("myopathy", "muscular weakness", "myalgia"),
    "serotonin_syndrome": ("serotonin syndrome",),
    "qt_prolongation": ("electrocardiogram qt prolonged", "torsade de pointes",
                        "ventricular tachycardia"),
    "respiratory_depression": ("respiratory depression", "respiratory arrest", "apnoea"),
    "hyperkalaemia": ("hyperkalaemia",),
    "acute_kidney_injury": ("acute kidney injury", "renal failure"),
    "hypoglycaemia": ("hypoglycaemia",),
    "myelosuppression": ("bone marrow failure", "pancytopenia", "neutropenia"),
    "agranulocytosis": ("agranulocytosis", "neutropenia"),
    "digoxin_toxicity": ("digitalis toxicity", "bradycardia"),
    "excess_sedation": ("sedation", "somnolence"),
    "severe_hypotension": ("hypotension", "shock"),
    "hypotension": ("hypotension",),
    "bradycardia": ("bradycardia", "atrioventricular block"),
    "seizure": ("seizure", "convulsion"),
    "hepatotoxicity": ("hepatotoxicity", "drug-induced liver injury",
                       "hepatic function abnormal"),
    "lactic_acidosis": ("lactic acidosis",),
    "colchicine_toxicity": ("toxicity to various agents", "pancytopenia"),
    "theophylline_toxicity": ("toxicity to various agents", "seizure"),
    "phenytoin_toxicity": ("toxicity to various agents", "ataxia", "nystagmus"),
}


def validate_predictions(
    predictions: pd.DataFrame,
    client: FAERSClient,
    *,
    default_events: tuple[str, ...] = ("drug interaction",),
    max_pairs: int | None = None,
) -> pd.DataFrame:
    """Look up a FAERS signal for each predicted pair.

    ``predictions`` needs ``drug_a``, ``drug_b``, ``score``; an optional
    ``clinical_effect`` column selects a specific MedDRA term, otherwise the
    generic 'drug interaction' term is used.

    Rows where openFDA could not answer are returned with ``queried=False``
    rather than dropped. **Silently dropping unanswerable pairs would bias the
    result towards well-reported (and therefore well-known) drugs** - which is
    precisely the notoriety bias that makes FAERS tricky in the first place.
    """
    rows = []
    frame = predictions if max_pairs is None else predictions.head(max_pairs)

    for record in frame.itertuples():
        effect = getattr(record, "clinical_effect", "") or ""
        events = EFFECT_TO_MEDDRA.get(effect, default_events)
        best: Disproportionality | None = None
        for event in events:
            result = client.analyse_pair(record.drug_a, record.drug_b, event)
            if result is None:
                continue
            if best is None or (np.isfinite(result.prr) and result.prr > best.prr):
                best = result
        if best is None:
            rows.append({
                "drug_a": record.drug_a, "drug_b": record.drug_b,
                "score": getattr(record, "score", float("nan")),
                "clinical_effect": effect, "queried": False,
            })
        else:
            rows.append({**best.to_dict(), "score": getattr(record, "score", float("nan")),
                         "clinical_effect": effect, "queried": True})
    return pd.DataFrame(rows)


def signal_enrichment(
    flagged: pd.DataFrame, control: pd.DataFrame
) -> dict:
    """Compare FAERS signal rates between model-flagged and control pairs.

    This is the actual experiment: *do pairs the model flags carry a FAERS
    signal more often than pairs it does not?*

    A single pair agreeing with FAERS proves nothing - you can find a signal for
    almost any famous pair. **The rate difference between a flagged set and a
    matched control set is the evidence.** Report the control's rate too; a
    flagged rate of 40% is only meaningful next to a control rate of 10%.
    """
    def rate(frame: pd.DataFrame) -> tuple[int, int, float]:
        answered = frame[frame.get("queried", True) == True]  # noqa: E712
        if len(answered) == 0:
            return 0, 0, float("nan")
        n_sig = int(answered["is_signal"].sum()) if "is_signal" in answered else 0
        return n_sig, len(answered), n_sig / len(answered)

    f_sig, f_n, f_rate = rate(flagged)
    c_sig, c_n, c_rate = rate(control)
    return {
        "flagged_signals": f_sig, "flagged_n": f_n, "flagged_rate": f_rate,
        "control_signals": c_sig, "control_n": c_n, "control_rate": c_rate,
        "rate_ratio": (f_rate / c_rate) if c_rate and np.isfinite(c_rate) and c_rate > 0
                      else float("nan"),
        "interpretation": (
            "A rate ratio above 1 means model-flagged pairs carry a FAERS "
            "disproportionality signal more often than control pairs. This is "
            "corroborating evidence, NOT proof of causation - FAERS has no "
            "denominator and is subject to notoriety and indication bias."
        ),
    }

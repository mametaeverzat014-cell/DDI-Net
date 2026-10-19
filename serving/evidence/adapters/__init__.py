"""Adapters for external, authoritative sources.

Each adapter answers one narrow question and reports, in so many words, when it
could not: ``SourceUnavailable`` is raised for network failure, timeout, HTTP
5xx or a blocked egress, and the API turns it into a ``sources_checked`` entry
with status "unavailable" — never into an empty result that would read as
"nothing found".

Sources evaluated for DDI-Net 3.0 (see docs/DDINET_V3_ARCHITECTURE.md §4):

* RxNorm (NLM RxNav REST) — name normalisation: brand and spelling variants to
  ingredient concepts. Public domain, updated monthly, no key. Its separate
  Drug Interaction API was discontinued by NLM on 2024-01-02 and is not used.
* openFDA drug label endpoint — structured sections of FDA Structured Product
  Labeling (SPL): boxed warning, contraindications, warnings and precautions,
  drug interactions. Public, CC0, updated weekly; 240 requests/minute without
  a key. Section text is the label's own; openFDA does not grade interactions.
* DailyMed — the human-readable home of the same SPL documents. Used only to
  build a link from the label's set ID; no request is made to it.
"""

from .http import HttpClient, SourceUnavailable  # noqa: F401

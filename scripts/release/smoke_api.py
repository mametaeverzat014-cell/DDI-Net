#!/usr/bin/env python3
"""Production smoke test of a DDI-Net 3.0 API (standard library only).

    python3 scripts/release/smoke_api.py https://ddinet-api.onrender.com

Run it from any machine that can reach the API (it was written in a build
container that cannot). Each check prints PASS/FAIL with the evidence; the exit
code is the number of failures. Nothing is written to the service except normal
read-only requests (about 15, well under the rate limits).

What a PASS means: the deployed API answers with the DDI-Net 3.0 schema, serves
no CRESCENDDI record, states "no specific clinical outcome" where none is
documented, refuses bad input cleanly, and allows the browser origin. It says
nothing about clinical correctness.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

ORIGIN = "https://ddi-net.vercel.app"
NO_SPECIFIC = "No specific clinical outcome established from available evidence."
results: list[tuple[bool, str, str]] = []


def call(base: str, method: str, path: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Origin": ORIGIN, **({"Content-Type": "application/json"} if data else {}), **(headers or {})}
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw, status, hdrs = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, hdrs = e.read(), e.code, dict(e.headers)
    dt = time.time() - t0
    try:
        js = json.loads(raw) if raw else None
    except ValueError:
        js = None
    return status, js, raw.decode("utf-8", "replace"), {k.lower(): v for k, v in hdrs.items()}, dt


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((bool(ok), name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


def no_restricted(raw: str) -> bool:
    low = raw.lower()
    return "crescenddi" not in low and "reference_set_outcome" not in low


def outcome_summary(rep: dict) -> tuple[bool, str]:
    """A documented clinical outcome WITH a quoted source, or the exact no-specific sentence."""
    o = rep.get("outcomes") or {}
    shown = [x for x in o.get("outcomes", []) if not x.get("research_only")]
    clinical = [x for x in shown if x.get("effect_level") == "clinical_outcome"]
    cited = all(s.get("excerpt", "").strip() and s.get("source_name") for x in clinical for s in x.get("supports", []))
    ns = (o.get("no_specific_outcome_text") or {}).get("en", "")
    if clinical:
        rules = sorted({s.get("extraction_method", "").split(":")[0] for x in clinical for s in x.get("supports", [])})
        return cited and not ns, f"{len(clinical)} documented clinical outcome(s), cited={cited}, rules={rules}"
    return ns.startswith(NO_SPECIFIC), f"no clinical outcome; no-specific sentence present={ns.startswith(NO_SPECIFIC)}"


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "https://ddinet-api.onrender.com").rstrip("/")
    print(f"API: {base}\n")

    s, js, raw, h, dt = call(base, "GET", "/api/health/ready")
    check(s == 200 and js and js.get("ready") and js.get("model_available") and js.get("evidence_available"),
          "health/ready: model and evidence loaded", f"HTTP {s}, {raw[:120]}, {dt:.1f}s")
    s, js, raw, h, dt = call(base, "GET", "/api/health")
    check(s == 200, "health: service metadata", raw[:300])

    s, js, raw, h, dt = call(base, "GET", "/api/v3/resolve?q=warfarin")
    check(s == 200 and js and js.get("status") == "resolved" and (js.get("drug") or {}).get("id") == "DB00682",
          "resolve 'warfarin' -> DB00682", f"HTTP {s}, status={js and js.get('status')}")
    s, js, raw, h, dt = call(base, "GET", "/api/v3/resolve?q=acetaminophen")
    check(s == 200 and js and (js.get("drug") or {}).get("id") == "DB00316",
          "resolve 'acetaminophen' -> DB00316 (paracetamol, US name)", f"HTTP {s}, {raw[:160]}")

    for a, b, label in [("warfarin", "fluconazole", "W+F"), ("warfarin", "aspirin", "W+aspirin"),
                        ("simvastatin", "clarithromycin", "simvastatin+clarithromycin")]:
        s, js, raw, h, dt = call(base, "POST", "/api/v3/report", {"drug_a": a, "drug_b": b})
        ok = s == 200 and isinstance(js, dict) and "outcomes" in js
        check(ok, f"report {label}: v3 schema with outcome block", f"HTTP {s}, {dt:.1f}s")
        if not ok:
            continue
        o = js["outcomes"]
        check(no_restricted(raw), f"report {label}: no CRESCENDDI / reference-set record",
              f"sources_checked={[c.get('source') for c in js.get('sources_checked', [])]}")
        good, why = outcome_summary(js)
        check(good, f"report {label}: cited outcome or exact no-specific sentence", f"{o.get('interaction_status')}; {why}")
        m = js.get("model") or {}
        check(m.get("available") is True and m.get("calibrated_model_score") is not None,
              f"report {label}: BIO-GINE score present (research signal)",
              f"calibrated={m.get('calibrated_model_score')}, regime={m.get('regime')}")
        labels = next((c for c in js.get("sources_checked", []) if c.get("source") == "openfda_label"), {})
        print(f"      info: FDA labels status = {labels.get('status')} ({(labels.get('detail') or '')[:90]})")
        if label == "W+F":
            safe_claim = any(w in raw.lower() for w in ("is safe to", "safe combination", "no interaction risk"))
            check(not safe_claim, "report W+F: no positive safety claim")
            chains = o.get("chains", [])
            unconf = all(lk.get("provenance") != "documented" for c in chains for lk in c.get("links", [])
                         if lk.get("relation") == "may_lead_to") if chains else True
            check(unconf, "report W+F: exposure→outcome route never 'documented' without one sentence stating both",
                  f"{len(chains)} chain(s)")

    s, js, raw, h, dt = call(base, "POST", "/api/v3/graph", {"drug_a": "warfarin", "drug_b": "fluconazole"})
    check(s == 200 and isinstance(js, dict), "graph W+F: mechanism graph", f"HTTP {s}, {dt:.1f}s")

    drugs = ["warfarin", "fluconazole", "simvastatin", "clarithromycin", "acetylsalicylic acid", "metformin"]
    s, js, raw, h, dt = call(base, "POST", "/api/v3/multi", {"drugs": drugs})
    pairs = (js or {}).get("pairs", []) if isinstance(js, dict) else []
    check(s == 200 and len(pairs) == 15, "multi (6 drugs): 15 pairs", f"HTTP {s}, pairs={len(pairs)}, {dt:.1f}s")
    check(s == 200 and no_restricted(raw) and all(not p.get("n_reference_records") for p in pairs),
          "multi: no reference-set records")

    s, js, raw, h, dt = call(base, "POST", "/api/analyze", {"drug_a": "DB00682", "drug_b": "DB00196"})
    check(s == 200, "v2 /api/analyze still answers (BIO-GINE)", f"HTTP {s}, {raw[:160]}")

    s, js, raw, h, dt = call(base, "POST", "/api/v3/report", {"drug_a": "notadrugxyz", "drug_b": "warfarin"})
    check(s == 422, "unknown drug -> 422, nothing guessed", f"HTTP {s}")
    s, js, raw, h, dt = call(base, "POST", "/api/v3/report", {"drug_a": "<script>", "drug_b": "warfarin"})
    check(s == 422, "invalid characters -> 422", f"HTTP {s}")

    s, js, raw, h, dt = call(base, "OPTIONS", "/api/v3/report",
                             headers={"Access-Control-Request-Method": "POST",
                                      "Access-Control-Request-Headers": "content-type"})
    acao = h.get("access-control-allow-origin")
    check(s in (200, 204) and acao in ("*", ORIGIN), f"CORS preflight from {ORIGIN}", f"HTTP {s}, allow-origin={acao}")
    s, js, raw, h, dt = call(base, "GET", "/api/v3/limits")
    check("x-ratelimit-limit" in h, "rate limiting active (X-RateLimit-Limit header)",
          f"limit={h.get('x-ratelimit-limit')}, remaining={h.get('x-ratelimit-remaining')}")

    fails = [n for ok, n, _ in results if not ok]
    print(f"\n{len(results) - len(fails)}/{len(results)} checks passed.")
    for n in fails:
        print(f"  FAILED: {n}")
    return len(fails)


if __name__ == "__main__":
    sys.exit(main())

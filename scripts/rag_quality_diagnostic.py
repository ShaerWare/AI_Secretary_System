#!/usr/bin/env python3
"""
RAG quality diagnostic: run a fixed corpus of thematic queries against each
Irish-accountancy collection and print per-collection top-1 similarity stats.

Used to measure retrieval quality for the DigiTax chat session and track
the impact of tuning work (threshold, per-collection top-k, reranking).

Output buckets: strong (top-1 ≥ 0.70), neutral (0.55..0.70), weak (< 0.55).
The baseline snapshot lives in `docs/rag-quality-baseline-2026-04-19.md`.

Usage:
    python3 scripts/rag_quality_diagnostic.py
"""

import json
import os
import urllib.error
import urllib.request


AUTH_TOKEN = os.environ.get(
    "VECTOR_SEARCH_TOKEN",
    "hcVAINgKGa1kwjx8e4ATYPkRjZ9bH_aRyEjAyly-Hs4",
)
BASE = os.environ.get("VECTOR_SEARCH_URL", "http://127.0.0.1:8003")

COLLECTIONS = [
    (8, "irish-tax"),
    (13, "chartered-accountants-ie"),
    (14, "cpa-ireland"),
    (12, "boards-ie-accountancy"),
    (15, "accounting-technicians-ie"),
    (16, "accountant-forums-ireland"),
    (17, "icaew-ireland"),
]

QUERIES = [
    "How do I register as self-employed in Ireland?",
    "PRSI contribution rates 2025",
    "USC rates and thresholds Ireland",
    "How to fill Form 11 self-assessment",
    "VAT registration threshold Ireland",
    "Capital Acquisitions Tax CAT rates Ireland",
    "Preliminary tax payment deadline",
    "ROS Revenue Online Service file return",
    "Corporation tax 12.5% Ireland qualifying trade",
    "Rent Tax Credit amount",
    "CAI chartered accountant qualification requirements",
    "CPA Ireland exam syllabus",
    "FRS 102 small company criteria",
    "audit exemption thresholds Ireland",
    "Sole trader vs limited company tax Ireland",
]


def search(text: str, group: str, limit: int = 3, min_sim: float = 0.3) -> tuple[list, str]:
    """POST /search. Returns (items, error_label)."""
    try:
        req = urllib.request.Request(
            f"{BASE}/search",
            data=json.dumps(
                {"text": text, "group": group, "limit": limit, "min_similarity": min_sim}
            ).encode(),
            headers={"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("items", []), ""
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except Exception as e:
        return [], f"ERR {type(e).__name__}"


def main() -> None:
    hdr = f"{'Query':55s}{'Collection':30s}{'Top1':>6} {'Top3avg':>8}  {'Snippet':60}"
    print(hdr)
    print("-" * len(hdr))
    agg: dict[str, list[float]] = {slug: [] for _, slug in COLLECTIONS}
    errors: dict[str, int] = {slug: 0 for _, slug in COLLECTIONS}

    for q in QUERIES:
        q_short = q[:53]
        for _cid, slug in COLLECTIONS:
            hits, err = search(q, slug, limit=3)
            if err:
                print(f"{q_short:55s}{slug:30s}{err:>15}")
                errors[slug] += 1
                continue
            if not hits:
                print(f"{q_short:55s}{slug:30s}{'—':>6} {'—':>8}  (no hits)")
                agg[slug].append(0.0)
                continue
            top1 = hits[0].get("similarity", 0.0)
            top3 = sum(h.get("similarity", 0.0) for h in hits[:3]) / min(3, len(hits))
            snippet = hits[0].get("text", "").replace("\n", " ")[:58]
            marker = "★" if top1 >= 0.70 else ("·" if top1 >= 0.55 else " ")
            print(f"{q_short:55s}{slug:30s}{top1:>6.3f}{marker}{top3:>8.3f}  {snippet}")
            agg[slug].append(top1)
        print("")

    print("\n=== Per-collection summary (avg top-1, buckets) ===")
    for slug, scores in agg.items():
        if errors[slug] == len(QUERIES):
            print(f"  {slug:30s} ALL ERRORS ({errors[slug]}/{len(QUERIES)})")
            continue
        valid = [s for s in scores if s > 0]
        avg = (sum(valid) / len(valid)) if valid else 0.0
        strong = sum(1 for s in scores if s >= 0.70)
        weak = sum(1 for s in scores if 0 < s < 0.55)
        miss = sum(1 for s in scores if s == 0)
        err_tag = f"  errors={errors[slug]}" if errors[slug] else ""
        print(
            f"  {slug:30s} avg={avg:.3f}  strong(≥0.70)={strong:2d}  "
            f"weak(<0.55)={weak:2d}  miss={miss:2d}{err_tag}"
        )


if __name__ == "__main__":
    main()

# RAG Quality Baseline — 2026-04-19

Diagnostic snapshot of retrieval quality across the 7 Irish-accountancy
knowledge collections used by the DigiTax chat session, taken immediately
after PR #710 (unique `doc_id` per section) and PR #711 (snowballstemmer
`IndexError` workaround) landed and a full Vector Search resync finished
(148,170 records total — up from 8,344 before the fix; ~×17.7).

This is the **before** state for the quality-tuning work. All later
experiments are measured against these numbers with the same
[`scripts/rag_quality_diagnostic.py`](../scripts/rag_quality_diagnostic.py)
driver and the same 15-query corpus.

## Method

- Target: Vector Search microservice at `http://127.0.0.1:8003/search`
- Embedding model: `paraphrase-multilingual-mpnet-base-v2` (shared by all groups)
- 15 English queries covering core Irish tax/accountancy topics (self-employed registration, PRSI, USC, Form 11, VAT, CAT, preliminary tax, ROS, corporation tax, rent credit, professional-body qualifications, FRS 102, audit exemption, sole-trader vs Ltd)
- Per collection: top-3 hits with `min_similarity=0.3`
- Metric: top-1 cosine similarity per (query, collection) pair; aggregated as mean and bucketed into strong (≥0.70), weak (0.55 ≤ s < 0.70 is neutral, s < 0.55 is weak), miss (no hits)

## Summary

| Collection (group) | avg top-1 | strong (≥0.70) | weak (<0.55) | notes |
| --- | --- | --- | --- | --- |
| `irish-tax` (id 8) | **0.707** | 9 / 15 | 0 | ★ gold standard — direct Revenue.ie content |
| `chartered-accountants-ie` (id 13) | 0.655 | 5 / 15 | 2 | solid professional-body content |
| `boards-ie-accountancy` (id 12) | 0.666 | 3 / 15 | 1 | forum, but live practical Q&A |
| `accountant-forums-ireland` (id 16) | 0.570 | 3 / 15 | 6 | noisy, residual "Unknown" post dedup issues |
| `cpa-ireland` (id 14) | 0.567 | 3 / 15 | 7 | content-thin site, lots of nav boilerplate |
| `icaew-ireland` (id 17) | 0.556 | 1 / 15 | 5 | broad UK body, Irish content diluted |
| `accounting-technicians-ie` (id 15) | — | — | — | 🔴 **100% HTTP 500** — Chroma HNSW `RuntimeError: ef/M too small` (105 records) |

## Findings, in order of ROI

### 1. `accounting-technicians-ie` returns HTTP 500 on every query

Chroma raises `RuntimeError: Cannot return the results in a contiguous 2D
array. Probably ef or M is too small` from
`local_persistent_hnsw.query_vectors`. Collection has ~105 records, which
falls below the default HNSW `ef_search` in the vector-search microservice.
Either raise `ef_search` per-collection, fall back to brute-force search
for small groups, or catch the error and retry with a smaller
`construction_ef`. Until fixed, this collection is effectively dark for
retrieval.

### 2. No similarity threshold in `retrieve_multi_async`

`modules/chat/facade.py` calls `retrieve_multi_async(..., top_k=7)` without
a `min_similarity` floor. The diagnostic shows several queries where the
top-1 hit in a weak collection is 0.40–0.50 — that content gets injected
into the LLM prompt next to a 0.78-scoring hit from `irish-tax`, diluting
the context. A `min_similarity ≈ 0.55` floor would drop the weak tail from
`cpa-ireland`, `icaew-ireland`, and `accountant-forums-ireland` without
affecting the strong collections.

### 3. No per-collection weighting / slot allocation

Multi-collection retrieval is a flat global top-k: a 0.79 `boards-ie` forum
hit can beat a 0.72 `irish-tax` hit for a tax-law question, because we
don't weight by collection authority. Two options:

- **Per-collection top-k** — reserve N slots per group and merge
  (e.g. `irish-tax`: 3, `chartered-accountants-ie`: 2, others: 1). Cheap
  to implement, predictable.
- **Reranking** — pull top-20 from everything, rerank with a cross-encoder
  or even an LLM. Better quality but +200–400ms latency and needs a
  reranker model.

### 4. Cross-collection leakage on proper nouns

"CPA Ireland exam syllabus" returns 0.75 on `chartered-accountants-ie`
(the CAI site mentions CPA) and 0.79 on `boards-ie-accountancy` (a forum
thread about CPA). The genuine authority (`cpa-ireland` at 0.86) is the
correct top hit but the runner-ups pollute the prompt. Fixing (2) and (3)
should largely absorb this; a title-level dedupe would finish it off.

### 5. Residual duplicates in `accountant-forums-ireland`

"I'm selling my PPR in Ireland…" shows up twice byte-identical at
different `doc_id`s. The scraper parse step should dedupe post bodies
before emitting sections; worth a pass after the bigger retrieval fixes
land.

## Reproducing

Run from the server:

```bash
python3 scripts/rag_quality_diagnostic.py
```

The script hits Vector Search directly (no chat-facade layer), so it
reflects raw retrieval quality independent of prompt engineering. Token
and collection list are in the script header.

## Next steps (not yet implemented)

- Fix HNSW behaviour for small collections (`accounting-technicians-ie`)
- Add `min_similarity` threshold in chat facade retrieval
- Per-collection slot allocation + dedupe by title
- Re-run this diagnostic; compare summary table
- Consider reranking layer if gaps remain

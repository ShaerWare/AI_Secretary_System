# RAG Quality — after tuning sweep, 2026-04-21

Follow-up to [`rag-quality-baseline-2026-04-19.md`](./rag-quality-baseline-2026-04-19.md). Measures the combined effect of the four PRs landed between 2026-04-19 and 2026-04-21:

| PR | What changed |
| --- | --- |
| [#713](https://github.com/ShaerWare/AI_Secretary_System/pull/713) (patch doc) | Vector Search HNSW "ef/M too small" fix for small collections (clamp `n_results` to filtered-pool size). Unblocked `accounting-technicians-ie` (100% HTTP 500 → HTTP 200). |
| [#714](https://github.com/ShaerWare/AI_Secretary_System/pull/714) | Default `min_similarity` floor 0.3 → 0.55 in `retrieve_*_async` paths. Cuts the weak tail from `cpa-ireland`, `icaew-ireland`, `accountant-forums-ireland`. |
| [#715](https://github.com/ShaerWare/AI_Secretary_System/pull/715) | Per-collection diversity slot allocation + body-hash dedup in `_merge_results`. Multi-collection output stays multi-source instead of being dominated by one collection. |
| [#727](https://github.com/ShaerWare/AI_Secretary_System/pull/727) | **Critical:** three pre-existing bugs had been silently disabling Vector Search inside `retrieve_multi_async` (chat path). Slug vs numeric-id mismatch on the `group` filter, wrong response key in the client, nested `metadata` wrapper that the microservice never emits. Also added BM25↔VS score normalization so the merge can actually mix engines instead of BM25 always winning on raw score. |

The raw Vector Search diagnostic (`scripts/rag_quality_diagnostic.py`) hits `/search` directly and so is unaffected by #714/#715/#727 — those all live in the consumer layer. Raw VS numbers match the 2026-04-19 baseline (same underlying content). The real change is visible on the consumer side, measured with a separate `retrieve_multi_async` probe.

## Raw Vector Search (unchanged from baseline)

| Collection | avg top-1 | strong (≥0.70) | weak (<0.55) | status |
| --- | --- | --- | --- | --- |
| `irish-tax` | 0.707 | 9 / 15 | 0 | gold standard |
| `chartered-accountants-ie` | 0.655 | 5 / 15 | 2 | solid |
| `boards-ie-accountancy` | 0.666 | 3 / 15 | 1 | forum, practical Q&A |
| `accountant-forums-ireland` | 0.570 | 3 / 15 | 6 | noisy, residual dupes |
| `cpa-ireland` | 0.567 | 3 / 15 | 7 | content-thin |
| `icaew-ireland` | 0.556 | 1 / 15 | 5 | UK body, Ireland diluted |
| `accounting-technicians-ie` | 0.435 | 0 / 15 | 12 | **HNSW unblocked**, but thin (105 records) |

## Consumer layer (the actual chat path) — 15-query probe

Ran `retrieve_multi_async(query, collection_ids=[8,12,13,14,15,16,17], top_k=7)` for the 15 baseline queries, captured the merged top-7 returned to the LLM.

| | Before #727 | After #727 |
| --- | --- | --- |
| Vector Search hits per query (pre-merge) | **0 / query** across all 15 | 6–38 / query |
| Merged top-7 engine mix | 7 / 7 BM25 (VS silently dead) | ~2–3 BM25 + ~4–5 VS |
| Collections represented in top-7 | 1–4 | 1–4 (unchanged — diversity round still kicks in) |

The "before" numbers are the surprise. Vector Search was effectively offline in the chat pipeline for weeks: the retrieve path queried VS with `group=str(collection_id)` ("8"), but the sync pipeline stored records under the slug ("irish-tax"). The result was a silent fall-back to BM25-only. #714 and #715 were running, but on BM25 output only — their real-world effect was much smaller than the diagnostic would suggest.

## What's left — ROI-ordered from the baseline

1. ~~`accounting-technicians-ie` HTTP 500~~ — #713 ✅
2. ~~No `min_similarity` floor in `retrieve_multi_async`~~ — #714 ✅
3. ~~Flat global top-k without per-collection weighting~~ — #715 (diversity round) ✅
3a. ~~Vector Search dark in retrieve pipeline (slug mismatch)~~ — #727 ✅ (was the invisible root cause behind why #714/#715 looked muted)
4. Cross-collection leakage on proper nouns — largely absorbed by #714/#715/#727; revisit only if observed in live chat.
5. ~~Residual duplicates in `accountant-forums-ireland`~~ — [#729](https://github.com/ShaerWare/AI_Secretary_System/pull/729) ✅. `parse.py` now hashes normalized content per site and skips byte-identical rewrites. On the 3 in-repo corpuses this dropped 34 (43%) files from `accountant-forums-ireland`, 26 (8%) from `cpa-ireland`, 0 from `icaew-ireland`. After deploy (re-parse → rsync `wiki-pages/` → restart → VS group delete + re-sync) the baseline case ("I'm selling my PPR…") is now a single hit. `raw_count → chunks` for the two affected VS groups: `accountant-forums-ireland` 884 → 517 (−42%), `cpa-ireland` 611 → 523 (−14%).
6. **Residual sidebar leakage in forums** (new, discovered during #729 verification). Forum pages include a "latest threads" sidebar, so every thread .md ends up containing the recent-thread block. VS still returns near-identical 130-char chunks for the sidebar snippet under many `doc_id`s (e.g. "UK Sale of a Subsidiary company"). Requires tightening `strip_boilerplate()` for the forum sites (`accountantforums.com`, boards.ie if observed). Lower priority than 1–5 — those chunks are short and below similarity threshold for most real queries.

## Reproducing

Raw Vector Search:

```bash
python3 scripts/rag_quality_diagnostic.py
```

Consumer-side probe (ad-hoc, see PR #727 commit message for the script):

```python
from app.services.wiki_rag_service import WikiRAGService
from app.services.vector_search_client import VectorSearchClient
# ... load collections with slug, call retrieve_multi_async ...
```

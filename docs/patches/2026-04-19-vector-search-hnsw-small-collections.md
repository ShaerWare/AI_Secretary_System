# Patch: vector-search HNSW "ef/M too small" on small groups

**Date:** 2026-04-19
**Applies to:** standalone Vector Search microservice at `/opt/vector-search/` (deployed separately from this repo, no upstream git origin)
**Symptom:** `POST /search` returned HTTP 500 with `RuntimeError: Cannot return the results in a contiguous 2D array. Probably ef or M is too small` for any group that had fewer records than the requested `n_results`. In practice this disabled `accounting-technicians-ie` (~105 records) completely — 100% of queries failed.
**Root cause:** `app/storage.py::search()` asked Chroma for `n_results = max(limit * page * 2, 100)` regardless of how many records actually passed the `where` filter. When the group had fewer candidates than `n_results`, hnswlib raised the "ef or M too small" error.
**Fix:** count the where-filtered pool first via `col.get(where=where)["ids"]` and clamp `n_results` to that size. Counting is cheap and keeps latency predictable versus a crash+retry loop.

## Applied diff (live in `/opt/vector-search/app/storage.py`)

```diff
     col = _get_collection()
     where = _build_where(doc_id=doc_id, group=group)

-    total_in_collection = col.count()
-    if total_in_collection == 0:
+    # Cap n_results to the actual filtered pool size. Chroma's HNSW raises
+    # "Cannot return the results in a contiguous 2D array. Probably ef or M
+    # is too small" when n_results exceeds the number of records passing the
+    # where-filter (e.g. asking for 100 in a 105-record group where only a
+    # fraction survives the candidate pool). Counting first is cheaper than
+    # the crash + retry loop and keeps latency predictable.
+    if where:
+        matching_total = len(col.get(where=where)["ids"])
+    else:
+        matching_total = col.count()
+    if matching_total == 0:
         return {"items": [], "total": 0, "page": page, "limit": limit}

     query_embedding = encode_single(text)

     # Fetch more than needed to account for similarity filtering
-    n_results = min(total_in_collection, max(limit * page * 2, 100))
+    n_results = min(matching_total, max(limit * page * 2, 100))
```

## Verification

`scripts/rag_quality_diagnostic.py` before/after:

| Collection | Before | After |
| --- | --- | --- |
| `accounting-technicians-ie` | 🔴 100% HTTP 500 (0 / 15 queries returned) | HTTP 200 on 15 / 15 (avg top-1 = 0.435 — low quality is a separate content issue, not the bug) |

All other collections unchanged — their filtered pools were already larger than `n_results`, so the clamp is a no-op for them.

## Provenance note

The `/opt/vector-search/` deployment does not have a git origin; there is an older monolithic copy at `services/vector-search/main.py` in this repo which has diverged from what's actually running. This patch is documented here (rather than as a code change) to keep a trail for future redeploys and for anyone reconciling the two codebases.

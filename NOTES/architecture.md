# How a request flows (simple version)

1. **server.py**: the official MCP Python SDK in stateless JSON mode. `tools/call search_products` runs
   `Catalog.search(arguments)` in a worker thread. A Host-header allow-list is set by `MCP_ALLOWED_HOSTS`.
2. **Validation** (`search.validate_arguments`): JSON Schema check plus blank-filter and min>max checks. Any
   violation raises, and the SDK returns an MCP tool error (`isError: true`).
3. **Empty query** (the speed-test path): precomputed numpy arrays. One boolean mask per filter is ANDed together,
   then a presorted index order is used for price, rating, review_count or id (ID tie-break, null ratings last).
   About 1 ms.
4. **Non-empty query**:
   - `query_parser` (rules only, no network) turns the text into an intent. It fixes typos against catalog
     vocabulary, reads budgets, ratings and review counts, colours, audience (including ages), and product-type
     words.
   - It splits mixed choices ("X and Y") and detects complements ("X with a matching Y", "recommend a Y",
     "What Y would match?").
   - It returns empty for non-catalog, impossible or non-shopping requests, and expands occasion words into
     garments only when there is a clothing cue.
5. **Retrieval per choice**:
   - Hard constraints are applied as numpy masks: explicit filters, plus type, colour, audience, budget and rating
     from the query. Filters win over conflicting query words.
   - Score = 0.75 × embedding similarity (bge-small, precomputed `data/emb.npy`, query embedded locally in about
     8 ms) + 0.25 × BM25 + an attribute-coverage bonus (material, pattern, occasion words found in the
     description or pattern), plus small audience and rating priors.
6. **Merge**: choices are interleaved round-robin. The relevant set is computed independently of offset and limit,
   so pages are stable. Field sorts use the top 100 relevant items.
7. **Recommendations** (`Catalog.recommend`), only when `include_recommendations` is true:
   - Uses the requested complement if one was named, otherwise a complement map by product type.
   - Anchored to the top primary result, kept to the same audience, and scored by occasion words, colour harmony
     and same-collection name.
   - Deduplicated by name, never one of the primary IDs, and empty if the requested item is not sold.
8. **Network or LLM at query time**: none. All work is in-process numpy plus one local ONNX embedding call.
   Results are cached per (query, filters).

Where time goes: about 8 ms query embedding, 5–10 ms matrix product, a few ms BM25 and masks, plus MCP/HTTP
overhead. The official p95 of 300 ms is mostly network and SDK overhead, measured from the organizers' runner.

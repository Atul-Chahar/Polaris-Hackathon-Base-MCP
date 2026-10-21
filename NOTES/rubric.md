# Scoring rubric (quoted from hackathon-brief.md) and where our points are

Latest official run (run 5, 21 Oct): **76.87 / 100**, functional 76.87 / 95, p95 308 ms, correct rate 100%.

| Category | Max | Ours | Missing | How it is graded |
|---|---|---|---|---|
| Validity | 25 | 25.00 | 0 | Python, exact |
| Ranking | 30 | 24.40 | **5.60** | Bedrock 0-3 grades, nDCG@10 |
| Unusual | 7.5 | 5.64 | 1.86 | Bedrock, nDCG@10 |
| Irrelevant | 7.5 | 5.25 | 2.25 (3 of 10 cases wrong) | Python: empty or not |
| Mixed | 15 | 13.04 | 1.96 | Bedrock: coverage + nDCG@10 |
| Recommendation | 10 | 3.54 | **6.46** | Bedrock: primary nDCG@10 + recommendation nDCG@5 |
| Performance | 5 | 0.00 | 5 (gated, see below) | latency, only if functional >= 85.5 |

Ranked by points available: Recommendation 6.46, Ranking 5.60, Performance 5 (needs about +8.6 functional
first), Irrelevant 2.25, Mixed 1.96, Unusual 1.86.

## Exact wording

**Weights:** "Validity and constraints | 25 | 25 × mean per-case validity score." "Ranking relevance | 30 | 30 × mean
nDCG@10 on single-intent relevance cases." "Unusual or irrelevant queries | 15 | 7.5 × mean nDCG@10 on meaningful
unusual cases, plus 7.5 × correct empty-response rate on irrelevant or impossible cases." "Mixed choices | 15 | 15 ×
mean of (0.5 × choice coverage + 0.5 × nDCG@10)." "Complementary recommendations | 10 | 10 × mean per-case
recommendation score." "Performance | 5 | 5 × correct response rate × max(0, min(1, (2000 − p95_ms) / 1800)),
subject to eligibility below."

**Suite:** "100 cases: 30 validity cases (including 10 invalid calls), 25 ranking cases, 10 meaningful unusual cases,
10 irrelevant or impossible cases, 15 mixed-choice cases, and 10 recommendation cases."

**Judging:** "Bedrock grades each primary product from 0 to 3: 3 directly relevant, 2 useful but less direct, 1 weak
connection, 0 irrelevant or unsupported." "DCG at k is the sum of (2^grade - 1) / log2(rank + 1) ... Normalize
against the fixed ideal of grade 3 in each declared reference slot ... Missing slots earn zero." "hard-constraint-
violating products earn no gain."

Important consequence: a grade 3 is worth 7 and a grade 2 is worth 3. A page of only grade-2 items scores 0.43, not
0.67. Moving items from "useful" to "directly relevant" is the biggest lever in every semantic category.

**Mixed:** "coverage is the fraction of requested choices receiving at least one grade-2-or-3 result that also has
primary relevance of at least 2 and obeys hard constraints."

**Recommendations:** "the case score is the mean of primary quality at 10 and recommendation quality at 5. A
recommendation must satisfy its own constraints and reference a primary product on the current page with a primary
grade of at least 2. Substitutes do not automatically qualify as complements. If a reviewed case declares no
available complement, an empty recommendation list receives full complement credit." "Explicit filters apply to
primary results only." "budgets are per item unless the query explicitly assigns a different budget to an
accompanying item". "Unqualified global requirements such as an audience apply to recommendations too."

**Irrelevant:** "For unrelated requests, impossible requirements, or insufficient evidence, return empty arrays
instead of random products."

**Performance:** "A team is eligible for performance points only if it earns at least 85.5 of the 95 functional
points and at least 95% correct performance calls. Otherwise performance points are zero. The fixed scale gives full
latency credit at 200 ms or below and zero at 2,000 ms or above." The pool is "empty-query filter and field-sort
calls", 50 at concurrency 1 and 50 at concurrency 5, three times, p95 over all 300 calls.

## Where the prompt I was given conflicts with the brief (the brief wins)

1. "Validity and Ranking are near full": Ranking is missing 5.6 points, the second-largest gap.
2. "Performance until the points are earned": performance is **not** a latency problem for us. Our p95 of 300 ms
   would already earn about 5 × (2000 − 300) / 1800 = 4.7 points. It is zero only because functional (76.87) is
   below the 85.5 gate. Speed work earns nothing until functional rises by about 8.6.
3. "Recommendations ... respect hard filters": the brief says "Explicit filters apply to primary results only."
   Only query constraints aimed at the accompanying item, and unqualified global ones like audience, apply.
4. "Limit colour variants in the top results": the brief says "Different IDs can represent similar products or
   variants: do not merge distinct catalog records". nDCG grades every ID on its own, so a relevant colour variant
   still earns full gain. A variant cap was measured with the strict judge and lowered ranking (a knitted-beanie
   query dropped from 1.00 to 0.73), so it is off.
5. "Remove any LLM call from the request path": already true. The server runs with no LLM keys; llm_client.py
   returns None immediately.

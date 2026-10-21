"""Perf workload per brief: .venv/bin/python eval/perf.py URL [--reps 3]
20 warmup calls, then per rep: 50 calls at concurrency 1, then 50 at concurrency 5. Exact-page checked."""
import argparse, asyncio, math, random, sys, time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import CATALOG, expected_page, structure_ok  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

def make_pool(n=50, seed=7):
    rnd = random.Random(seed)
    vals = {k: sorted({p[k] for p in CATALOG.values()}) for k in ('category', 'product_type', 'color', 'audience', 'section', 'pattern')}
    pool = []
    while len(pool) < n:
        f = {}
        for k in rnd.sample(list(vals), rnd.randint(0, 2)):
            v = rnd.choice(vals[k]); f[k] = rnd.choice([v, v.upper(), f' {v.lower()} '])
        if rnd.random() < .4: f['max_price'] = rnd.choice([999, 1499, 2999, 4999])
        if rnd.random() < .2: f['min_rating'] = rnd.choice([3, 4, 4.5])
        if rnd.random() < .15: f['min_review_count'] = rnd.choice([0, 5, 20])
        a = {'filters': f, 'sort_by': rnd.choice(['relevance', 'id', 'price', 'rating', 'review_count']),
             'sort_order': rnd.choice(['asc', 'desc']), 'limit': 10, 'offset': 0}
        pool.append((a, expected_page(a)))
    return pool

async def one(session, a, exp):
    t = time.perf_counter()
    try:
        r = await asyncio.wait_for(session.call_tool('search_products', a, read_timeout_seconds=timedelta(seconds=10)), 10)
        ms = (time.perf_counter() - t) * 1000
        ok = (not r.isError and structure_ok(r.structuredContent, a)
              and [x['id'] for x in r.structuredContent['results']] == exp)
        return ms if ok else 10000.0, ok
    except Exception:
        return 10000.0, False

async def workload(session, pool, conc):
    out, it = [], iter(pool)
    async def worker():
        for a, exp in it:
            out.append(await one(session, a, exp))
    await asyncio.gather(*[worker() for _ in range(conc)])
    return out

async def main(url, reps):
    pool = make_pool()
    async with streamable_http_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize(); await s.list_tools()
            for a, exp in (pool * 2)[:20]:
                await one(s, a, exp)
            res = []
            for rep in range(reps):
                for conc in (1, 5):
                    t = time.perf_counter(); out = await workload(s, pool, conc); el = time.perf_counter() - t
                    lat = sorted(m for m, _ in out)
                    print(f'rep {rep + 1} c={conc}: p50={lat[len(lat) // 2]:.0f}ms p95={lat[math.ceil(.95 * len(lat)) - 1]:.0f}ms '
                          f'ok={sum(o for _, o in out)}/{len(out)} rps={sum(o for _, o in out) / el:.1f}')
                    res += out
    lat = sorted(m for m, _ in res)
    p50, p95 = lat[math.ceil(.5 * len(lat)) - 1], lat[math.ceil(.95 * len(lat)) - 1]
    rate = sum(o for _, o in res) / len(res)
    pts = 5 * rate * max(0, min(1, (2000 - p95) / 1800))
    print(f'\nALL {len(res)} calls: p50={p50:.0f}ms p95={p95:.0f}ms correct={rate:.1%} error_rate={1 - rate:.1%}')
    print(f'performance points (if eligible: functional>=85.5 and correct>=95%): {pts:.2f} / 5'
          + ('' if rate >= .95 else '  [INELIGIBLE: correct<95%]'))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('url', nargs='?', default='http://127.0.0.1:8000/mcp')
    ap.add_argument('--reps', type=int, default=3); a = ap.parse_args()
    asyncio.run(main(a.url, a.reps))

"""Strict LLM-judge workflow with a per-item grade cache, so only new (query, product) pairs need grading.

  prep  DUMP.json GRADES.json OUTDIR [--chunk 120]   -> writes OUTDIR/batch_N.json with ungraded items
  merge GRADES.json OUTDIR                           -> folds OUTDIR/batch_N.out.json into GRADES.json
  score DUMP.json GRADES.json [--cases a.json,b.json] -> per-category strict scores (fixed ideal 3 in every slot)

DUMP.json comes from eval/dump_topk.py. Batch item kinds:
  primary: grade the product for the query (0-3); mixed cases also get one 0-3 grade per listed choice.
  rec:     grade the recommendation as a complement for its anchor product (0-3).
Output file per batch: {"<key>": grade, ...} where mixed primaries map to {"grade": g, "choices": [..]}.
"""
import argparse, glob, json, math, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACT_KEYS = ('name', 'description', 'product_type', 'category', 'audience', 'section', 'color', 'pattern',
             'price_inr', 'rating')


def strip(p):
    return {k: p[k] for k in FACT_KEYS}


def case_choices(cases):
    out = {}
    for c in cases:
        if c.get('choices'):
            out[c['id']] = [ch['text'] for ch in c['choices']]
    return out


def load_cases(spec):
    cases = []
    for f in (spec or f"{ROOT / 'eval/devset.json'},{ROOT / 'eval/heldout.json'}").split(','):
        if os.path.exists(f):
            cases += json.loads(Path(f).read_text())
    return cases


def pkey(query, pid):
    return f'P|{query}|{pid}'


def rkey(query, anchor, pid):
    return f'R|{query}|{anchor}|{pid}'


def prep(a):
    dump = json.loads(Path(a.dump).read_text())
    grades = json.loads(Path(a.grades).read_text()) if os.path.exists(a.grades) else {}
    choices = case_choices(load_cases(a.cases))
    items, seen = [], set()
    for c in dump:
        if c['category'] == 'irrelevant':
            continue
        ch = choices.get(c['id'])
        for p in c['results']:
            k = pkey(c['query'], p['id'])
            if k in grades or k in seen:
                continue
            seen.add(k)
            it = {'key': k, 'kind': 'primary', 'query': c['query'], 'product': strip(p)}
            if ch:
                it['choices'] = ch
            items.append(it)
        anchors = {p['id']: p for p in c['results']}
        for r in c['recommendations']:
            k = rkey(c['query'], r['for_product_id'], r['id'])
            if k in grades or k in seen:
                continue
            seen.add(k)
            items.append({'key': k, 'kind': 'rec', 'query': c['query'],
                          'anchor': strip(anchors[r['for_product_id']]), 'product': strip(r)})
    os.makedirs(a.outdir, exist_ok=True)
    for f in glob.glob(os.path.join(a.outdir, 'batch_*.json')):
        os.remove(f)
    n = 0
    for i in range(0, len(items), a.chunk):
        Path(a.outdir, f'batch_{n}.json').write_text(json.dumps(items[i:i + a.chunk], indent=1, ensure_ascii=False))
        n += 1
    print(f'{len(items)} ungraded items -> {n} batches in {a.outdir}')


def merge(a):
    grades = json.loads(Path(a.grades).read_text()) if os.path.exists(a.grades) else {}
    added = 0
    for f in sorted(glob.glob(os.path.join(a.outdir, 'batch_*.out.json'))):
        for k, v in json.loads(Path(f).read_text()).items():
            grades[k] = v
            added += 1
    Path(a.grades).write_text(json.dumps(grades, indent=0, ensure_ascii=False))
    print(f'merged {added} grades; cache size {len(grades)}')


def g_of(v):
    return int(v['grade'] if isinstance(v, dict) else v)


def ndcg(gs, k):
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gs[:k]))
    return dcg / sum(7 / math.log2(i + 2) for i in range(k))


def score(a):
    dump = json.loads(Path(a.dump).read_text())
    grades = json.loads(Path(a.grades).read_text())
    cases = {c['id']: c for c in load_cases(a.cases)}
    per, missing, rows = {}, 0, []
    for c in dump:
        cat, q = c['category'], c['query']
        if cat == 'irrelevant':
            s = float(not c['results'] and not c['recommendations'])
            per.setdefault(cat, []).append(s)
            rows.append((c['id'], cat, s, ''))
            continue
        gs = []
        for p in c['results'][:10]:
            v = grades.get(pkey(q, p['id']))
            if v is None:
                missing += 1
                v = 0
            gs.append(g_of(v))
        nd = ndcg(gs, 10)
        detail = ''.join(map(str, gs))
        if cat == 'mixed':
            nch = len(cases[c['id']]['choices'])
            cov_hits = [False] * nch
            for p, g in zip(c['results'][:10], gs):
                v = grades.get(pkey(q, p['id']))
                chs = v.get('choices', []) if isinstance(v, dict) else []
                for j, cg in enumerate(chs[:nch]):
                    if cg >= 2 and g >= 2:
                        cov_hits[j] = True
            cov = sum(cov_hits) / nch
            s = 0.5 * cov + 0.5 * nd
            detail += f' cov={cov:.2f}'
        elif cat == 'recommendation':
            gmap = {p['id']: g for p, g in zip(c['results'][:10], gs)}
            rg = []
            for r in c['recommendations'][:5]:
                v = grades.get(rkey(q, r['for_product_id'], r['id']))
                if v is None:
                    missing += 1
                    v = 0
                rg.append(g_of(v) if gmap.get(r['for_product_id'], 0) >= 2 else 0)
            comp = cases.get(c['id'], {}).get('complement', 'unknown')
            rs = (1.0 if not c['recommendations'] else 0.0) if comp is None else ndcg(rg, 5)
            s = 0.5 * nd + 0.5 * rs
            detail += f' rec={"".join(map(str, rg))} ({rs:.2f})'
        else:
            s = nd
        per.setdefault(cat, []).append(s)
        rows.append((c['id'], cat, s, detail))
    if a.verbose:
        for r in rows:
            print(f'{r[0]:10} {r[1]:15} {r[2]:.3f}  {r[3]}')
    for cat in ('ranking', 'unusual', 'irrelevant', 'mixed', 'recommendation'):
        if cat in per:
            v = per[cat]
            print(f'{cat:16}{len(v):>4}{sum(v) / len(v):>8.3f}')
    if missing:
        print(f'WARNING: {missing} ungraded items counted as 0')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prep'); p.add_argument('dump'); p.add_argument('grades'); p.add_argument('outdir')
    p.add_argument('--chunk', type=int, default=120); p.add_argument('--cases')
    m = sub.add_parser('merge'); m.add_argument('grades'); m.add_argument('outdir')
    s = sub.add_parser('score'); s.add_argument('dump'); s.add_argument('grades'); s.add_argument('--cases')
    s.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    {'prep': prep, 'merge': merge, 'score': score}[a.cmd](a)

"""Synthetic benchmark: queries generated from real catalog products, scored by attribute agreement.

Each query is written from one sampled product, the way benchmark authors usually build test cases, so the
expected type / color family / audience group / budget are known exactly. Prints per-template precision@10,
short-list rate (missing slots score zero in nDCG) and the worst queries.
Usage: LLM_PROVIDER=none .venv/bin/python eval/synth.py [N]
"""
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import query_parser as qp  # noqa: E402
import search  # noqa: E402

FAMILY = {}
for word, cols in qp.COLOR_WORDS.items():
    for col in cols:
        FAMILY.setdefault(col, word)
AUD_WORD = {'men': ['men', "men's", 'for him'], 'women': ['women', "women's", 'ladies', 'for her'],
            'kids': ['kids', 'children'], 'baby': ['baby', 'babies']}


def group(cat, i):
    for g in ('baby', 'kids', 'men', 'women'):
        if cat.aud_masks[g][i]:
            return g
    return None


def type_noun(pt):
    pt = pt.split('/')[0].lower()
    return {'t-shirt': 't-shirt', 'vest top': 'tank top', 'underwear bottom': 'briefs', 'hat': 'hat',
            'cap': 'cap', 'other accessories': 'accessory', 'garment set': 'set'}.get(pt, pt)


def make_queries(cat, n, seed=1):
    rnd = random.Random(seed)
    P = cat.products
    pool = [i for i, p in enumerate(P) if p['product_type'] not in ('Unknown', 'Other accessories', 'Other shoe')
            and p['color'] not in ('Other', 'Unknown')]
    out = []
    for _ in range(n):
        i = rnd.choice(pool)
        p = P[i]
        g = group(cat, i)
        fam = FAMILY.get(p['color'], p['color'].lower())
        noun = type_noun(p['product_type'])
        budget = int(((p['price']['amount'] // 500) + 1) * 500)
        t = rnd.choice(['color_type_aud', 'type_budget', 'pattern_type', 'name', 'desc', 'verbatim', 'plural_aud'])
        if t == 'color_type_aud' and g:
            q = f"{fam} {noun} for {rnd.choice(AUD_WORD[g])}"
            exp = dict(type=p['product_type'], fam=fam, aud=g)
        elif t == 'type_budget':
            q = f"{noun} under ₹{budget}"
            exp = dict(type=p['product_type'], max_price=budget)
        elif t == 'pattern_type' and p['pattern'] not in ('Solid', 'Unknown', 'Other pattern', 'Other structure'):
            q = f"{p['pattern'].lower()} {noun}"
            exp = dict(type=p['product_type'])
        elif t == 'name':
            q = p['name']
            exp = dict(type=p['product_type'], name=p['name'].casefold())
        elif t == 'desc' and p.get('description'):
            q = re.split(r'[.,]', p['description'])[0]
            exp = dict(type=p['product_type'])
        elif t == 'verbatim':
            q = f"{p['color'].lower()} {p['product_type'].lower()}"
            exp = dict(type=p['product_type'], color=p['color'])
        elif g:
            q = f"{noun}s for {rnd.choice(AUD_WORD[g])}"
            exp = dict(type=p['product_type'], aud=g)
            t = 'plural_aud'
        else:
            continue
        out.append((t, q, exp))
    return out


def check(cat, j, exp):
    p = cat.products[j]
    ok = p['product_type'] == exp['type']
    if 'fam' in exp:
        ok &= p['color'] in qp.COLOR_WORDS.get(exp['fam'], [p['color']])
    if 'color' in exp:
        ok &= p['color'] == exp['color']
    if 'aud' in exp:
        ok &= bool(cat.aud_masks[exp['aud']][j])
    if 'max_price' in exp:
        ok &= p['price']['amount'] <= exp['max_price']
    return ok


def main(n=400):
    cat = search.Catalog.load(str(Path(__file__).resolve().parent.parent / 'data/products.json'))
    stats = defaultdict(lambda: [0, 0.0, 0])  # count, precision sum, short lists
    worst = []
    for t, q, exp in make_queries(cat, n):
        ids = [x['id'] for x in cat.search({'query': q})['results']]
        idx = [cat.index_of[i] for i in ids]
        prec = sum(check(cat, j, exp) for j in idx) / 10
        s = stats[t]
        s[0] += 1
        s[1] += prec
        s[2] += len(ids) < 10
        worst.append((prec, t, q, len(ids), [cat.products[j]['product_type'] for j in idx[:4]], exp.get('type')))
    print(f"{'template':16s} {'n':>4s} {'prec@10':>8s} {'short':>6s}")
    tot = [0, 0.0, 0]
    for t, (c, ps, sh) in sorted(stats.items()):
        print(f"{t:16s} {c:4d} {ps / c:8.3f} {sh:6d}")
        tot = [tot[0] + c, tot[1] + ps, tot[2] + sh]
    print(f"{'ALL':16s} {tot[0]:4d} {tot[1] / tot[0]:8.3f} {tot[2]:6d}")
    worst.sort(key=lambda x: x[0])
    for w in worst[:45]:
        print(f"  {w[0]:.1f} [{w[1]}] {w[2]!r} n={w[3]} got={w[4]} want={w[5]}")


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400)

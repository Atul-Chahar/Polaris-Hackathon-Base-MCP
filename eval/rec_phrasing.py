"""Recommendation-intent matrix: phrasing templates x (anchor, complement) pairs.
Checks the primary list holds the anchor type and the recommendations hold the complement type."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import search  # noqa: E402

PAIRS = [('a black dress', 'bag', {'Dress'}, {'Bag', 'Shoulder bag', 'Cross-body bag', 'Tote bag'}),
         ('navy chinos for men', 'belt', {'Trousers'}, {'Belt'}),
         ('a white formal shirt', 'tie', {'Shirt'}, {'Tie'}),
         ('a red party dress', 'heels', {'Dress'}, {'Pumps', 'Heeled sandals', 'Heels', 'Wedge'}),
         ('a denim jacket', 'sneakers', {'Jacket'}, {'Sneakers'}),
         ('a bikini', 'sunglasses', {'Bikini top', 'Swimwear bottom', 'Swimwear set'}, {'Sunglasses'}),
         ('a wool coat', 'scarf', {'Coat', 'Jacket'}, {'Scarf'}),
         ('a summer dress', 'sun hat', {'Dress'}, {'Hat/brim', 'Straw hat', 'Bucket hat'}),
         ('white sneakers', 'socks', {'Sneakers'}, {'Socks'}),
         ('a blouse', 'earrings', {'Blouse'}, {'Earring', 'Earrings'})]
T = ['{a} with a matching {c}', '{a} and a {c} to go with it', '{a}, and recommend a {c} to wear with it',
     'I need {a}; also suggest a {c} that would go well with it', '{a} paired with a {c}',
     'Looking for {a}. What {c} would match?', '{a} plus a coordinating {c}', '{a} along with a complementary {c}',
     '{a} with a {c} to complete the look', 'Show me {a} and suggest a matching {c}',
     '{a} under 3000 with a {c} under 1500', 'Complete my outfit: {a} with a {c}',
     '{a} and something to go with it', '{a}, recommend accessories', '{a} with a {c} that matches']
cat = search.Catalog.load(str(Path(__file__).resolve().parent.parent / 'data/products.json'))
fails, tot = {}, 0
for ti, t in enumerate(T):
    ok_t = 0
    for a, cw, at, ct in PAIRS:
        q = t.format(a=a, c=cw)
        r = cat.search({'query': q, 'include_recommendations': True})
        P = [cat.products[cat.index_of[x['id']]]['product_type'] for x in r['results']]
        R = [cat.products[cat.index_of[x['id']]]['product_type'] for x in r['recommendations']]
        prim = sum(p in at for p in P) / 10
        if '{c}' in t:
            rec = sum(x in ct for x in R) / 5
        else:
            rec = 1.0 if len(R) >= 3 else 0.0
        good = prim >= 0.8 and rec >= 0.6
        ok_t += good
        if not good:
            fails.setdefault(ti, []).append(f"    prim={prim:.1f} rec={rec:.1f} {q!r}  P={P[:3]} R={R[:3]}")
    tot += ok_t
    print(f"{ok_t:2d}/10  {t}")
print(f"TOTAL {tot}/{len(T) * 10}")
for ti, f in fails.items():
    print(f"\n[{T[ti]}]")
    print('\n'.join(f[:4]))

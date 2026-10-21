"""Mixed-choice matrix: every requested choice must appear in the top 10, recommendations must stay empty."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import search  # noqa: E402
PAIRS = [('black jeans', 'white t-shirts', {'Trousers'}, {'T-shirt'}), ('a dress', 'a bag', {'Dress'}, {'Bag'}),
         ('a hoodie', 'joggers', {'Hoodie'}, {'Trousers'}), ('sneakers', 'socks', {'Sneakers'}, {'Socks'}),
         ('a bikini', 'sunglasses', {'Bikini top', 'Swimwear bottom', 'Swimwear set'}, {'Sunglasses'}),
         ('a blazer', 'formal trousers', {'Blazer'}, {'Trousers'}), ('a skirt', 'a blouse', {'Skirt'}, {'Blouse'}),
         ('pyjamas', 'slippers', {'Pyjama set', 'Pyjama bottom', 'Pyjama jumpsuit/playsuit'}, {'Slippers'})]
T = ['{a} and {b}', '{a} or {b}', '{a}, {b}', 'both {a} and {b}', 'either {a} or {b}', '{a} as well as {b}',
     '{a} & {b}', 'I want {a}. I also want {b}', 'show me {a} and {b} for women', '{a} and {b} under 3000 each',
     'looking for {a}; also need {b}', '{a} plus {b}']
cat = search.Catalog.load(str(Path(__file__).resolve().parent.parent / 'data/products.json'))
tot = 0
for t in T:
    ok = 0
    bad = []
    for a, b, at, bt in PAIRS:
        q = t.format(a=a, b=b)
        r = cat.search({'query': q})
        P = [cat.products[cat.index_of[x['id']]]['product_type'] for x in r['results']]
        good = any(p in at for p in P) and any(p in bt for p in P) and len(P) == 10
        ok += good
        if not good:
            bad.append(f"    {q!r} -> {P[:6]}")
    tot += ok
    print(f"{ok}/8  {t}")
    print('\n'.join(bad[:3]))
print(f"TOTAL {tot}/{len(T) * 8}")

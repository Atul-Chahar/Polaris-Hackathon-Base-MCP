"""Typo robustness: realistic misspellings of product nouns must still retrieve that product type."""
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import search  # noqa: E402
W = {'sneakers': {'Sneakers'}, 'trousers': {'Trousers'}, 'sweater': {'Sweater'}, 'jacket': {'Jacket', 'Blazer'},
     'hoodie': {'Hoodie'}, 'leggings': {'Leggings/Tights'}, 'blouse': {'Blouse'}, 'skirt': {'Skirt'},
     'dress': {'Dress'}, 'cardigan': {'Cardigan'}, 'sandals': {'Sandals', 'Heeled sandals'}, 'necklace': {'Necklace'},
     'earrings': {'Earring', 'Earrings'}, 'pyjamas': {'Pyjama set', 'Pyjama bottom'}, 'swimsuit': {'Swimsuit'},
     'sunglasses': {'Sunglasses'}, 'shorts': {'Shorts'}, 'jeans': {'Trousers'}, 't-shirt': {'T-shirt'},
     'bikini': {'Bikini top', 'Swimwear bottom', 'Swimwear set'}, 'scarf': {'Scarf'}, 'boots': {'Boots'},
     'blazer': {'Blazer'}, 'jumpsuit': {'Jumpsuit/Playsuit'}, 'backpack': {'Bag', 'Backpack'}, 'bracelet': {'Bracelet'}}
EXTRA = {'tshirt': 't-shirt', 'tee shirt': 't-shirt', 'sweatshirt': 'sweater'}


def typos(w, rnd):
    out = set()
    for _ in range(12):
        i = rnd.randrange(1, len(w) - 1)
        k = rnd.choice(['del', 'swap', 'dup', 'sub', 'del2'])
        if k == 'del':
            t = w[:i] + w[i + 1:]
        elif k == 'swap':
            t = w[:i] + w[i + 1] + w[i] + w[i + 2:] if i + 1 < len(w) else w
        elif k == 'dup':
            t = w[:i] + w[i] + w[i:]
        elif k == 'sub':
            near = {'a': 'e', 'e': 'a', 'i': 'e', 'o': 'u', 'u': 'o', 's': 'z', 'k': 'c', 'c': 'k', 'r': 't', 'n': 'm'}
            t = w[:i] + near.get(w[i], w[i]) + w[i + 1:]
        else:
            j = rnd.randrange(1, len(w) - 1)
            t = w[:i] + w[i + 1:]
            t = t[:j] + t[j + 1:] if len(t) > 4 else t
        if t != w and '-' not in t:
            out.add(t)
    return sorted(out)[:4]


cat = search.Catalog.load(str(Path(__file__).resolve().parent.parent / 'data/products.json'))
rnd = random.Random(3)
ok = tot = 0
fails = []
for w, types in W.items():
    for t in typos(w, rnd):
        for q in (t, f"{t} for women", f"black {t}"):
            P = [cat.products[cat.index_of[x['id']]]['product_type'] for x in cat.search({'query': q})['results']]
            good = sum(p in types for p in P) >= 6
            ok += good
            tot += 1
            if not good:
                fails.append(f"  {q!r} ({w}) -> corrected={cat.correct(q)!r} got={P[:3]}")
print(f"typo matrix {ok}/{tot}")
print('\n'.join(fails[:40]))

"""Context-garment phrasing: in "X to wear over/under my Y", Y is what the shopper already has; X is the target.
Scores type precision@10 against the garments a shopper would accept. Usage: LLM_PROVIDER=none .venv/bin/python eval/context_phrasing.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import search  # noqa: E402

OUTER = {'Cardigan', 'Jacket', 'Blazer', 'Coat', 'Outdoor Waistcoat'}
TOPS = {'Top', 'Vest top', 'T-shirt', 'Blouse'}
CASES = [
    ('something to wear over my dress', OUTER), ('a layer to put on over a t-shirt', OUTER),
    ('what can I throw on over my blouse', OUTER), ('a layer to wear over my top for the office', OUTER),
    ('something warm to wear over my shirt', OUTER), ('a light layer for over a sundress', OUTER),
    ('a cardigan to wear over my dress', {'Cardigan'}), ('a blazer to go over my t-shirt', {'Blazer'}),
    ('a jacket to wear over a hoodie', {'Jacket', 'Coat'}), ('a top to go under my blazer', TOPS),
    ('a t-shirt to wear under my shirt', {'T-shirt'}), ('a vest top to wear under a cardigan', {'Vest top'}),
    ('a shirt to wear under my sweater', {'Shirt'}), ('a coat to wear over my suit', {'Coat', 'Jacket'}),
    ('a jacket over 3000', {'Jacket', 'Blazer'}), ('a dress under 2000', {'Dress'}),
]


def main():
    cat = search.Catalog.load(str(Path(__file__).resolve().parent.parent / 'data/products.json'))
    total = 0.0
    for q, want in CASES:
        res = cat.search({'query': q, 'limit': 10})['results']
        types = [cat.products[cat.index_of[r['id']]]['product_type'] for r in res]
        p = sum(t in want for t in types) / 10
        total += p
        print(f'{p:4.1f}  {q!r:52} {types[:4]}')
    print(f'TOTAL {total:.1f}/{len(CASES)}')


if __name__ == '__main__':
    main()

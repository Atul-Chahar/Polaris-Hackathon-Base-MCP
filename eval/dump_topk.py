"""Dump top-k catalog facts (and recommendations) for semantic queries, for strict LLM-judge review.
Usage: .venv/bin/python eval/dump_topk.py OUT.json [--cases eval/devset.json] [--k 10]
Runs the Catalog in-process (no server). Each case needs 'id', 'category', 'arguments'; validity cases are skipped.
"""
import argparse, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('LLM_PROVIDER', 'none')
from search import Catalog  # noqa: E402


def facts(p):
    return {'id': p['id'], 'name': p['name'], 'description': p['description'], 'product_type': p['product_type'],
            'category': p['category'], 'audience': p['audience'], 'section': p['section'], 'color': p['color'],
            'pattern': p['pattern'], 'price_inr': p['price']['amount'], 'rating': p['rating']['average']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--cases', default=str(ROOT / 'eval/devset.json'))
    ap.add_argument('--k', type=int, default=10)
    a = ap.parse_args()
    cat = Catalog.load(ROOT / 'data/products.json')
    by_id = {p['id']: p for p in cat.products}
    out = []
    for case in json.loads(Path(a.cases).read_text()):
        if case['category'] == 'validity':
            continue
        args = case['arguments']
        res = cat.search(args)
        out.append({'id': case['id'], 'category': case['category'], 'query': args.get('query', ''),
                    'arguments': args,
                    'results': [facts(by_id[r['id']]) for r in res['results'][:a.k]],
                    'recommendations': [{**facts(by_id[r['id']]), 'for_product_id': r['for_product_id']}
                                        for r in res['recommendations']]})
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f'{len(out)} cases -> {a.out}')


if __name__ == '__main__':
    main()

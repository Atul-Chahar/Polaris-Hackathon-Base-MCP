"""Offline build of product embeddings: python index_build.py  ->  data/emb.npy (float16, rows in ID order)."""
import json
import sys
import time
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

ROOT = Path(__file__).resolve().parent
MODEL = 'BAAI/bge-small-en-v1.5'


def doc_text(p):
    return (f"{p['name']}. {p.get('description') or ''} Type: {p['product_type']}. "
            f"Category: {p['category']}. For: {p['audience']}, {p['section']}. "
            f"Color: {p['color']}. Pattern: {p['pattern']}.")


def main(out=ROOT / 'data/emb.npy'):
    products = sorted(json.loads((ROOT / 'data/products.json').read_text(encoding='utf-8')), key=lambda p: p['id'])
    texts = [doc_text(p) for p in products]
    unique = sorted(set(texts))
    where = {t: i for i, t in enumerate(unique)}
    print(f'{len(texts)} products, {len(unique)} unique docs', flush=True)
    model = TextEmbedding(MODEL, threads=8)
    start, vecs = time.time(), []
    for i, v in enumerate(model.embed(unique, batch_size=128)):
        vecs.append(v)
        if i % 5000 == 0:
            print(i, round(time.time() - start), flush=True)
    mat = np.asarray(vecs, dtype=np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    emb = mat[[where[t] for t in texts]].astype(np.float16)
    np.save(out, emb)
    (ROOT / 'data/emb.meta.json').write_text(json.dumps({'model': MODEL, 'dim': emb.shape[1], 'rows': len(products),
                                                          'normalized': True, 'order': 'id ascending'}))
    print('done', emb.shape, round(time.time() - start), flush=True)


if __name__ == '__main__':
    main(*(Path(a) for a in sys.argv[1:]))

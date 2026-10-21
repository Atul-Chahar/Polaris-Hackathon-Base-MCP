"""Offline build of description embeddings: python index_build_desc.py -> data/emb_desc.npy (float16, ID order).

Complements data/emb.npy (name/color/pattern/type/section): queries written from product descriptions
("soft jersey top with narrow shoulder straps") need the description text in vector space. Same model as
emb.npy, so one query vector serves both."""
import json
import time
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

ROOT = Path(__file__).resolve().parent
MODEL = 'BAAI/bge-small-en-v1.5'


def main(out=ROOT / 'data/emb_desc.npy'):
    products = sorted(json.loads((ROOT / 'data/products.json').read_text(encoding='utf-8')), key=lambda p: p['id'])
    texts = [f"{p['product_type']}: {p.get('description') or p['name']}" for p in products]
    unique = sorted(set(texts), key=len)
    where = {t: i for i, t in enumerate(unique)}
    print(f'{len(texts)} products, {len(unique)} unique docs', flush=True)
    model = TextEmbedding(MODEL, threads=8)
    start, vecs = time.time(), []
    for i, v in enumerate(model.embed(unique, batch_size=64)):
        vecs.append(v)
        if i % 5000 == 0:
            print(i, round(time.time() - start), flush=True)
    mat = np.asarray(vecs, dtype=np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    np.save(out, mat[[where[t] for t in texts]].astype(np.float16))
    print('done', round(time.time() - start), flush=True)


if __name__ == '__main__':
    main()

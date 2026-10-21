"""Build step: replace a Git LFS pointer with the real catalog and verify its SHA-256."""
import hashlib
import os
import urllib.request

PATH = 'data/products.json'
SHA = '05b6aa5e8e8c1c8c997d584f8288e432862454f8820531e13473443e83c8f073'
URL = 'https://media.githubusercontent.com/media/Atul-Chahar/Polaris-Hackathon-Base-MCP/main/data/products.json'

if os.path.getsize(PATH) < 1_000_000:
    urllib.request.urlretrieve(URL, PATH)
digest = hashlib.sha256(open(PATH, 'rb').read()).hexdigest()
assert digest == SHA, f'catalog hash mismatch: {digest}'
print('catalog ok', os.path.getsize(PATH))

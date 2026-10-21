FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 \
    FASTEMBED_CACHE_PATH=/app/models \
    HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /app
RUN useradd --uid 10001 --create-home student

# 1) deps (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) pre-download the embedding model into a fixed cache so runtime never hits the network
RUN python -c "from fastembed import TextEmbedding; m = TextEmbedding('BAAI/bge-small-en-v1.5'); print(len(next(iter(m.embed(['warmup'])))))" \
 && chown -R student:student /app/models
# after this point, fastembed/huggingface-hub resolve the model from local files only
ENV HF_HUB_OFFLINE=1

# 3) data (products.json, emb.npy, emb.meta.json, ...) - big, rarely changes
COPY --chown=student:student data/ ./data/

# 4) code (small, changes often). Add new top-level dirs here if teammates create them.
COPY --chown=student:student schemas/ ./schemas/
COPY --chown=student:student *.py ./

USER student
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/healthz', timeout=3)"
CMD ["python", "server.py"]

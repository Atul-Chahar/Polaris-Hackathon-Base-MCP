# Deploy (EC2 m7i-flex.large, ap-south-1, Elastic IP 15.206.29.88)

Normal redeploy, from the repo folder on your machine:

```sh
KEY_FILE=~/.ssh/polaris-search-key.pem deploy/push_and_run.sh 15.206.29.88
```

The script:
1. Rsyncs the code and data.
2. Builds the image **on the server**, so it is linux/amd64.
3. Restarts the container via `~/run.sh`, which uses `--restart unless-stopped` and `-p 8000:8000`.
4. Waits for `/healthz` and runs `smoke_test.py` against the public URL.

`~/run.sh` on the server sets:
`MCP_ALLOWED_HOSTS=localhost:*,127.0.0.1:*,[::1]:*,15.206.29.88:*,15.206.29.88,15-206-29-88.sslip.io,15-206-29-88.sslip.io:*,<organizer host>,<organizer host>:*`.
HTTPS for Claude Desktop is a Caddy container on the same server: `https://15-206-29-88.sslip.io/mcp`.

Checks after every deploy:

```sh
curl http://15.206.29.88:8000/healthz                    # {"status":"ok","products":105126}
.venv/bin/python smoke_test.py http://15.206.29.88:8000/mcp
ssh -i ~/.ssh/polaris-search-key.pem ec2-user@15.206.29.88 \
  'docker exec polaris-search sha256sum /app/data/products.json /app/search.py /app/query_parser.py'
#  products.json must be 05b6aa5e8e8c1c8c997d584f8288e432862454f8820531e13473443e83c8f073 (fetch_catalog.py
#  also asserts this at build time, replacing a Git LFS pointer); the .py hashes must match `git show HEAD:<file>`.
.venv/bin/python eval/perf.py http://15.206.29.88:8000/mcp --reps 1
```

Rollback: `ssh ... '~/run.sh polaris-search:<older tag>'` (list tags with `docker images polaris-search`).
Never deploy while a benchmark run is in progress.

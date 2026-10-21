# Deploy runbook

1. Credentials: `aws sts get-caller-identity` must work. Region: `export AWS_REGION=ap-south-1` (pick the organizer runner's region).
2. Infra (idempotent, safe to re-run): `deploy/aws_deploy.sh`. It prints the IP, the ssh command and `http://IP:8000/mcp`.
3. Secrets: write a local `app.env` (`LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...`, `NVIDIA_API_KEY=...`). It is never baked into the image.
4. First deploy (about 3-5 min, mostly bootstrap + pip on the box): `KEY_FILE=~/.ssh/polaris-search-key.pem deploy/push_and_run.sh IP --env app.env`
5. Redeploys (about 30-60 s): the same command, `--env` optional. Only changed files go over rsync, the remote build reuses cached layers, then it restarts, waits for `/healthz` and runs `smoke_test.py`.
6. Make sure `data/emb.npy` exists before deploying (`index_build.py`), or the script warns.
7. Logs: `ssh -i KEY ec2-user@IP docker logs -f polaris-search`. Roll back: `ssh ... '~/run.sh polaris-search:<older tag>'`.
8. Don't redeploy while a benchmark run is in flight. Submit `http://IP:8000/mcp`, never localhost or a private IP.
9. Security group is 0.0.0.0/0 on 22 and 8000. You can narrow 8000 to the organizer runner IP and 22 to your own IP.
10. No-AWS fallback: on any VM with a public IP + Docker, run `git clone`/`rsync` of the repo (with data/emb.npy), then `docker build -t polaris-search:latest . && docker run -d --name polaris-search --restart unless-stopped -p 8000:8000 --env-file app.env -e MCP_ALLOWED_HOSTS="localhost:*,127.0.0.1:*,PUBLIC_IP:*,PUBLIC_IP" polaris-search:latest`, and open port 8000 in that provider's firewall.

#!/bin/bash
# FAST redeploy: rsync the build context to the box and `docker build` there.
# Why not `docker save | ssh`: the image is ~1 GB uncompressed (data + model + onnxruntime) and
# would be re-sent every time. rsync sends data/ (~190 MB, compressed in transit) only once;
# later deploys ship just the changed .py files, and the remote build reuses cached layers
# (deps -> model -> data -> code), so a code-only redeploy is ~10-20 s plus container startup.
# Usage: KEY_FILE=~/.ssh/polaris-search-key.pem deploy/push_and_run.sh IP [--env path/to/app.env]
set -euo pipefail
IP="${1:?usage: push_and_run.sh IP [--env app.env]}"
ENV_FILE=""
[ "${2:-}" = "--env" ] && ENV_FILE="${3:?--env needs a file}"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/polaris-search-key.pem}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SSH_OPTS=(-i "$KEY_FILE" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
ssh_() { ssh "${SSH_OPTS[@]}" "ec2-user@$IP" "$@"; }
TAG="polaris-search:$(date +%Y%m%d-%H%M%S)"

[ -f "$REPO/data/emb.npy" ] || echo "WARNING: data/emb.npy missing - semantic search will be degraded" >&2

echo "== waiting for bootstrap (docker installed)"
until ssh_ 'test -f ~/.bootstrap-done && docker info >/dev/null 2>&1'; do sleep 5; done

if [ -n "$ENV_FILE" ]; then
  echo "== uploading env file (secrets stay on the box, not in the image)"
  scp "${SSH_OPTS[@]}" "$ENV_FILE" "ec2-user@$IP:/home/ec2-user/app.env"
  ssh_ 'chmod 600 ~/app.env'
fi

echo "== rsync build context"
rsync -az --delete -e "ssh ${SSH_OPTS[*]}" \
  --exclude .git --exclude .venv --exclude venv --exclude '__pycache__' --exclude eval/ \
  --exclude tests/ --exclude scratch/ --exclude '*.env' --exclude .env --exclude models/ \
  "$REPO/" "ec2-user@$IP:/home/ec2-user/app/"

echo "== remote build $TAG"
ssh_ "cd ~/app && docker build -t $TAG -t polaris-search:latest . 2>&1 | tail -5"

echo "== restart container"
ssh_ "~/run.sh $TAG"

echo "== waiting for /healthz"
START=$(date +%s)
until curl -fsS --max-time 3 "http://$IP:8000/healthz" >/dev/null 2>&1; do
  if [ $(( $(date +%s) - START )) -gt 240 ]; then
    echo "healthz timeout; container logs:" >&2; ssh_ 'docker logs --tail 50 polaris-search' >&2; exit 1
  fi
  sleep 2
done
echo "healthy after $(( $(date +%s) - START ))s: $(curl -sS "http://$IP:8000/healthz")"

echo "== smoke test"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY=python3
(cd "$REPO" && "$PY" smoke_test.py "http://$IP:8000/mcp")
echo "DEPLOYED: http://$IP:8000/mcp   (image $TAG)"
echo "rollback: ssh ec2-user@$IP '~/run.sh <previous tag>'   (docker images | grep polaris-search)"

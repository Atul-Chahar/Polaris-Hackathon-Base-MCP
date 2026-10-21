#!/bin/bash
# EC2 user-data for Amazon Linux 2023 (x86_64). Installs docker + git + rsync and drops
# /home/ec2-user/run.sh, which (re)starts the container with the public IP from IMDSv2
# in MCP_ALLOWED_HOSTS. Image/code arrive later via deploy/push_and_run.sh.
set -euxo pipefail

dnf -y install docker git rsync
systemctl enable --now docker
usermod -aG docker ec2-user

# Secrets live only here on the box (never in the image). Fill in via push_and_run.sh or by hand.
if [ ! -f /home/ec2-user/app.env ]; then
  cat > /home/ec2-user/app.env <<'ENV'
# LLM_PROVIDER=gemini
# GEMINI_API_KEY=
# NVIDIA_API_KEY=
ENV
  chmod 600 /home/ec2-user/app.env
  chown ec2-user:ec2-user /home/ec2-user/app.env
fi

cat > /home/ec2-user/run.sh <<'RUN'
#!/bin/bash
# Usage: ~/run.sh [image]   (default polaris-search:latest)
set -euo pipefail
IMAGE="${1:-polaris-search:latest}"
TOKEN=$(curl -sS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')
PUBLIC_IP=$(curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
docker rm -f polaris-search >/dev/null 2>&1 || true
docker run -d --name polaris-search --restart unless-stopped -p 8000:8000 \
  --env-file /home/ec2-user/app.env \
  -e MCP_ALLOWED_HOSTS="localhost:*,127.0.0.1:*,[::1]:*,${PUBLIC_IP}:*,${PUBLIC_IP}" \
  "$IMAGE"
echo "started $IMAGE -> http://${PUBLIC_IP}:8000/mcp"
RUN
chmod +x /home/ec2-user/run.sh
chown ec2-user:ec2-user /home/ec2-user/run.sh
mkdir -p /home/ec2-user/app && chown ec2-user:ec2-user /home/ec2-user/app
touch /home/ec2-user/.bootstrap-done

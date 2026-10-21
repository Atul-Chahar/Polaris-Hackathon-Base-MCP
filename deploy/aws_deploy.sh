#!/bin/bash
# Idempotent: creates/reuses key pair, security group, one EC2 instance, Elastic IP.
# Usage: AWS_REGION=ap-south-1 deploy/aws_deploy.sh
set -euo pipefail
REGION="${AWS_REGION:-ap-south-1}"
NAME="${DEPLOY_NAME:-polaris-search}"
KEY_NAME="${KEY_NAME:-$NAME-key}"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/$KEY_NAME.pem}"
SG_NAME="$NAME-sg"
HERE="$(cd "$(dirname "$0")" && pwd)"
aws() { command aws --region "$REGION" "$@"; }

aws sts get-caller-identity --query Account --output text >/dev/null

# --- key pair ---
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  mkdir -p "$(dirname "$KEY_FILE")"
  aws ec2 create-key-pair --key-name "$KEY_NAME" --key-type ed25519 \
    --query KeyMaterial --output text > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
  echo "created key pair $KEY_NAME -> $KEY_FILE"
elif [ ! -f "$KEY_FILE" ]; then
  echo "WARNING: key pair $KEY_NAME exists in AWS but $KEY_FILE is missing locally" >&2
fi

# --- security group (default VPC) ---
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$SG_NAME" --description "Polaris MCP search" \
    --vpc-id "$VPC_ID" --query GroupId --output text)
fi
# 0.0.0.0/0 for speed. Can be narrowed to the organizer runner IP (port 8000) and your own IP (port 22).
for PORT in 22 8000; do
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port "$PORT" \
    --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
done

# --- instance ---
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values="$NAME" Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
  AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query Parameter.Value --output text)
  for TYPE in m7i-flex.large c7i-flex.large; do
    if INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$TYPE" \
        --key-name "$KEY_NAME" --security-group-ids "$SG_ID" \
        --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3,DeleteOnTermination=true}' \
        --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2 \
        --user-data "file://$HERE/ec2_user_data.sh" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
        --query 'Instances[0].InstanceId' --output text); then
      echo "launched $INSTANCE_ID ($TYPE)"; break
    fi
    echo "launch with $TYPE failed, trying next type" >&2
    INSTANCE_ID=""
  done
  [ -n "$INSTANCE_ID" ] || { echo "could not launch instance" >&2; exit 1; }
else
  echo "reusing $INSTANCE_ID"
  aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null 2>&1 || true
fi
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# --- Elastic IP ---
ALLOC_ID=$(aws ec2 describe-addresses --filters Name=tag:Name,Values="$NAME" \
  --query 'Addresses[0].AllocationId' --output text)
if [ "$ALLOC_ID" = "None" ] || [ -z "$ALLOC_ID" ]; then
  ALLOC_ID=$(aws ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" \
    --query AllocationId --output text)
fi
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" --allow-reassociation >/dev/null
IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp' --output text)

echo
echo "instance : $INSTANCE_ID"
echo "ssh      : ssh -i $KEY_FILE ec2-user@$IP"
echo "next     : KEY_FILE=$KEY_FILE deploy/push_and_run.sh $IP"
echo "MCP URL  : http://$IP:8000/mcp"

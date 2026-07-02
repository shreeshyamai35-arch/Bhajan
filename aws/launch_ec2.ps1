# BhajanForge — launch a GPU EC2 box for RVC voice cloning (Windows/PowerShell).
#
# PREREQS (one-time, your side):
#   1. AWS account with an ACTIVE payment method.
#   2. A GPU vCPU quota > 0 for "Running On-Demand G and VT instances"
#      (Service Quotas -> EC2 -> request increase; new accounts start at 0).
#   3. AWS CLI installed + `aws configure` done (access key/secret/region).
#   4. An EC2 key pair (.pem) you can SSH with.
#
# Then run:  .\launch_ec2.ps1 -KeyName my-key -Region ap-south-1

param(
  [Parameter(Mandatory = $true)][string]$KeyName,
  [string]$Region = "ap-south-1",
  [string]$InstanceType = "g4dn.xlarge",
  [int]$VolumeGb = 60
)

# Ubuntu 22.04 Deep Learning OSS AMI (ships NVIDIA drivers + CUDA).
# Resolve the latest AMI id for the region via SSM public parameter:
$amiId = aws ssm get-parameters `
  --names "/aws/service/deeplearning/ami/x86_64/oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id" `
  --region $Region --query "Parameters[0].Value" --output text

if (-not $amiId -or $amiId -eq "None") {
  Write-Host "Could not resolve Deep Learning AMI. Falling back to base Ubuntu 22.04."
  $amiId = aws ssm get-parameters `
    --names "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id" `
    --region $Region --query "Parameters[0].Value" --output text
}
Write-Host "Using AMI: $amiId"

$runJson = aws ec2 run-instances `
  --image-id $amiId `
  --instance-type $InstanceType `
  --key-name $KeyName `
  --region $Region `
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$VolumeGb,\"VolumeType\":\"gp3\"}}]" `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=bhajanforge-rvc}]" `
  --output json | ConvertFrom-Json

$instanceId = $runJson.Instances[0].InstanceId
Write-Host "Launched instance: $instanceId"
Write-Host "Waiting for it to enter 'running'..."
aws ec2 wait instance-running --instance-ids $instanceId --region $Region

$ip = aws ec2 describe-instances --instance-ids $instanceId --region $Region `
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text

Write-Host ""
Write-Host "=========================================================="
Write-Host "Instance running at $ip"
Write-Host "Next steps:"
Write-Host "  scp -i <key>.pem aws/rvc_server.py aws/ec2_rvc_setup.sh ubuntu@${ip}:~/"
Write-Host "  ssh -i <key>.pem ubuntu@$ip"
Write-Host "  bash ec2_rvc_setup.sh"
Write-Host ""
Write-Host "STOP THE BOX WHEN DONE (it bills per hour):"
Write-Host "  aws ec2 terminate-instances --instance-ids $instanceId --region $Region"
Write-Host "=========================================================="

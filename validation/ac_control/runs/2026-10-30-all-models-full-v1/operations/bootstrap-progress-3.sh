set -eu
date -u
ps -eo pid,etime,comm | awk '$3 == "docker" || $3 == "python3" || $3 == "aws" {print}'
df -h /
tail -n 6 /var/lib/amazon/ssm/i-01e87f489911925cf/document/orchestration/581f2ed6-cb69-4f57-9c45-f8bc9d11b0ed/awsrunShellScript/0.awsrunShellScript/stdout
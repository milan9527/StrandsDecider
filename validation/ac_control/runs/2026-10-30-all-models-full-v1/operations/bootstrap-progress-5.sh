set -eu
date -u
docker ps --no-trunc --format '{{.ID}} {{.Status}} {{.Command}}'
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}'
ls -l /opt/ac-nine-tests/logs/strands-model-integrity.json
tail -n 3 /var/lib/amazon/ssm/i-01e87f489911925cf/document/orchestration/581f2ed6-cb69-4f57-9c45-f8bc9d11b0ed/awsrunShellScript/0.awsrunShellScript/stderr
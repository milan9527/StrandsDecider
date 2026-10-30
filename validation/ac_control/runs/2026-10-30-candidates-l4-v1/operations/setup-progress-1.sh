set -eu
ps -eo pid,etime,pcpu,pmem,comm,args | grep -E 'python|uv|aws' | head -20
ls -l /opt/ac-candidate-tests/models-verified.json /opt/ac-candidate-tests/logs/pplx-requirements.txt 2>/dev/null || true
free -m
df -h /opt/ac-candidate-tests
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader

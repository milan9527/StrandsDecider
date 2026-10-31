set -eu
date -u
ps -eo pid,etime,comm,args | grep -E "[d]ocker pull|[a]ws s3|[u]v pip|[p]ython3 -|[a]pt.systemd.daily"
df -h /
du -sh /opt/ac-nine-tests/models/decider /opt/ac-nine-tests/models/liquid 2>/dev/null || true
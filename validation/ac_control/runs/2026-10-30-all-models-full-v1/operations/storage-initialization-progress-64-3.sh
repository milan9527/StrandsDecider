set -eu
date -u
cat /opt/ac-nine-tests/logs/storage-initialization.json
ls -l /proc/2828/fd 2>/dev/null | tail -n 2
ls -l /opt/ac-nine-tests/logs/model-verification.json 2>/dev/null || true
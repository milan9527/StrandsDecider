set -eu
cp /opt/ac-nine-tests/logs/storage-initialization.json /opt/ac-nine-tests/logs/storage-initialization-attempt-16.json
aws s3 cp /opt/ac-nine-tests/logs/storage-initialization-attempt-16.json s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/logs/storage-initialization-attempt-16.json --only-show-errors
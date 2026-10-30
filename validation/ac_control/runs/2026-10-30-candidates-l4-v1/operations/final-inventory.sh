set -eu
aws s3 cp s3://strands-decider-vllm-632930644527/input/ac-candidates/2026-10-30-l4-v1/final-inventory.py /opt/ac-candidate-tests/final-inventory.py --only-show-errors
/opt/ac-candidate-tests/tools/bin/python -c 'import hashlib,pathlib; assert hashlib.sha256(pathlib.Path('"'"'/opt/ac-candidate-tests/final-inventory.py'"'"').read_bytes()).hexdigest() == '"'"'2cab28b87893bfca47de8db9c0db4696cdf768312bb41a0746834dcceb0eb2d3'"'"''
/opt/ac-candidate-tests/tools/bin/python /opt/ac-candidate-tests/final-inventory.py
aws s3 sync /opt/ac-candidate-tests/logs s3://strands-decider-vllm-632930644527/output/ac-candidates/2026-10-30-l4-v1/logs --only-show-errors
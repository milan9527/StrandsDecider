set -eu
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
export UV_CACHE_DIR=/opt/ac-candidate-tests/uv-cache
export CUDA_HOME=/usr/local/cuda-13.0
export PATH=/opt/ac-candidate-tests/envs/clef/bin:/usr/local/cuda-13.0/bin:$PATH
export MAX_JOBS=2
/opt/ac-candidate-tests/tools/bin/uv pip install --python /opt/ac-candidate-tests/envs/clef/bin/python 'torch==2.11.0' 'torchvision==0.26.0' ninja packaging wheel setuptools
/opt/ac-candidate-tests/tools/bin/uv pip install --python /opt/ac-candidate-tests/envs/clef/bin/python --no-build-isolation 'causal-conv1d==1.7.0'
/opt/ac-candidate-tests/tools/bin/uv pip freeze --python /opt/ac-candidate-tests/envs/clef/bin/python > /opt/ac-candidate-tests/logs/clef-final-requirements.txt
aws s3 sync /opt/ac-candidate-tests/logs s3://strands-decider-vllm-632930644527/output/ac-candidates/2026-10-30-l4-v1/logs --only-show-errors
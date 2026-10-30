set -eu
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
export UV_CACHE_DIR=/opt/ac-candidate-tests/uv-cache-clef-rebuild
export CUDA_HOME=/usr/local/cuda-13.0
export PATH=/opt/ac-candidate-tests/envs/clef/bin:/usr/local/cuda-13.0/bin:$PATH
export MAX_JOBS=2
export TORCH_CUDA_ARCH_LIST=8.9
export CAUSAL_CONV1D_FORCE_BUILD=TRUE
trap 'aws s3 sync /opt/ac-candidate-tests/logs s3://strands-decider-vllm-632930644527/output/ac-candidates/2026-10-30-l4-v1/logs --only-show-errors' EXIT
/opt/ac-candidate-tests/tools/bin/uv pip install --python /opt/ac-candidate-tests/envs/clef/bin/python --no-build-isolation --no-binary causal-conv1d --reinstall-package causal-conv1d "causal-conv1d==1.7.0" > /opt/ac-candidate-tests/logs/clef-causal-rebuild.log 2>&1
/opt/ac-candidate-tests/envs/clef/bin/python -c "import torch,causal_conv1d; from transformers import Qwen3_5ForConditionalGeneration; print(torch.__version__, causal_conv1d.__version__)" > /opt/ac-candidate-tests/logs/clef-causal-import.txt
/opt/ac-candidate-tests/tools/bin/uv pip freeze --python /opt/ac-candidate-tests/envs/clef/bin/python > /opt/ac-candidate-tests/logs/clef-final-requirements.txt
systemctl reset-failed ac-candidate-clef || true
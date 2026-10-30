set -eu
candidate_root=/opt/ac-candidate-tests
candidate_uv="$candidate_root/tools/bin/uv"
export UV_CACHE_DIR="$candidate_root/uv-cache"
export MAX_JOBS=2
export CUDA_HOME=/usr/local/cuda-13.0
export PATH="$CUDA_HOME/bin:$PATH"
"$candidate_uv" venv --python /usr/bin/python3 "$candidate_root/envs/knowline"
"$candidate_uv" pip install --python "$candidate_root/envs/knowline/bin/python" 'sglang==0.5.21' 'transformers==5.12.1' requests
"$candidate_uv" pip freeze --python "$candidate_root/envs/knowline/bin/python" > "$candidate_root/logs/knowline-requirements.txt"
"$candidate_uv" venv --python /usr/bin/python3 "$candidate_root/envs/torchcast"
"$candidate_uv" pip install --python "$candidate_root/envs/torchcast/bin/python" 'torch==2.9.1' --index-url https://download.pytorch.org/whl/cu128
"$candidate_uv" pip install --python "$candidate_root/envs/torchcast/bin/python" 'transformers==5.8.1' 'flash-linear-attention==0.5.2' accelerate safetensors huggingface-hub ninja packaging wheel setuptools
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$PATH"
"$candidate_uv" pip install --python "$candidate_root/envs/torchcast/bin/python" --no-build-isolation 'causal-conv1d>=1.7'
"$candidate_uv" pip freeze --python "$candidate_root/envs/torchcast/bin/python" > "$candidate_root/logs/torchcast-requirements.txt"
"$candidate_uv" venv --python /usr/bin/python3 "$candidate_root/envs/clef"
"$candidate_uv" pip install --python "$candidate_root/envs/clef/bin/python" 'torch==2.11.0' 'transformers==5.10.2' 'flash-linear-attention==0.5.2' accelerate safetensors pillow
"$candidate_uv" pip freeze --python "$candidate_root/envs/clef/bin/python" > "$candidate_root/logs/clef-requirements.txt"
"$candidate_uv" venv --python /usr/bin/python3 "$candidate_root/envs/h2o"
"$candidate_uv" pip install --python "$candidate_root/envs/h2o/bin/python" 'vllm==0.30.0' 'transformers==5.20.2'
"$candidate_uv" pip freeze --python "$candidate_root/envs/h2o/bin/python" > "$candidate_root/logs/h2o-requirements.txt"
df -h "$candidate_root"

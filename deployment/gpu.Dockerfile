FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/tmp/huggingface \
    TRITON_CACHE_DIR=/tmp/triton OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false \
    DECIDER_DEVICE=cuda MODEL_HOST=0.0.0.0 NVIDIA_DRIVER_CAPABILITIES=compute,utility
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app
RUN pip install --no-cache-dir torch==2.7.1 --index-url https://download.pytorch.org/whl/cu126
COPY deployment/model-requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir flash-linear-attention==0.5.2 \
    'https://github.com/Dao-AILab/causal-conv1d/releases/download/v1.7.0/causal_conv1d-1.7.0%2Bcu12torch2.7cxx11abiTRUE-cp311-cp311-linux_x86_64.whl'
COPY .deployment/models /opt/models
COPY deployment/model_server.py /srv/model_server.py
USER 10001
EXPOSE 8099
CMD ["python", "/srv/model_server.py"]

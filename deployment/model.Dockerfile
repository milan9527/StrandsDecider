FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/tmp/huggingface \
    OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app
COPY deployment/model-requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY .deployment/models /opt/models
COPY deployment/model_server.py /srv/model_server.py
USER 10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3)"
CMD ["python", "/srv/model_server.py"]

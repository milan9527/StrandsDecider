set -eu
mkdir -p /opt/ac-input-tests/logs/model-manifests
cp /opt/ac-input-tests/models/liquid/manifest.json /opt/ac-input-tests/logs/model-manifests/liquid.json
cp /opt/ac-input-tests/models/pplx/manifest.json /opt/ac-input-tests/logs/model-manifests/pplx.json
cp /opt/ac-input-tests/models/knowline/manifest.json /opt/ac-input-tests/logs/model-manifests/knowline.json
cp /opt/ac-input-tests/models/torchcast/manifest.json /opt/ac-input-tests/logs/model-manifests/torchcast.json
cp /opt/ac-input-tests/models/clef/manifest.json /opt/ac-input-tests/logs/model-manifests/clef.json
cp /opt/ac-input-tests/models/h2o/manifest.json /opt/ac-input-tests/logs/model-manifests/h2o.json
/opt/ac-candidate-tests/tools/bin/uv pip freeze --python /opt/ac-input-tests/runner-env/bin/python > /opt/ac-input-tests/logs/runner-requirements.txt
aws s3 sync /opt/ac-input-tests/logs s3://strands-decider-vllm-632930644527/output/ac-input-optimization/2026-10-31-nine-v1/logs --only-show-errors
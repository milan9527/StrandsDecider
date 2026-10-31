set -eu
test -s /opt/ac-input-tests/run/run_optimized_models.py
test ! -d /opt/ac-input-tests/run/profiles/schema_once/results
aws s3 cp s3://strands-decider-vllm-632930644527/input/ac-input-optimization/2026-10-31-nine-v1/runtime-amendment-v2.tar.gz /opt/ac-input-tests/runtime-amendment-v2.tar.gz --only-show-errors
python3 - <<'APPLY'
import hashlib,tarfile,pathlib
path='/opt/ac-input-tests/runtime-amendment-v2.tar.gz'
assert hashlib.sha256(open(path,"rb").read()).hexdigest()=='079f4e0d937a12144de0d7fdc513ea1f8f4cf168048b75dc0a078ad6d093c66c'
with tarfile.open(path) as tar:
 assert all(m.isfile() and not pathlib.PurePosixPath(m.name).is_absolute() and '..' not in pathlib.PurePosixPath(m.name).parts for m in tar.getmembers())
 tar.extractall('/opt/ac-input-tests/run',filter="data")
print('Full-state columnar input amendment applied before GPU inference.')
APPLY
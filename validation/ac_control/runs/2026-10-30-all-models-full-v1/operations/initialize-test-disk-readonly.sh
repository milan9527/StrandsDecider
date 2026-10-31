set -eu
python3 -c '
import concurrent.futures,json,mmap,os,pathlib,subprocess,threading,time
device="/dev/nvme0n1"
assert subprocess.check_output(["findmnt","-n","-o","SOURCE","/"],text=True).strip() in ("/dev/root",device+"p1")
assert not subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip()
size=int(subprocess.check_output(["blockdev","--getsize64",device],text=True))
assert size == 250 * 1024**3
chunk=4*1024**2
assert size % chunk == 0
workers=16
started=time.monotonic()
lock=threading.Lock()
completed=0
last=started
output=pathlib.Path("/opt/ac-nine-tests/logs/storage-initialization.json")
def record(status):
    elapsed=time.monotonic()-started
    value={"status":status,"device":device,"read_only":True,"direct_io":True,
           "workers":workers,"chunk_bytes":chunk,"total_bytes":size,
           "read_bytes":completed*chunk,"elapsed_seconds":elapsed,
           "mean_mib_s":completed*chunk/1024**2/max(elapsed,.001),
           "model_inference_paused":True,"read_ahead_kb_before_inference":128}
    output.write_text(json.dumps(value,indent=2)+"\n")
    print(json.dumps(value),flush=True)
def worker(index):
    global completed,last
    fd=os.open(device,os.O_RDONLY|os.O_DIRECT)
    buffer=mmap.mmap(-1,chunk)
    try:
        for block in range(index,size//chunk,workers):
            assert os.preadv(fd,[buffer],block*chunk)==chunk
            with lock:
                completed+=1
                if time.monotonic()-last>=30:
                    record("running")
                    last=time.monotonic()
    finally:
        buffer.close()
        os.close(fd)
record("running")
try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for future in [pool.submit(worker,index) for index in range(workers)]:
            future.result()
    assert completed*chunk==size
    assert not subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip()
finally:
    for path in (device,device+"p1"):
        subprocess.run(["blockdev","--setra","256",path],check=True)
assert pathlib.Path("/sys/block/nvme0n1/queue/read_ahead_kb").read_text().strip()=="128"
record("complete")
'
aws s3 cp /opt/ac-nine-tests/logs/storage-initialization.json s3://strands-decider-vllm-632930644527/output/ac-all-models/2026-10-30-full-v1/logs/storage-initialization.json --only-show-errors
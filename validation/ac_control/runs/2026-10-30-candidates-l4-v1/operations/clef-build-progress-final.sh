/opt/ac-candidate-tests/tools/bin/python - <<'CODE'
import subprocess
from pathlib import Path
print(Path('/opt/ac-candidate-tests/logs/clef-causal-rebuild.log').read_text()[-2000:])
for line in subprocess.check_output(['ps','-eo','pid,etime,pcpu,rss,args'],text=True).splitlines():
 if '/nvvm/bin/cicc' in line:
  cols=line.split(); arches=[cols[i+1] for i,x in enumerate(cols[:-1]) if x=='-arch']; print(' '.join(cols[:4]),arches,[x for x in cols if x.endswith('.cu')][:1])
CODE

/opt/ac-candidate-tests/tools/bin/python - <<'CODE'
import subprocess
from pathlib import Path
print(Path('/opt/ac-candidate-tests/logs/clef-causal-rebuild.log').read_text()[-2500:])
print('
'.join(subprocess.check_output(['ps','-eo','pid,ppid,etime,pcpu,rss,args','--sort=-pcpu'],text=True).splitlines()[:9]))
CODE

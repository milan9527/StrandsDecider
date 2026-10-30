/opt/ac-candidate-tests/tools/bin/python - <<'CODE'
import subprocess
print(subprocess.check_output(['free','-m'],text=True))
for line in subprocess.check_output(['ps','-eo','pid,etime,pcpu,rss,args'],text=True).splitlines():
 if any(word in line for word in ('nvcc','cicc','ninja','cc1plus')) and 'script.sh' not in line:
  print(line[:600])
CODE

set -eu
date -u
docker top a79bf94faf5b -eo pid,ppid,stat,wchan:32,comm
docker inspect a79bf94faf5b --format '{{.State.Pid}}'
for task_pid in $(docker top a79bf94faf5b -eo pid | tail -n +2); do echo "$task_pid"; cat /proc/"$task_pid"/io; ls -l /proc/"$task_pid"/fd | tail -n 6; done
tail -n 12 /opt/ac-candidate-tests/logs/clef-causal-rebuild.log
ps -eo pid,etime,pcpu,rss,args | rg "[n]vcc|[c]icc|[n]inja|[c]c1plus"
#!/bin/bash
cd ~/transcribe-engine
export PATH=$HOME/miniconda3/envs/transcribe-engine/bin:$PATH
export HF_HOME=/mnt/d/AI/Models/HuggingFace HF_HUB_CACHE=/mnt/d/AI/Models/HuggingFace/hub
export PYTHONFAULTHANDLER=1 PYTHONIOENCODING=utf-8
PY=.venv/bin/python
for r in 1 2 3; do
  rm -f ~/r${r}_*.log
  $PY -m uvicorn transcribe_engine.api_server:create --factory --host 127.0.0.1 --port 8000 > ~/r${r}_api.log 2>&1 &
  sleep 8
  $PY -m transcribe_engine.worker gpu > ~/r${r}_gpu.log 2>&1 &
  $PY -m transcribe_engine.worker cpu > ~/r${r}_cpu.log 2>&1 &
  sleep 5
  KEY=$($PY scripts/seed.py 2>/dev/null | tail -1)
  for n in 1 2; do for t in $(seq 1 12); do out=$($PY ~/create_job.py "$KEY" 2>&1 | tail -n 1); case "$out" in JOB*) break;; esac; sleep 15; done; done
  sleep 120
  echo "round $r: gpu_fatal=$(grep -a -c "fatal exception\|Traceback" ~/r${r}_gpu.log) cpu_fatal=$(grep -a -c "fatal exception\|Traceback" ~/r${r}_cpu.log) persisted=$(grep -a -c "PERSISTING\", \"status\": \"ok" ~/r${r}_gpu.log) chunk_failed=$(grep -a -c "chunk failed" ~/r${r}_gpu.log)" >> ~/loop_result.txt
  pkill -f "transcribe_engine.worker" ; pkill -f "uvicorn transcribe_engine"; sleep 10
done
echo LOOP_DONE >> ~/loop_result.txt

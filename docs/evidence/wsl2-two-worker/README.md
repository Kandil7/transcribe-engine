# WSL2 two-worker test (D-078)

Evidence for running the GPU and CPU workers together under WSL2 on the Quadro RTX 5000.

- run_loop.sh: starts the API, the GPU worker and the CPU worker together, creates two jobs per round through the API,
  waits two minutes, then records crashes and persisted jobs. The API key is read at run time and is not stored here.
- create_job.py: uploads the clip and creates one job. Takes the key as its argument.
- loop_result.txt: the output of three rounds.

Result: three rounds, six jobs persisted, no worker crash, no failed chunk. Native Windows crashed in the same
scenario, so this is the basis for D-078.

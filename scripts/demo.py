"""Local demo (S10, `make demo FILE=...`): upload a file, wait for the job, save the JSON result.

Needs the API running (`make dev`) and TE_API_KEY in the environment (the key from `make seed`). The
script does not read .env.local (D-026). Output goes to out/<job id>.json (git-ignored). SRT and VTT
arrive with S15; until a real ASR exists (S12) the transcript is empty by design (D-035).
"""

import os
import pathlib
import sys
import time

import httpx

API = "http://127.0.0.1:8000"
OUT = pathlib.Path("out")
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
TIMEOUT_S = 900.0


def _fail(message: str) -> int:
    sys.stderr.write(message + "\n")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return _fail("usage: python scripts/demo.py <audio file>")
    key = os.environ.get("TE_API_KEY")
    if not key:
        return _fail("set TE_API_KEY to the key printed by `make seed`")
    path = pathlib.Path(argv[1])
    if not path.is_file():
        return _fail("the audio file does not exist")
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=API, timeout=60.0) as client:
        ticket = client.post("/v1/uploads", headers=headers)
        ticket.raise_for_status()
        body = ticket.json()
        upload = httpx.post(
            body["url"],
            data=body["fields"],
            files={"file": (path.name, path.read_bytes())},
            timeout=600.0,
        )
        upload.raise_for_status()
        created = client.post(
            "/v1/transcriptions",
            headers=headers,
            json={"upload_id": body["upload_id"], "language": "ar", "diarization": False},
        )
        created.raise_for_status()
        job_id = created.json()["id"]
        sys.stdout.write(f"job {job_id} created\n")
        state = _wait(client, headers, job_id)
        sys.stdout.write(f"state {state}\n")
        if state != "COMPLETED":
            return _fail(f"job ended in {state}")
        result = client.get(f"/v1/transcriptions/{job_id}/result?format=json", headers=headers)
        result.raise_for_status()
    OUT.mkdir(exist_ok=True)
    target = OUT / f"{job_id}.json"
    target.write_bytes(result.content)
    data = result.json()
    sys.stdout.write(f"words {len(data['words'])}; warnings {data['warnings']}; saved {target}\n")
    return 0


def _wait(client: httpx.Client, headers: dict[str, str], job_id: str) -> str:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        job = client.get(f"/v1/transcriptions/{job_id}", headers=headers)
        job.raise_for_status()
        data = job.json()
        if data["state"] in TERMINAL:
            return str(data["state"])
        sys.stdout.write(f"state {data['state']} progress {data.get('progress', 0)}\n")
        time.sleep(2.0)
    return "TIMEOUT"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

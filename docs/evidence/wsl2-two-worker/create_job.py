"""Upload the demo clip and create one job through the API (D-078 evidence).

Usage: python create_job.py <API key>. The key is passed as an argument, never stored here.
"""

import sys

import httpx

CLIP = "/mnt/d/AI/Models/namaa-tts/92fe3f9212ab443c.wav"


def main(key: str) -> None:
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=120.0) as client:
        ticket = client.post("/v1/uploads", headers=headers)
        ticket.raise_for_status()
        body = ticket.json()
        with open(CLIP, "rb") as handle:
            upload = httpx.post(
                body["url"],
                data=body["fields"],
                files={"file": ("clip.wav", handle.read())},
                timeout=120.0,
            )
        upload.raise_for_status()
        job = client.post(
            "/v1/transcriptions",
            headers=headers,
            json={"upload_id": body["upload_id"], "language": "ar", "diarization": False},
        )
        job.raise_for_status()
        sys.stdout.write(f"JOB {job.json()['id']}\n")


if __name__ == "__main__":
    main(sys.argv[1])

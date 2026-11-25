"""S3-compatible object storage adapter (S07). Works with AWS S3 and local MinIO.

boto3 is synchronous, so each call runs in a worker thread (asyncio.to_thread).
The Port stays async.
Library errors are translated into domain errors at this boundary (CLAUDE.md).
"""

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Literal

from botocore.exceptions import ClientError

from transcribe_engine.application.ports.storage import ObjectInfo
from transcribe_engine.domain.errors import PermanentError, TransientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

__all__ = ["S3ObjectStorage"]

SSE_ALGORITHM: Literal["AES256"] = "AES256"  # every put is encrypted at rest (S07 rule)
_NOT_FOUND = frozenset({"404", "NoSuchKey", "NotFound"})
_TRANSIENT = frozenset({"SlowDown", "RequestTimeout", "ServiceUnavailable", "InternalError"})


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _translate(exc: ClientError) -> Exception:
    status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
    code = _error_code(exc)
    if status >= 500 or code in _TRANSIENT:
        return TransientError(f"object store unavailable: {code}")
    return PermanentError(f"object store rejected request: {code}")


class S3ObjectStorage:
    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def head(self, key: str) -> ObjectInfo | None:
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if _error_code(exc) in _NOT_FOUND:
                return None
            raise _translate(exc) from exc
        return ObjectInfo(
            key=key,
            size=int(response["ContentLength"]),
            encryption=response.get("ServerSideEncryption"),
        )

    async def read_range(self, key: str, start: int, length: int) -> bytes:
        if length <= 0:
            return b""
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=self._bucket,
                Key=key,
                Range=f"bytes={start}-{start + length - 1}",
            )
        except ClientError as exc:
            raise _translate(exc) from exc
        return await asyncio.to_thread(response["Body"].read)

    async def stream(self, key: str, chunk_bytes: int = 8 * 2**20) -> AsyncIterator[bytes]:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            raise _translate(exc) from exc
        body = response["Body"]
        while chunk := await asyncio.to_thread(body.read, chunk_bytes):
            yield chunk

    async def put(self, key: str, data: bytes | AsyncIterator[bytes]) -> None:
        payload = data if isinstance(data, bytes) else b"".join([c async for c in data])
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=payload,
                ServerSideEncryption=SSE_ALGORITHM,
            )
        except ClientError as exc:
            raise _translate(exc) from exc

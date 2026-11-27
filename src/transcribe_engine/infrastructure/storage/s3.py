"""S3-compatible object storage adapter (S07). Works with AWS S3 and local MinIO.

boto3 is synchronous, so each call runs in a worker thread (asyncio.to_thread).
The Port stays async. Library errors (ClientError, BotoCoreError) become domain errors here.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from botocore.exceptions import BotoCoreError, ClientError

from transcribe_engine.application.ports.storage import ObjectInfo, UploadTicket
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.storage_keys import check_incoming_key, check_prefix

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

__all__ = ["MAX_UPLOAD_BYTES", "MAX_UPLOAD_EXPIRY", "S3ObjectStorage"]

SSE_ALGORITHM: Literal["AES256"] = "AES256"  # every put is encrypted at rest (S07 rule)
MAX_UPLOAD_BYTES = 2 * 2**30  # D-015
MAX_UPLOAD_EXPIRY = timedelta(minutes=15)  # S07: links are valid 15 minutes (D-015)
_DELETE_BATCH = 1000  # S3 accepts at most 1000 keys per DeleteObjects call
_NOT_FOUND = frozenset({"404", "NoSuchKey", "NotFound"})
_TRANSIENT = frozenset({"SlowDown", "RequestTimeout", "ServiceUnavailable", "InternalError"})


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _translate(exc: ClientError) -> Exception:
    """Map an S3 error to a domain error. Keep only the error code, never bucket or key names."""
    error = exc.response.get("Error", {})
    code = str(error.get("Code", ""))
    status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
    if status >= 500 or code in _TRANSIENT:
        return TransientError(f"object store unavailable: {code}")
    return PermanentError(f"object store rejected request: {code}")


async def _call[R](fn: Callable[..., R], *args: object, **kwargs: object) -> R:
    """Run one blocking client call in a thread; translate library errors at the boundary."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except ClientError as exc:
        raise _translate(exc) from exc
    except BotoCoreError as exc:  # connection, timeout, credential-chain errors
        raise TransientError("object store connection failed") from exc


class S3ObjectStorage:
    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def presign_upload(self, key: str, max_bytes: int, expires: timedelta) -> UploadTicket:
        """Presigned POST: the signed policy limits size and pins the key (D-013, D-015)."""
        check_incoming_key(key)
        if not 1 <= max_bytes <= MAX_UPLOAD_BYTES:
            raise ValueError("max_bytes must be between 1 and the configured upload cap")
        if not timedelta(0) < expires <= MAX_UPLOAD_EXPIRY:
            raise ValueError("expires must be positive and at most 15 minutes")
        issued = datetime.now(UTC)
        post = await _call(
            self._client.generate_presigned_post,
            Bucket=self._bucket,
            Key=key,
            Conditions=[
                ["content-length-range", 0, max_bytes],
                {"key": key},
                {"x-amz-server-side-encryption": SSE_ALGORITHM},
            ],
            Fields={"x-amz-server-side-encryption": SSE_ALGORITHM},
            ExpiresIn=int(expires.total_seconds()),
        )
        return UploadTicket(
            upload_id=key.rsplit("/", 1)[-1],
            url=post["url"],
            fields=post["fields"],
            expires_at=issued + expires,
            max_bytes=max_bytes,
        )

    async def head(self, key: str) -> ObjectInfo | None:
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if _error_code(exc) in _NOT_FOUND:
                return None
            raise _translate(exc) from exc
        except BotoCoreError as exc:
            raise TransientError("object store connection failed") from exc
        return ObjectInfo(
            key=key,
            size=int(response["ContentLength"]),
            encryption=response.get("ServerSideEncryption"),
        )

    async def read_range(self, key: str, start: int, length: int) -> bytes:
        if start < 0:
            raise ValueError("start must be >= 0")
        if length <= 0:
            return b""
        response = await _call(
            self._client.get_object,
            Bucket=self._bucket,
            Key=key,
            Range=f"bytes={start}-{start + length - 1}",
        )
        return await _call(response["Body"].read)

    async def stream(self, key: str, chunk_bytes: int = 8 * 2**20) -> AsyncIterator[bytes]:
        response = await _call(self._client.get_object, Bucket=self._bucket, Key=key)
        body = response["Body"]
        while chunk := await _call(body.read, chunk_bytes):
            yield chunk

    async def put(self, key: str, data: bytes | AsyncIterator[bytes]) -> None:
        # The iterator form buffers the whole object; multipart upload is a follow-up (BUILD_LOG).
        payload = data if isinstance(data, bytes) else b"".join([c async for c in data])
        await _call(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=payload,
            ServerSideEncryption=SSE_ALGORITHM,
        )

    async def delete(self, key: str) -> bool:
        """Delete one object; True if it existed. Idempotent (S21)."""
        if await self.head(key) is None:
            return False
        await _call(self._client.delete_object, Bucket=self._bucket, Key=key)
        return True

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object under `prefix`; return how many were removed (D-015)."""
        check_prefix(prefix)
        keys = await _call(self._list_keys, prefix)
        removed = 0
        for start in range(0, len(keys), _DELETE_BATCH):
            batch = keys[start : start + _DELETE_BATCH]
            response = await _call(
                self._client.delete_objects,
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )
            failed = response.get("Errors", [])
            if failed:
                raise TransientError(f"{len(failed)} objects could not be deleted")
            removed += len(batch)
        return removed

    def _list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for page in self._client.get_paginator("list_objects_v2").paginate(
            Bucket=self._bucket, Prefix=prefix
        ):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

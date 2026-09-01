"""Bounded streaming decoder for the Server V4 multipart wire format."""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass
from typing import BinaryIO

from document_parser.server.s0_domain import S0Error, S0TemporaryError, S0ValidationError
from document_parser.server.v4_domain import V4Config, V4PayloadTooLargeError


@dataclass(slots=True)
class ParsedV4Multipart:
    metadata_bytes: bytes
    manifest_bytes: bytes
    files: list[tuple[str, BinaryIO]]

    def close(self) -> None:
        for _path, stream in self.files:
            stream.close()


def parse_v4_multipart(
    stream: BinaryIO,
    *,
    boundary: str,
    content_length: int,
    config: V4Config,
) -> ParsedV4Multipart:
    try:
        boundary_bytes = boundary.encode("ascii")
    except UnicodeEncodeError as exc:
        raise S0ValidationError("UPLOAD_BOUNDARY_INVALID", "multipart boundary must be ASCII") from exc
    if not boundary_bytes or len(boundary_bytes) > 200 or any(value < 33 or value > 126 for value in boundary_bytes):
        raise S0ValidationError("UPLOAD_BOUNDARY_INVALID", "multipart boundary is invalid")
    if content_length > config.max_request_bytes:
        raise V4PayloadTooLargeError("UPLOAD_REQUEST_LIMIT", "upload request exceeds configured limit")

    from werkzeug.exceptions import RequestEntityTooLarge
    from werkzeug.sansio.multipart import (
        Data,
        Epilogue,
        Field,
        File,
        MultipartDecoder,
        NeedData,
        Preamble,
    )

    decoder = MultipartDecoder(
        boundary_bytes,
        max_form_memory_size=config.max_manifest_bytes,
        max_parts=config.max_bundle_files + 2,
    )
    files: list[tuple[str, BinaryIO]] = []
    metadata = io.BytesIO()
    manifest = io.BytesIO()
    current: Field | File | None = None
    target: BinaryIO | None = None
    part_index = 0
    bundle_bytes = 0
    epilogue = False
    try:
        while True:
            chunk = stream.read(min(64 * 1024, content_length + 1))
            if chunk:
                content_length -= len(chunk)
                if content_length < 0:
                    raise S0ValidationError("UPLOAD_LENGTH_MISMATCH", "request body exceeds Content-Length")
                decoder.receive_data(chunk)
            else:
                decoder.receive_data(None)
            while True:
                try:
                    event = decoder.next_event()
                except RequestEntityTooLarge as exc:
                    raise V4PayloadTooLargeError("UPLOAD_REQUEST_LIMIT", "multipart request exceeds configured limit") from exc
                if isinstance(event, NeedData):
                    break
                if isinstance(event, Preamble):
                    if event.data.strip(b"\r\n"):
                        raise S0ValidationError(
                            "UPLOAD_MULTIPART_INVALID", "multipart preamble is not allowed"
                        )
                    continue
                if isinstance(event, Epilogue):
                    if event.data.strip(b"\r\n"):
                        raise S0ValidationError(
                            "UPLOAD_MULTIPART_INVALID", "multipart epilogue is not allowed"
                        )
                    epilogue = True
                    break
                if isinstance(event, Field):
                    _validate_part_headers(event.headers)
                    part_index += 1
                    if part_index != 1 or event.name != "metadata":
                        raise S0ValidationError(
                            "UPLOAD_PART_ORDER_INVALID",
                            "metadata must be the first multipart part",
                        )
                    current = event
                    target = metadata
                    if event.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                        raise S0ValidationError(
                            "UPLOAD_PART_MEDIA_TYPE_INVALID",
                            "metadata part must use application/json",
                        )
                    continue
                if isinstance(event, File):
                    _validate_part_headers(event.headers)
                    part_index += 1
                    if part_index == 1:
                        raise S0ValidationError(
                            "UPLOAD_PART_ORDER_INVALID",
                            "metadata must be the first multipart part",
                        )
                    if part_index == 2:
                        if event.name != "manifest" or event.filename != "manifest.json":
                            raise S0ValidationError(
                                "UPLOAD_PART_ORDER_INVALID",
                                "manifest.json must be the second multipart part",
                            )
                        if event.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                            raise S0ValidationError(
                                "UPLOAD_PART_MEDIA_TYPE_INVALID",
                                "manifest part must use application/json",
                            )
                        target = manifest
                    else:
                        if event.name != "bundle_file" or not event.filename:
                            raise S0ValidationError(
                                "UPLOAD_PART_INVALID",
                                "bundle file parts must use name=bundle_file and a filename",
                            )
                        target = tempfile.SpooledTemporaryFile(
                            max_size=1024 * 1024,
                            mode="w+b",
                            dir=config.staging_root,
                        )
                        files.append((event.filename, target))
                    current = event
                    continue
                if isinstance(event, Data):
                    if current is None or target is None:
                        raise S0ValidationError("UPLOAD_MULTIPART_INVALID", "multipart data has no part header")
                    if part_index == 1 and metadata.tell() + len(event.data) > 64 * 1024:
                        raise V4PayloadTooLargeError("UPLOAD_METADATA_LIMIT", "upload metadata exceeds 64 KiB")
                    if part_index == 2 and manifest.tell() + len(event.data) > config.max_manifest_bytes:
                        raise V4PayloadTooLargeError("BUNDLE_MANIFEST_TOO_LARGE", "bundle manifest exceeds configured limit")
                    if part_index > 2:
                        bundle_bytes += len(event.data)
                        if bundle_bytes > config.max_bundle_bytes:
                            raise V4PayloadTooLargeError("BUNDLE_BYTE_LIMIT", "bundle exceeds configured byte limit")
                    target.write(event.data)
                    if not event.more_data and part_index > 2:
                        target.seek(0)
                    continue
                raise S0ValidationError("UPLOAD_MULTIPART_INVALID", "unsupported multipart event")
            if epilogue:
                break
            if not chunk:
                raise S0ValidationError("UPLOAD_MULTIPART_INCOMPLETE", "multipart request ended before final boundary")
        if content_length != 0:
            raise S0ValidationError("UPLOAD_LENGTH_MISMATCH", "request body is shorter than Content-Length")
        if part_index < 2 or not files:
            raise S0ValidationError("UPLOAD_PARTS_MISSING", "metadata, manifest, and bundle files are required")
        return ParsedV4Multipart(metadata.getvalue(), manifest.getvalue(), files)
    except S0Error:
        for _path, file_stream in files:
            file_stream.close()
        raise
    except RequestEntityTooLarge as exc:
        for _path, file_stream in files:
            file_stream.close()
        raise V4PayloadTooLargeError(
            "UPLOAD_REQUEST_LIMIT", "multipart request exceeds configured limit"
        ) from exc
    except (UnicodeError, ValueError) as exc:
        for _path, file_stream in files:
            file_stream.close()
        raise S0ValidationError("UPLOAD_MULTIPART_INVALID", "multipart request is malformed") from exc
    except OSError as exc:
        for _path, file_stream in files:
            file_stream.close()
        raise S0TemporaryError("UPLOAD_STORAGE_TEMPORARY", "temporary multipart staging failure") from exc
    except BaseException:
        for _path, file_stream in files:
            file_stream.close()
        raise


def _validate_part_headers(headers) -> None:
    size = sum(len(str(name)) + len(str(value)) + 4 for name, value in headers.items())
    if size > 8 * 1024:
        raise V4PayloadTooLargeError("UPLOAD_PART_HEADER_LIMIT", "multipart part headers exceed 8 KiB")

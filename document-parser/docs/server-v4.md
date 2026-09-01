# Server V4 durable bundle upload

Server V4 is the product HTTP boundary between a Scanner sender and the existing Server S1
incremental pipeline. It receives one immutable Scanner V2 spread bundle, writes it below
server-owned storage, and returns an acknowledgement only after S1 has committed its durable
spread and fragment receipt.

V4 does not run OCR, braille conversion, TTS, or datapack publication in the request thread.

## Endpoint

```http
POST /api/v1/scan-sessions/{scan_session_id}/spreads
Content-Type: multipart/form-data; boundary=...
Content-Length: ...
X-API-Key: ...
Idempotency-Key: upload-...
X-ASL-Upload-Digest: <lowercase SHA-256>
```

Chunked transfer and compressed request bodies are not supported. `Content-Length` is required so
the server can reject an oversized bundle before writing it. The default logical bundle limits are
32 files, 128 MiB of listed file bytes, a 4 MiB manifest, and 16,384 pixels per UVDoc dimension.

Multipart parts must be ordered as follows:

1. `metadata`: `application/json`, no filename
2. `manifest`: `application/json`, filename `manifest.json`
3. one `bundle_file` part per `manifest.files` record; filename is the relative POSIX path

Bundle file order is not significant. Absolute paths, backslashes, dot segments, duplicate paths,
unknown parts, missing files, and additional files are rejected.

## Metadata schema

```json
{
  "schema_version": 1,
  "device_id": "asl-device-prototype-01",
  "sequence": 1,
  "artifact_id": "artifact-...",
  "spread_id": "spread-...",
  "source_frame_id": "frame-...",
  "manifest_sha256": "64-lowercase-hex",
  "file_count": 9,
  "total_file_bytes": 12345678
}
```

The URL scan session is authoritative. `device_id` must own that scan. All identities must match
the immutable Scanner manifest, whose `session_id` must equal the scan session ID.

## Canonical upload digest

`X-ASL-Upload-Digest` identifies logical content, not raw multipart bytes. The server and client
construct the following object, sort `files` by path, and hash the UTF-8 output of:

```python
json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
```

The payload contains upload schema version, scan/device/sequence/artifact/spread/source identities,
the exact manifest SHA-256, and each file's path, size, and SHA-256. Multipart boundary and bundle
file order may change on retry without changing this digest.

The implementation helper is
`document_parser.server.v4_domain.canonical_upload_digest`.

## Acknowledgement

```json
{
  "status": "acked",
  "receipt_id": "receipt-...",
  "scan_session_id": "scan-...",
  "sequence": 1,
  "artifact_id": "artifact-...",
  "manifest_sha256": "...",
  "upload_digest": "...",
  "spread_status": "received",
  "accepted_at": "server UTC timestamp"
}
```

The first accepted upload returns `201`. An exact logical replay already present in S1 returns
`200`. A replay using the same idempotency key returns the stored status and body and adds
`Idempotency-Replayed: true`.

ACK means all of the following are complete:

- the complete bundle is in the server-owned receive tree;
- each listed file matched its declared size and SHA-256;
- the staging directory was promoted atomically on the same filesystem;
- S1 revalidated the bundle and committed `scan_spreads` plus two `page_fragments` rows.

ACK does not mean the parser or finalization worker is complete. Use these existing endpoints for
later state:

```text
GET  /api/v1/scan-sessions/{scan_session_id}/spreads
GET  /api/v1/scan-sessions/{scan_session_id}
POST /api/v1/scan-sessions/{scan_session_id}/seal-intent
```

## Idempotency and retry

- same scan/key/digest after a terminal result: exact stored response, no mutation;
- same scan/key with a different digest: `409 IDEMPOTENCY_KEY_REUSED`;
- same sequence with different content: `409 SPREAD_SEQUENCE_COLLISION`;
- artifact reused at another logical position: `409 ARTIFACT_ID_COLLISION`;
- response loss or retryable error: resend the same immutable bundle, sequence, key, and digest;
- deterministic validation failure: terminal structured error, never infer ACK.

The SQLite schema version 4 `spread_upload_attempts` journal distinguishes receiving, abandoned,
promoted, accepted, and rejected attempts. A restart discards incomplete private staging, resumes a
promoted bundle through the same S1 boundary, and handles a crash between directory promotion and
journal update by recognizing the server-generated final storage key. A server-generated final
directory with no journal row is moved to quarantine without deleting its contents.

## Storage and limits

```text
DATAPACKS_DIR/_server/upload-staging/{upload_id}.partial/
DATAPACKS_DIR/_server/received/v4/{upload_id}/
DATAPACKS_DIR/_server/upload-quarantine/
```

Client IDs and paths are never used as server directory names. Staging and received roots must be
on the same filesystem. The writer flushes each file, attempts directory fsync where supported,
then promotes the directory with `os.replace` before calling S1.

Combined-server options:

```text
--upload-max-staging-mib   default 512
--upload-max-received-mib  default 8192
--upload-max-concurrent    default 1
```

Quota exhaustion returns a retryable structured error with `Retry-After` and does not evict an
accepted or promoted bundle. Scanner V3-B now supplies the single-sender persistent outbox, retry,
strict ACK validation, and ACK-driven local cache cleanup. E0-Core now composes the Scanner bridge,
Coordinator, C0, S0, and V3-B through an actual local HTTP/SQLite flow. Whole active-session restart
and physical Laptop validation remain later work. The HTTP route reserves a writer slot and the
request's bounded staging budget before multipart file data is spooled.

## Security boundary

The endpoint uses the existing prototype `X-API-Key`. It also verifies that the metadata device
owns the scan, but the shared key is not device-level authorization. External TLS deployment,
device-specific credentials, mTLS, and rate-limit hardening are separate work.

No API response exposes a filesystem/storage key, API key, raw manifest, or image bytes.

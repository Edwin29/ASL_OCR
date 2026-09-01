# Server S1 incremental datapack pipeline

Server S1 extends the SQLite-backed S0 control plane with durable spread acceptance, per-page
Document Parser fragments, ordered append assembly, and atomic immutable-revision publication.
The SQLite database remains authoritative across process restarts.

## Boundary and acknowledgement

S1 itself remains transport-neutral. Server V4 now provides the public artifact-upload endpoint,
stores an immutable Scanner V2 bundle below `DATAPACKS_DIR/_server/received`, then calls the S1
application boundary with its server-owned relative key:

```python
receipt = pipeline.accept_verified_spread(
    VerifiedSpreadInput(
        scan_session_id=scan_id,
        sequence=sequence,
        artifact_id=artifact_id,
        spread_id=spread_id,
        source_frame_id=source_frame_id,
        bundle_storage_key=storage_key,
        manifest_sha256=manifest_sha256,
    )
)
```

The returned receipt acknowledges verified bundle durability and the committed spread/fragment
rows. It does not mean that OCR, braille conversion, TTS, or final publication has completed.
Scanner-to-server HTTP upload is implemented by Server V4; see [server-v4.md](server-v4.md). The
Scanner V3-B single-sender durable outbox, retry, strict ACK validation, and ACK-driven local cache
cleanup are implemented and locally verified. During development the Scanner, coordinator, HTTP
client, and outbox run in a device-host role that substitutes for the Raspberry Pi application host.
E0-Core locally composes that full boundary; physical Laptop validation, whole active-session
restart, and the later Pi port remain separate work.

The validator requires an exact Scanner bundle manifest, both ready pages, confined relative
paths, matching file hashes and sizes, decodable UVDoc images, and configured resource limits.
Only each side's UVDoc result is sent to Document Parser; source/crop images are retained as
evidence and are not reparsed as fallbacks.

## Persistent processing

Migration version 2 adds `scan_spreads`, `page_fragments`, and `finalize_runs`, plus finalization
fields on `scan_sessions`. The S1 worker claims queued fragments with a persistent lease. Expired
claims are returned to the queue or made terminal after the configured attempt limit.

Page IDs are deterministic from scan session, client sequence, and side. Final order is always:

```text
base pages, 1-left, 1-right, 2-left, 2-right, ... N-left, N-right
```

Page-number OCR is neither identity nor ordering authority. A rejected/error fragment blocks
publication; S1 never publishes a READY datapack by silently dropping a page.

## Seal and publication

`POST /api/v1/scan-sessions/{id}/seal-intent` records the S0 cutoff and creates a persistent
finalize run when S1 is configured. Publication waits for exactly the contiguous sequences
`1..through_sequence`, with two READY fragments per sequence.

The assembler preserves the base document pages, focus IDs, and audio entries, appends the new
pages, synthesizes missing utterances, and validates the complete document/audio/manifest through
the normal datapack loader and navigation session. It promotes a complete directory below:

```text
DATAPACKS_DIR/_revisions/{storage_key}/r000000NN/
```

Only after filesystem promotion does one SQLite transaction insert the READY revision, supersede
the base, switch `current_revision`, seal the scan, and publish the finalize journal. A promoted
directory with an uncommitted journal is revalidated and resumed after restart. Existing READY
data remains current on assembly, validation, or TTS failure.

Cutoff zero is a no-op for an existing READY datapack and publishes its base revision. A new empty
DRAFT fails explicitly with `EMPTY_DRAFT_SCAN`.

## Status API

S1 adds the spread list and enriches the existing scan view:

```text
GET  /api/v1/scan-sessions/{scan_session_id}
GET  /api/v1/scan-sessions/{scan_session_id}/spreads
POST /api/v1/scan-sessions/{scan_session_id}/seal-intent
```

The scan view includes `published_revision`, `spread_counts`, structured finalization state, and
errors. Polling is read-only. A device may treat only `sealed` with a published revision as READY.

## Runtime composition

The combined server starts one S1 background worker and shares serialized PaddleOCR-VL and Piper
wrappers with the retained legacy `/jobs` path. This prevents the legacy path and S1 from entering
the same model or synthesizer concurrently. Defaults remain one persistent worker; throughput and
GPU resource use have not been production-benchmarked.

## Current limitations

- E0-Core verifies the V3-B outbox/sender with the Coordinator through a local HTTP/SQLite flow, but
  whole active-session restart, physical Laptop hardware, and the later Pi storage port are not verified;
- V4 uses bounded whole-bundle multipart retry, not resumable chunk upload;
- no actual Raspberry Pi, STM, LAN, TLS, or deployment validation;
- no S1 run using the real PaddleOCR-VL GPU and Piper model in this implementation pass;
- no partial finalize, sequence replacement, or administration/garbage collection API.

The local fixture harness exists only to exercise the same verified-storage boundary in tests.

# Device Delivery V3-B

V3-B is the LAPTOP single-sender implementation of the existing `DeliveryPort`. It pins an
immutable Scanner V2 bundle in a SQLite outbox, streams it to Server V4, and reports ACK only after
the returned receipt matches the complete local delivery identity.

## Composition

V3-B reuses the C0 device ID, server origin, API-key file, and insecure-local-HTTP opt-in.

```python
from pathlib import Path

from asl_device.delivery_composition import build_laptop_delivery
from asl_device.delivery_config import DeviceDeliveryConfig

delivery = build_laptop_delivery(
    connectivity_config=connectivity_config,
    delivery_config=DeviceDeliveryConfig(
        outbox_db_path=Path("device-state/delivery.sqlite3"),
        artifact_root=Path("scanner-state/ready"),
    ),
    clock=clock,
)
```

The artifact root must contain Scanner-owned immutable directories in the form
`{artifact_root}/{artifact_id}/manifest.json`. The outbox database must be outside that root.

## Durable behavior

`queue()` validates the manifest, identity, readiness, exact file inventory, sizes, and SHA-256
values before committing a `queued` row. It performs no network call. Exact repeated queue calls
return the existing row; a different artifact at the same logical sequence is rejected.

`pending_status()` and `flush_through()` advance at most one oldest upload attempt per call. The
adapter is intentionally poll-driven and single-sender; it has no worker thread or lease.

```text
queued -> sending -> acked
                  -> retrying -> sending
                  -> rejected
```

On startup, an interrupted `sending` row becomes `retrying`. Retry preserves the exact scan,
sequence, artifact, canonical upload digest, and idempotency key.

## ACK rule

HTTP success alone is insufficient. The response must include `status=acked`, a non-empty receipt,
and exact matches for scan session, sequence, artifact, manifest SHA-256, and upload digest. A
malformed or mismatched success response raises a fatal port error while preserving the artifact
and a retryable outbox row.

The SQLite ACK is committed before source artifact cleanup. Cleanup failure does not revoke the
ACK. A deterministic non-retryable V4 rejection is stored as `rejected` and preserves the bundle
for diagnosis.

## Scope boundary

V3-B guarantees restart recovery after a successful `queue()` commit when the adapter is recreated
with the same database and artifact root. It does not restore the whole Coordinator active scan,
adopt artifacts created before `queue()` committed, persist the M1 accepted bank, run multiple
senders, implement generalized disk quota/retention, or deploy an external/Pi service. Those remain
separate E0 or hardening work.

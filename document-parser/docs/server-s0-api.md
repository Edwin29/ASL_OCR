# Server S0 persistent control plane

Server S0 is the SQLite-backed control plane used by the device coordinator. It owns catalog,
scan-session intent, and reading progress. Server S1 now supplies the internal verified-bundle,
Document Parser fragment, append, and immutable publish path described in `server-s1.md`. Public
artifact upload and the device durable outbox remain Server V4 work. During development the device
host and outbox run on a LAPTOP PC; the same contracts are later ported to Raspberry Pi.

## Startup

The combined server enables S0 automatically:

```powershell
python -m document_parser.server.combined_server `
  --api-key SECRET `
  --datapacks-dir D:\datapacks `
  --state-db D:\server-state\state.sqlite3 `
  ...
```

If `--state-db` is omitted, the default is `DATAPACKS_DIR/_server/state.sqlite3`. Startup validates
existing datapack directories and imports valid ones as READY revision 1. Invalid directories stay
untouched and are not added to the catalog. The SQLite database, rather than later directory
listings, is authoritative after reconciliation.

## HTTP contract

`GET /api/v1/health` is public. It identifies the service, supported API versions, process instance,
and SQLite schema version; it does not register a device. All other routes require `X-API-Key`.
Create/open mutations require `Idempotency-Key`; reading commands require `command_id` in the JSON
body or the header.

```text
GET  /api/v1/devices/{device_id}/datapacks
POST /api/v1/devices/{device_id}/presence-sessions
PUT  /api/v1/devices/{device_id}/presence-sessions/{presence_session_id}
DELETE /api/v1/devices/{device_id}/presence-sessions/{presence_session_id}
GET  /api/v1/devices/{device_id}/presence
GET  /api/v1/devices?limit=100
POST /api/v1/devices/{device_id}/datapacks
POST /api/v1/datapacks/{datapack_id}/scan-sessions
GET  /api/v1/scan-sessions/{scan_session_id}
POST /api/v1/scan-sessions/{scan_session_id}/seal-intent
POST /api/v1/reading-sessions
GET  /api/v1/reading-sessions/{reading_session_id}
POST /api/v1/reading-sessions/{reading_session_id}/commands
```

Errors use this shape:

```json
{"code":"...","message":"...","retryable":false,"details":{}}
```

Validation errors are 400, missing records 404, state/idempotency conflicts 409, and temporary
database failures 503. Bodies are limited to 64 KiB. Responses expose opaque audio references,
not local filesystem paths.

## Device Connectivity C0 presence

After public health compatibility succeeds, a device starts an authenticated presence session with
a stable provisioned `device_id`, a process-scoped `boot_id`, and a unique
`presence_session_id`. The start body is:

```json
{
  "presence_session_id": "presence-...",
  "boot_id": "process-...",
  "heartbeat_sequence": 0,
  "client_version": "0.1.0",
  "platform": "windows-laptop",
  "capabilities": ["scanner", "coordinator"]
}
```

Heartbeat uses a strictly increasing positive sequence and `connection_state: "online"`. An exact
replay is idempotent and does not extend `last_seen_at`; reusing a sequence with different content
conflicts. Graceful disconnect is idempotent. All presence timestamps and status projections use the
server clock.

The default projection is `online` through 45 seconds since last receipt, `stale` after 45 seconds,
and `offline` after 120 seconds or an explicit disconnect. These thresholds and the recommended
15-second heartbeat interval are server CLI settings. More than one online/stale session for one
device sets `split_brain_suspected=true`; it is diagnostic and does not silently choose a winner.

SQLite schema v3 stores presence sessions. Migration from a v2 database is forward-only and keeps
existing device and datapack records.

## Device adapters

Create one `S0HttpClient`, then inject the narrow wrappers into `DeviceFlowCoordinator`:

```python
client = S0HttpClient("http://server:8420", "SECRET")
catalog = S0CatalogHttpAdapter(client)
scans = S0ScanHttpAdapter(client)
reading = S0ReadingHttpAdapter(client)
```

Selection event IDs become stable create/open operation IDs. Reading button event IDs remain
command IDs, so a lost HTTP response can be retried without repeating navigation.

## S0 seal boundary

`seal-intent` durably records `through_sequence`, changes the scan to `sealing`, and changes the
datapack to `finalizing`. A repeated identical cutoff is a no-op; a different cutoff conflicts.
S0 never fabricates a READY revision. When the combined server configures S1, seal intent creates a
persistent finalize run; the Coordinator remains in finalization until S1 verifies fragments,
atomically publishes the revision, and returns READY.

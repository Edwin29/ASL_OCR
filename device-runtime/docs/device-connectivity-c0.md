# Device Connectivity C0

Device Connectivity C0 gates the application Coordinator on a configured ASL OCR server. During
prototype development, starting the Device Runtime process on the LAPTOP is the boot boundary. A
later Raspberry Pi adapter must retain the same configuration, state machine, and HTTP contract.

## Configuration

Keep the API key in a separate file beside the TOML configuration. Do not put it in the TOML or a
URL. Relative key paths are confined to the configuration directory.

```toml
schema_version = 1
device_id = "scanner-laptop-01"
server_base_url = "http://127.0.0.1:8420"
api_key_file = "api-key.txt"

# Prototype-only local HTTP. Production endpoints should use HTTPS.
allow_insecure_http = true

connect_timeout_seconds = 5.0
request_timeout_seconds = 10.0
heartbeat_interval_seconds = 15.0
stale_after_seconds = 45.0
offline_after_seconds = 120.0
retry_initial_seconds = 1.0
retry_max_seconds = 30.0
retry_jitter_fraction = 0.2
```

`ASL_DEVICE_ID`, `ASL_DEVICE_SERVER_URL`, and `ASL_DEVICE_API_KEY_FILE` override the corresponding
file values. The `device_id` is provisioned identity; it is not derived from an IP address, MAC
address, or host name. The server URL must be one HTTP(S) origin without credentials, a path, query,
or fragment. HTTP is rejected unless the prototype-only opt-in is explicit.

Build the LAPTOP implementation with:

```python
from pathlib import Path
from asl_device.connectivity_composition import build_laptop_connectivity

connectivity = build_laptop_connectivity(Path("device-connectivity.toml"), clock=clock)
coordinator = DeviceFlowCoordinator(..., connectivity=connectivity)
```

## Runtime contract

The poll-driven sequence is:

```text
load and validate configuration
  -> public GET /api/v1/health compatibility probe
  -> authenticated presence start
  -> ONLINE and Coordinator catalog load
  -> periodic authenticated heartbeat
```

Transport timeout, DNS/connection failure, HTTP 408/429, and 5xx responses enter bounded
exponential retry with jitter. Authentication failure and incompatible service/API/schema enter a
fatal state without retry. A connection loss freezes Scanner progress through the Coordinator gate;
recovery reuses the same presence session and server-accepted heartbeat sequence. Graceful process
stop performs best-effort disconnect.

Health does not prove authentication, register a device, acknowledge an upload, or finalize a
datapack. C0 also does not store Scanner artifacts. Durable upload, ACK, cache, duplicate-suppression
and resend semantics remain the Server V4 and Scanner outbox boundary.

## Prototype and production boundary

The verified C0 integration runs a real HTTP server on LAPTOP loopback, stops it, restarts it on the
same port and SQLite database, and observes session recovery. It does not establish a public fixed
DNS name, TLS certificate, VPN/tunnel, Windows auto-start, Raspberry Pi `systemd` unit, Wi-Fi/DNS
bootstrap, or captive-portal handling. Those deployment and Pi adapter checks must not be inferred
from the C0 result.

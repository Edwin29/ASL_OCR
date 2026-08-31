"""Persistent device presence sessions and server-clock status projection."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

from document_parser.server.s0_domain import (
    S0ConflictError,
    S0NotFoundError,
    S0ValidationError,
    require_id,
)
from document_parser.server.s0_store import S0Store


class DevicePresenceService:
    def __init__(
        self,
        store: S0Store,
        *,
        now: Callable[[], datetime] | None = None,
        heartbeat_interval_seconds: int = 15,
        stale_after_seconds: int = 45,
        offline_after_seconds: int = 120,
    ) -> None:
        if (
            isinstance(heartbeat_interval_seconds, bool)
            or not isinstance(heartbeat_interval_seconds, int)
            or heartbeat_interval_seconds <= 0
        ):
            raise ValueError("heartbeat_interval_seconds must be a positive integer")
        if (
            isinstance(stale_after_seconds, bool)
            or not isinstance(stale_after_seconds, int)
            or stale_after_seconds <= heartbeat_interval_seconds
        ):
            raise ValueError("stale_after_seconds must be greater than heartbeat_interval_seconds")
        if (
            isinstance(offline_after_seconds, bool)
            or not isinstance(offline_after_seconds, int)
            or offline_after_seconds <= stale_after_seconds
        ):
            raise ValueError("offline_after_seconds must be greater than stale_after_seconds")
        self.store = store
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.stale_after_seconds = stale_after_seconds
        self.offline_after_seconds = offline_after_seconds

    def start_session(self, device_id: str, payload: dict[str, Any]) -> dict[str, object]:
        device_id = require_id("device_id", device_id)
        normalized = _start_payload(payload)
        session_id = normalized["presence_session_id"]
        request_hash = _digest(normalized)
        heartbeat_hash = _digest(
            {
                "boot_id": normalized["boot_id"],
                "heartbeat_sequence": 0,
                "connection_state": "online",
            }
        )
        now = self._timestamp()
        with self.store.transaction() as connection:
            existing = connection.execute(
                """
                SELECT * FROM device_presence_sessions
                 WHERE device_id=? AND presence_session_id=?
                """,
                (device_id, session_id),
            ).fetchone()
            if existing is not None:
                if existing["request_sha256"] != request_hash:
                    raise S0ConflictError(
                        "PRESENCE_SESSION_COLLISION",
                        "presence session ID was already used with different start data",
                    )
                return self._session_response(existing, replayed=True)
            connection.execute(
                """
                INSERT INTO devices(device_id, first_seen_at, last_seen_at)
                VALUES (?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
                """,
                (device_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO device_presence_sessions(
                    device_id, presence_session_id, boot_id, request_sha256,
                    client_version, platform, capabilities_json, status,
                    last_heartbeat_sequence, last_heartbeat_sha256,
                    started_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?)
                """,
                (
                    device_id,
                    session_id,
                    normalized["boot_id"],
                    request_hash,
                    normalized["client_version"],
                    normalized["platform"],
                    _canonical(normalized["capabilities"]),
                    heartbeat_hash,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM device_presence_sessions
                 WHERE device_id=? AND presence_session_id=?
                """,
                (device_id, session_id),
            ).fetchone()
        return self._session_response(row, replayed=False)

    def heartbeat(
        self,
        device_id: str,
        presence_session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, object]:
        device_id = require_id("device_id", device_id)
        presence_session_id = require_id("presence_session_id", presence_session_id)
        normalized = _heartbeat_payload(payload)
        request_hash = _digest(normalized)
        now = self._timestamp()
        with self.store.transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM device_presence_sessions
                 WHERE device_id=? AND presence_session_id=?
                """,
                (device_id, presence_session_id),
            ).fetchone()
            if row is None:
                raise S0NotFoundError("PRESENCE_SESSION_NOT_FOUND", "unknown presence session")
            if row["status"] != "active":
                raise S0ConflictError("PRESENCE_SESSION_CLOSED", "presence session is disconnected")
            if row["boot_id"] != normalized["boot_id"]:
                raise S0ConflictError("PRESENCE_BOOT_ID_MISMATCH", "heartbeat boot ID differs")
            accepted = int(row["last_heartbeat_sequence"])
            incoming = normalized["heartbeat_sequence"]
            if incoming == accepted:
                if row["last_heartbeat_sha256"] != request_hash:
                    raise S0ConflictError(
                        "HEARTBEAT_SEQUENCE_COLLISION",
                        "heartbeat sequence was reused with different data",
                    )
                return self._session_response(row, replayed=True)
            if incoming < accepted:
                return self._session_response(row, replayed=True, stale_replay=True)
            connection.execute(
                """
                UPDATE device_presence_sessions
                   SET last_heartbeat_sequence=?, last_heartbeat_sha256=?, last_seen_at=?
                 WHERE device_id=? AND presence_session_id=? AND status='active'
                """,
                (incoming, request_hash, now, device_id, presence_session_id),
            )
            connection.execute(
                "UPDATE devices SET last_seen_at=? WHERE device_id=?",
                (now, device_id),
            )
            row = connection.execute(
                """
                SELECT * FROM device_presence_sessions
                 WHERE device_id=? AND presence_session_id=?
                """,
                (device_id, presence_session_id),
            ).fetchone()
        return self._session_response(row, replayed=False)

    def disconnect(self, device_id: str, presence_session_id: str) -> dict[str, object]:
        device_id = require_id("device_id", device_id)
        presence_session_id = require_id("presence_session_id", presence_session_id)
        now = self._timestamp()
        with self.store.transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM device_presence_sessions
                 WHERE device_id=? AND presence_session_id=?
                """,
                (device_id, presence_session_id),
            ).fetchone()
            if row is None:
                raise S0NotFoundError("PRESENCE_SESSION_NOT_FOUND", "unknown presence session")
            replayed = row["status"] == "disconnected"
            if row["status"] == "active":
                connection.execute(
                    """
                    UPDATE device_presence_sessions
                       SET status='disconnected', disconnected_at=?
                     WHERE device_id=? AND presence_session_id=?
                    """,
                    (now, device_id, presence_session_id),
                )
                row = connection.execute(
                    """
                    SELECT * FROM device_presence_sessions
                     WHERE device_id=? AND presence_session_id=?
                    """,
                    (device_id, presence_session_id),
                ).fetchone()
        return self._session_response(row, replayed=replayed)

    def get_device(self, device_id: str) -> dict[str, object]:
        device_id = require_id("device_id", device_id)
        with self.store.readonly() as connection:
            device = connection.execute(
                "SELECT * FROM devices WHERE device_id=?", (device_id,)
            ).fetchone()
            if device is None:
                raise S0NotFoundError("DEVICE_NOT_FOUND", "unknown device_id")
            sessions = connection.execute(
                """
                SELECT * FROM device_presence_sessions
                 WHERE device_id=? ORDER BY started_at DESC, presence_session_id
                 LIMIT 32
                """,
                (device_id,),
            ).fetchall()
        return self._device_response(device, sessions)

    def list_devices(self, *, limit: int = 100) -> tuple[dict[str, object], ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise S0ValidationError("DEVICE_LIMIT_INVALID", "limit must be between 1 and 500")
        with self.store.readonly() as connection:
            devices = connection.execute(
                "SELECT * FROM devices ORDER BY last_seen_at DESC, device_id LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for device in devices:
                sessions = connection.execute(
                    """
                    SELECT * FROM device_presence_sessions
                     WHERE device_id=? ORDER BY started_at DESC, presence_session_id
                     LIMIT 32
                    """,
                    (device["device_id"],),
                ).fetchall()
                result.append(self._device_response(device, sessions))
        return tuple(result)

    def _session_response(
        self,
        row: Any,
        *,
        replayed: bool,
        stale_replay: bool = False,
    ) -> dict[str, object]:
        return {
            "device_id": row["device_id"],
            "presence_session_id": row["presence_session_id"],
            "boot_id": row["boot_id"],
            "status": row["status"],
            "accepted_heartbeat_sequence": int(row["last_heartbeat_sequence"]),
            "started_at": row["started_at"],
            "last_seen_at": row["last_seen_at"],
            "disconnected_at": row["disconnected_at"],
            "server_time": self._timestamp(),
            "recommended_heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "replayed": replayed,
            "stale_replay": stale_replay,
        }

    def _device_response(self, device: Any, rows: Any) -> dict[str, object]:
        now = self._now().astimezone(timezone.utc)
        sessions = [self._project_session(row, now) for row in rows]
        live = [row for row in sessions if row["status"] in {"online", "stale"}]
        if any(row["status"] == "online" for row in sessions):
            status = "online"
        elif any(row["status"] == "stale" for row in sessions):
            status = "stale"
        else:
            status = "offline"
        return {
            "device_id": device["device_id"],
            "status": status,
            "first_seen_at": device["first_seen_at"],
            "last_seen_at": max(
                [device["last_seen_at"]] + [str(row["last_seen_at"]) for row in sessions]
            ),
            "active_session_count": len(live),
            "split_brain_suspected": len(live) > 1,
            "sessions": sessions,
        }

    def _project_session(self, row: Any, now: datetime) -> dict[str, object]:
        last_seen = _parse_timestamp(row["last_seen_at"])
        age = max(0.0, (now - last_seen).total_seconds())
        if row["status"] == "disconnected" or age > self.offline_after_seconds:
            status = "offline"
        elif age > self.stale_after_seconds:
            status = "stale"
        else:
            status = "online"
        return {
            "presence_session_id": row["presence_session_id"],
            "boot_id": row["boot_id"],
            "status": status,
            "client_version": row["client_version"],
            "platform": row["platform"],
            "capabilities": json.loads(row["capabilities_json"]),
            "last_heartbeat_sequence": int(row["last_heartbeat_sequence"]),
            "started_at": row["started_at"],
            "last_seen_at": row["last_seen_at"],
            "disconnected_at": row["disconnected_at"],
        }

    def _timestamp(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat(timespec="microseconds")


def _start_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise S0ValidationError("JSON_OBJECT_REQUIRED", "request body must be a JSON object")
    allowed = {
        "presence_session_id",
        "boot_id",
        "heartbeat_sequence",
        "client_version",
        "platform",
        "capabilities",
    }
    _reject_unknown(payload, allowed)
    session_id = require_id("presence_session_id", payload.get("presence_session_id"))
    boot_id = require_id("boot_id", payload.get("boot_id"))
    if payload.get("heartbeat_sequence") != 0:
        raise S0ValidationError("HEARTBEAT_SEQUENCE_INVALID", "start heartbeat_sequence must be 0")
    client_version = _bounded_text("client_version", payload.get("client_version"), 64)
    platform = _bounded_text("platform", payload.get("platform"), 64)
    capabilities = payload.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or len(capabilities) > 32
        or any(not isinstance(value, str) or not value or len(value) > 64 for value in capabilities)
        or len(set(capabilities)) != len(capabilities)
    ):
        raise S0ValidationError("CAPABILITIES_INVALID", "capabilities must be unique bounded strings")
    return {
        "presence_session_id": session_id,
        "boot_id": boot_id,
        "heartbeat_sequence": 0,
        "client_version": client_version,
        "platform": platform,
        "capabilities": sorted(capabilities),
    }


def _heartbeat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise S0ValidationError("JSON_OBJECT_REQUIRED", "request body must be a JSON object")
    _reject_unknown(payload, {"boot_id", "heartbeat_sequence", "connection_state"})
    boot_id = require_id("boot_id", payload.get("boot_id"))
    sequence = payload.get("heartbeat_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise S0ValidationError("HEARTBEAT_SEQUENCE_INVALID", "heartbeat_sequence must be positive")
    if payload.get("connection_state") != "online":
        raise S0ValidationError("CONNECTION_STATE_INVALID", "connection_state must be online")
    return {
        "boot_id": boot_id,
        "heartbeat_sequence": sequence,
        "connection_state": "online",
    }


def _reject_unknown(payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise S0ValidationError(
            "UNKNOWN_FIELD", "request contains unknown fields", {"fields": sorted(unknown)}
        )


def _bounded_text(name: str, value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise S0ValidationError(f"{name.upper()}_INVALID", f"{name} must be 1..{maximum} characters")
    return value


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise S0ValidationError("PRESENCE_TIMESTAMP_INVALID", "stored presence timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise S0ValidationError("PRESENCE_TIMESTAMP_INVALID", "stored presence timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)

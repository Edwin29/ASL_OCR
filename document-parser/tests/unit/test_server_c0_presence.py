from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from document_parser.server.c0_presence import DevicePresenceService
from document_parser.server.s0_domain import S0ConflictError
from document_parser.server.s0_http import create_app
from document_parser.server.s0_migrations import MIGRATIONS
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store


class MutableNow:
    def __init__(self):
        self.value = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def start_payload(session="presence-1", boot="boot-1"):
    return {
        "presence_session_id": session,
        "boot_id": boot,
        "heartbeat_sequence": 0,
        "client_version": "0.1.0",
        "platform": "windows-laptop",
        "capabilities": ["scanner", "coordinator"],
    }


class C0PresenceTests(unittest.TestCase):
    def make(self, root):
        store = S0Store(root / "state.sqlite3", root / "datapacks")
        now = MutableNow()
        return store, now, DevicePresenceService(store, now=now)

    def test_migration_v3_and_start_replay_are_persistent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, _now, service = self.make(root)
            first = service.start_session("device-1", start_payload())
            replay = DevicePresenceService(store).start_session("device-1", start_payload())
            self.assertEqual(first["presence_session_id"], replay["presence_session_id"])
            self.assertTrue(replay["replayed"])
            connection = sqlite3.connect(root / "state.sqlite3")
            try:
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                count = connection.execute("SELECT COUNT(*) FROM device_presence_sessions").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(version, 4)
            self.assertEqual(count, 1)
            with self.assertRaises(S0ConflictError):
                service.start_session("device-1", start_payload(boot="other-boot"))

    def test_existing_v2_database_migrates_forward_without_rebuild(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            root.mkdir(parents=True, exist_ok=True)
            database = root / "state.sqlite3"
            connection = sqlite3.connect(database)
            try:
                for version, sql in MIGRATIONS[:2]:
                    connection.executescript(sql)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 'earlier')",
                        (version,),
                    )
                connection.execute(
                    "INSERT INTO devices(device_id, first_seen_at, last_seen_at) VALUES ('existing-device', 'a', 'a')"
                )
                connection.commit()
            finally:
                connection.close()

            store = S0Store(database, root / "datapacks")
            with store.readonly() as migrated:
                self.assertEqual(
                    migrated.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
                    4,
                )
                self.assertIsNotNone(
                    migrated.execute("SELECT * FROM devices WHERE device_id='existing-device'").fetchone()
                )

    def test_heartbeat_replay_stale_and_collision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _store, now, service = self.make(Path(temp_dir))
            service.start_session("device-1", start_payload())
            now.advance(5)
            payload = {"boot_id": "boot-1", "heartbeat_sequence": 2, "connection_state": "online"}
            accepted = service.heartbeat("device-1", "presence-1", payload)
            replay = service.heartbeat("device-1", "presence-1", payload)
            stale = service.heartbeat(
                "device-1",
                "presence-1",
                {"boot_id": "boot-1", "heartbeat_sequence": 1, "connection_state": "online"},
            )
            self.assertEqual(accepted["accepted_heartbeat_sequence"], 2)
            self.assertTrue(replay["replayed"])
            self.assertTrue(stale["stale_replay"])
            with self.assertRaises(S0ConflictError):
                service.heartbeat(
                    "device-1",
                    "presence-1",
                    {"boot_id": "other-boot", "heartbeat_sequence": 2, "connection_state": "online"},
                )

    def test_server_clock_projects_online_stale_offline_and_split_brain(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _store, now, service = self.make(Path(temp_dir))
            service.start_session("device-1", start_payload("presence-1"))
            self.assertEqual(service.get_device("device-1")["status"], "online")
            service.start_session("device-1", start_payload("presence-2"))
            self.assertTrue(service.get_device("device-1")["split_brain_suspected"])
            now.advance(46)
            self.assertEqual(service.get_device("device-1")["status"], "stale")
            now.advance(75)
            view = service.get_device("device-1")
            self.assertEqual(view["status"], "offline")
            self.assertEqual(view["active_session_count"], 0)

    def test_disconnect_is_idempotent_and_closes_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _store, _now, service = self.make(Path(temp_dir))
            service.start_session("device-1", start_payload())
            first = service.disconnect("device-1", "presence-1")
            replay = service.disconnect("device-1", "presence-1")
            self.assertEqual(first["status"], "disconnected")
            self.assertTrue(replay["replayed"])
            with self.assertRaises(S0ConflictError):
                service.heartbeat(
                    "device-1",
                    "presence-1",
                    {"boot_id": "boot-1", "heartbeat_sequence": 1, "connection_state": "online"},
                )

    def test_http_health_presence_and_server_listing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, now, presence = self.make(root)
            app = create_app(S0ControlPlane(store), "secret", presence_service=presence)
            client = app.test_client()
            health = client.get("/api/v1/health")
            self.assertEqual(health.get_json()["service"], "asl-ocr-server")
            self.assertEqual(health.get_json()["schema_version"], 4)
            self.assertEqual(
                client.get("/api/v1/devices", headers={"X-API-Key": "secret"}).get_json()["devices"],
                [],
            )
            denied = client.post("/api/v1/devices/device-1/presence-sessions", json=start_payload())
            self.assertEqual(denied.status_code, 401)
            headers = {"X-API-Key": "secret"}
            started = client.post(
                "/api/v1/devices/device-1/presence-sessions", headers=headers, json=start_payload()
            )
            self.assertEqual(started.status_code, 201)
            now.advance(15)
            heartbeat = client.put(
                "/api/v1/devices/device-1/presence-sessions/presence-1",
                headers=headers,
                json={"boot_id": "boot-1", "heartbeat_sequence": 1, "connection_state": "online"},
            )
            self.assertEqual(heartbeat.get_json()["accepted_heartbeat_sequence"], 1)
            listed = client.get("/api/v1/devices", headers=headers).get_json()["devices"]
            self.assertEqual(listed[0]["device_id"], "device-1")
            self.assertEqual(listed[0]["status"], "online")


if __name__ == "__main__":
    unittest.main()

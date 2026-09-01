import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from dataclasses import replace
from pathlib import Path
from unittest import mock

from document_parser.server.s0_domain import S0ConflictError, S0TemporaryError
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_domain import S1Config
from document_parser.server.s1_services import S1Pipeline
from document_parser.server.v4_domain import (
    FileDeclaration,
    UploadMetadata,
    V4BundleRejectedError,
    V4CapacityError,
    V4Config,
    canonical_upload_digest,
    prepare_upload,
)
from document_parser.server.v4_upload import V4UploadService
from tests.unit.test_server_s1_ingest import FakeFragmentParser, sha, write_bundle


class TemporaryS1:
    def accept_verified_spread(self, _spread):
        raise S0TemporaryError("DATABASE_BUSY", "temporary database outage")


def upload_parts(bundle: Path, device_id: str, sequence: int = 1):
    manifest_path = bundle / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    declarations = tuple(
        FileDeclaration(item["path"], item["size_bytes"], item["sha256"])
        for item in manifest["files"]
    )
    metadata = UploadMetadata(
        device_id=device_id,
        sequence=sequence,
        artifact_id=manifest["artifact_id"],
        spread_id=manifest["spread_id"],
        source_frame_id=manifest["source_frame_id"],
        manifest_sha256=sha(manifest_path),
        file_count=len(declarations),
        total_file_bytes=sum(item.size_bytes for item in declarations),
    )
    metadata_bytes = json.dumps(
        {
            "schema_version": 1,
            "device_id": metadata.device_id,
            "sequence": metadata.sequence,
            "artifact_id": metadata.artifact_id,
            "spread_id": metadata.spread_id,
            "source_frame_id": metadata.source_frame_id,
            "manifest_sha256": metadata.manifest_sha256,
            "file_count": metadata.file_count,
            "total_file_bytes": metadata.total_file_bytes,
        },
        separators=(",", ":"),
    ).encode()
    digest = canonical_upload_digest(manifest["session_id"], metadata, declarations)
    files = [(item.path, io.BytesIO((bundle / item.path).read_bytes())) for item in declarations]
    return metadata_bytes, manifest_bytes, digest, files


def multipart_body(metadata: bytes, manifest: bytes, files, boundary="asl-v4-boundary", *, reverse=False):
    parts = []

    def field(name, body, filename=None, content_type="application/octet-stream"):
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f"{disposition}\r\n".encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                body,
                b"\r\n",
            ]
        )

    if reverse:
        field("manifest", manifest, "manifest.json", "application/json")
        field("metadata", metadata, content_type="application/json")
    else:
        field("metadata", metadata, content_type="application/json")
        field("manifest", manifest, "manifest.json", "application/json")
    for path, stream in files:
        field("bundle_file", stream.read(), path)
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


class V4UploadTests(unittest.TestCase):
    def make_stack(self, root: Path, *, s1=None, config_update=None):
        store = S0Store(root / "state.sqlite3", root / "datapacks")
        s0 = S0ControlPlane(store)
        s1_config = S1Config.under(store.datapacks_root)
        pipeline = s1 or S1Pipeline(store, s0, s1_config, FakeFragmentParser())
        config = V4Config.from_s1(s1_config)
        if config_update:
            config = replace(config, **config_update)
        service = V4UploadService(store, pipeline, config)
        return store, s0, pipeline, service

    def prepare_bundle(self, root: Path, s0: S0ControlPlane, *, artifact="artifact-1", sequence=1):
        datapack = s0.create_datapack("device-1", "create-1")
        scan = s0.open_scan("device-1", datapack.datapack_id, "open-1")
        bundle = root / f"bundle-{artifact}"
        write_bundle(bundle, scan.scan_session_id, artifact, f"spread-{sequence}", f"frame-{sequence}")
        return scan, bundle

    def send(self, service, scan, bundle, *, key="upload-1", sequence=1, files=None):
        metadata, manifest, digest, generated = upload_parts(bundle, "device-1", sequence)
        return service.accept_upload(
            scan_session_id=scan.scan_session_id,
            idempotency_key=key,
            upload_digest=digest,
            metadata_bytes=metadata,
            manifest_bytes=manifest,
            files=generated if files is None else files,
        )

    def test_migration_v4_is_applied_and_restart_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, _s0, _pipeline, _service = self.make_stack(root)
            with store.readonly() as connection:
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='spread_upload_attempts'"
                ).fetchone()
            self.assertEqual(version, 4)
            self.assertIsNotNone(table)
            S0Store(root / "state.sqlite3", root / "datapacks")

    def test_accept_promotes_server_bundle_and_returns_s1_receipt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)

            result = self.send(service, scan, bundle)

            self.assertEqual(result.http_status, 201)
            self.assertEqual(result.body["status"], "acked")
            rows = pipeline.list_spreads(scan.scan_session_id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["receipt_id"], result.body["receipt_id"])
            with store.readonly() as connection:
                attempt = connection.execute("SELECT * FROM spread_upload_attempts").fetchone()
            self.assertEqual(attempt["status"], "accepted")
            promoted = service.config.received_root / attempt["bundle_relative_path"]
            self.assertTrue((promoted / "manifest.json").is_file())

    def test_same_key_replays_stored_response_without_duplicate_fragments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            first = self.send(service, scan, bundle)
            replay = self.send(service, scan, bundle)

            self.assertTrue(replay.replayed)
            self.assertEqual(first.body, replay.body)
            self.assertEqual(len(pipeline.list_spreads(scan.scan_session_id)), 1)
            self.assertEqual(len(pipeline.list_spreads(scan.scan_session_id)[0]["fragments"]), 2)

    def test_different_key_exact_logical_replay_uses_existing_s1_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, _pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            first = self.send(service, scan, bundle, key="upload-1")
            received_before = sorted(service.config.received_root.rglob("manifest.json"))
            second = self.send(service, scan, bundle, key="upload-2")
            received_after = sorted(service.config.received_root.rglob("manifest.json"))

            self.assertEqual(second.http_status, 200)
            self.assertEqual(first.body["receipt_id"], second.body["receipt_id"])
            self.assertEqual(received_before, received_after)
            with store.readonly() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM spread_upload_attempts").fetchone()[0], 2)

    def test_same_key_with_different_logical_upload_is_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, _pipeline, service = self.make_stack(root)
            scan, first_bundle = self.prepare_bundle(root, s0)
            self.send(service, scan, first_bundle, key="upload-key")
            second_bundle = root / "bundle-artifact-2"
            write_bundle(second_bundle, scan.scan_session_id, "artifact-2", "spread-2", "frame-2")

            with self.assertRaisesRegex(S0ConflictError, "reused"):
                self.send(service, scan, second_bundle, key="upload-key", sequence=2)

    def test_hash_reject_is_journaled_and_exact_retry_replays_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, _pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            metadata, manifest, digest, files = upload_parts(bundle, "device-1")
            files[0] = (files[0][0], io.BytesIO(b"tampered"))
            with self.assertRaises(V4BundleRejectedError) as raised:
                service.accept_upload(
                    scan_session_id=scan.scan_session_id,
                    idempotency_key="bad-upload",
                    upload_digest=digest,
                    metadata_bytes=metadata,
                    manifest_bytes=manifest,
                    files=files,
                )
            self.assertEqual(raised.exception.http_status, 422)
            replay = self.send(service, scan, bundle, key="bad-upload")
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.http_status, 422)
            with store.readonly() as connection:
                row = connection.execute("SELECT * FROM spread_upload_attempts").fetchone()
            self.assertEqual(row["status"], "rejected")

    def test_promoted_upload_recovers_s1_handoff_after_temporary_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = S0Store(root / "state.sqlite3", root / "datapacks")
            s0 = S0ControlPlane(store)
            s1_config = S1Config.under(store.datapacks_root)
            service = V4UploadService(store, TemporaryS1(), V4Config.from_s1(s1_config))
            scan, bundle = self.prepare_bundle(root, s0)
            with self.assertRaises(S0TemporaryError):
                self.send(service, scan, bundle)
            with store.readonly() as connection:
                self.assertEqual(connection.execute("SELECT status FROM spread_upload_attempts").fetchone()[0], "promoted")

            pipeline = S1Pipeline(store, s0, s1_config, FakeFragmentParser())
            restarted = V4UploadService(store, pipeline, V4Config.from_s1(s1_config))
            recovered = restarted.recover()

            self.assertEqual(recovered["accepted"], 1)
            self.assertEqual(len(pipeline.list_spreads(scan.scan_session_id)), 1)

    def test_restart_recovers_directory_promoted_before_journal_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = S0Store(root / "state.sqlite3", root / "datapacks")
            s0 = S0ControlPlane(store)
            s1_config = S1Config.under(store.datapacks_root)
            service = V4UploadService(store, TemporaryS1(), V4Config.from_s1(s1_config))
            scan, bundle = self.prepare_bundle(root, s0)
            with self.assertRaises(S0TemporaryError):
                self.send(service, scan, bundle)
            with store.transaction() as connection:
                row = connection.execute("SELECT * FROM spread_upload_attempts").fetchone()
                connection.execute(
                    """
                    UPDATE spread_upload_attempts
                       SET status='receiving', staging_relative_path=?, bundle_relative_path=NULL,
                           lease_owner='dead-writer', lease_until='2999-01-01T00:00:00+00:00'
                     WHERE upload_id=?
                    """,
                    (f"{row['upload_id']}.partial", row["upload_id"]),
                )

            pipeline = S1Pipeline(store, s0, s1_config, FakeFragmentParser())
            restarted = V4UploadService(store, pipeline, V4Config.from_s1(s1_config))
            recovered = restarted.recover()

            self.assertEqual(recovered["accepted"], 1)
            self.assertEqual(len(pipeline.list_spreads(scan.scan_session_id)), 1)

    def test_valid_lease_is_preserved_and_expired_same_key_retries_immediately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, _pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            metadata, manifest, digest, files = upload_parts(bundle, "device-1")
            prepared = prepare_upload(scan.scan_session_id, metadata, manifest, digest, service.config)
            upload_id, staging = service._claim(prepared, "leased-upload")

            recovered = service.recover()

            self.assertEqual(recovered["abandoned"], 0)
            self.assertTrue(staging.is_dir())
            with store.readonly() as connection:
                status = connection.execute(
                    "SELECT status FROM spread_upload_attempts WHERE upload_id=?", (upload_id,)
                ).fetchone()[0]
            self.assertEqual(status, "receiving")
            with store.transaction() as connection:
                connection.execute(
                    "UPDATE spread_upload_attempts SET lease_until=? WHERE upload_id=?",
                    ("1970-01-01T00:00:00+00:00", upload_id),
                )

            result = service.accept_upload(
                scan_session_id=scan.scan_session_id,
                idempotency_key="leased-upload",
                upload_digest=digest,
                metadata_bytes=metadata,
                manifest_bytes=manifest,
                files=files,
            )

            self.assertEqual(result.http_status, 201)
            with store.readonly() as connection:
                row = connection.execute(
                    "SELECT status, attempt_count FROM spread_upload_attempts WHERE upload_id=?",
                    (upload_id,),
                ).fetchone()
            self.assertEqual((row["status"], row["attempt_count"]), ("accepted", 2))

    def test_sealing_only_accepts_upload_at_or_below_cutoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, _pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            s0.request_seal(scan.scan_session_id, 0)
            with self.assertRaisesRegex(S0ConflictError, "does not accept"):
                self.send(service, scan, bundle)

    def test_partial_orphan_cleanup_does_not_remove_referenced_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, _s0, _pipeline, service = self.make_stack(
                root, config_update={"partial_orphan_ttl_seconds": 1}
            )
            orphan = service.config.staging_root / "orphan.partial"
            orphan.mkdir()
            old = 1
            os.utime(orphan, (old, old))
            self.assertEqual(service.cleanup_partial_orphans(), 1)
            self.assertFalse(orphan.exists())

    def test_recovery_quarantines_untracked_final_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, _s0, _pipeline, service = self.make_stack(root)
            untracked = service.config.received_root / "v4" / ("upload-" + "a" * 32)
            untracked.mkdir(parents=True)
            (untracked / "diagnostic.bin").write_bytes(b"preserve")

            recovered = service.recover()

            quarantined = service.config.quarantine_root / untracked.name
            self.assertEqual(recovered["quarantined"], 1)
            self.assertFalse(untracked.exists())
            self.assertEqual((quarantined / "diagnostic.bin").read_bytes(), b"preserve")

    def test_staging_quota_rejects_before_writing_partial_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, _pipeline, service = self.make_stack(
                root, config_update={"max_staging_bytes": 1}
            )
            scan, bundle = self.prepare_bundle(root, s0)
            with self.assertRaises(V4CapacityError) as raised:
                self.send(service, scan, bundle)
            self.assertEqual(raised.exception.http_status, 507)
            self.assertEqual(list(service.config.staging_root.iterdir()), [])

    def test_staging_allocation_failure_abandons_claim_for_immediate_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, _pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)

            with mock.patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
                with self.assertRaises(S0TemporaryError):
                    self.send(service, scan, bundle)

            with store.readonly() as connection:
                attempt = connection.execute("SELECT * FROM spread_upload_attempts").fetchone()
            self.assertEqual(attempt["status"], "abandoned")
            self.assertIsNone(attempt["staging_relative_path"])

    def test_http_upload_and_idempotency_replay_header(self):
        from document_parser.server.s0_http import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            metadata, manifest, digest, files = upload_parts(bundle, "device-1")
            body, boundary = multipart_body(metadata, manifest, files)
            client = create_app(s0, "secret", pipeline, v4_service=service).test_client()
            headers = {
                "X-API-Key": "secret",
                "Idempotency-Key": "http-upload-1",
                "X-ASL-Upload-Digest": digest,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }

            first = client.post(f"/api/v1/scan-sessions/{scan.scan_session_id}/spreads", headers=headers, data=body)
            replay = client.post(f"/api/v1/scan-sessions/{scan.scan_session_id}/spreads", headers=headers, data=body)

            self.assertEqual(first.status_code, 201, first.get_json())
            self.assertEqual(first.get_json(), replay.get_json())
            self.assertEqual(replay.headers["Idempotency-Replayed"], "true")

    def test_http_rejects_wrong_part_order_before_upload_claim(self):
        from document_parser.server.s0_http import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            metadata, manifest, digest, files = upload_parts(bundle, "device-1")
            body, boundary = multipart_body(metadata, manifest, files, reverse=True)
            client = create_app(s0, "secret", pipeline, v4_service=service).test_client()
            response = client.post(
                f"/api/v1/scan-sessions/{scan.scan_session_id}/spreads",
                headers={
                    "X-API-Key": "secret",
                    "Idempotency-Key": "http-upload-1",
                    "X-ASL-Upload-Digest": digest,
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                data=body,
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["code"], "UPLOAD_PART_ORDER_INVALID")
            with store.readonly() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM spread_upload_attempts").fetchone()[0], 0)

    def test_http_auth_and_media_type_are_structured(self):
        from document_parser.server.s0_http import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, pipeline, service = self.make_stack(root)
            scan, _bundle = self.prepare_bundle(root, s0)
            client = create_app(s0, "secret", pipeline, v4_service=service).test_client()
            url = f"/api/v1/scan-sessions/{scan.scan_session_id}/spreads"
            unauthorized = client.post(url, data=b"x")
            unsupported = client.post(
                url,
                headers={
                    "X-API-Key": "secret",
                    "Idempotency-Key": "upload-1",
                    "X-ASL-Upload-Digest": "0" * 64,
                    "Content-Type": "application/octet-stream",
                },
                data=b"x",
            )
            self.assertEqual(unauthorized.status_code, 401)
            self.assertEqual(unsupported.status_code, 415)

    def test_http_retryable_capacity_error_has_retry_after(self):
        from document_parser.server.s0_http import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, pipeline, service = self.make_stack(
                root, config_update={"max_staging_bytes": 1}
            )
            scan, bundle = self.prepare_bundle(root, s0)
            metadata, manifest, digest, files = upload_parts(bundle, "device-1")
            body, boundary = multipart_body(metadata, manifest, files)
            client = create_app(s0, "secret", pipeline, v4_service=service).test_client()

            response = client.post(
                f"/api/v1/scan-sessions/{scan.scan_session_id}/spreads",
                headers={
                    "X-API-Key": "secret",
                    "Idempotency-Key": "quota-upload-1",
                    "X-ASL-Upload-Digest": digest,
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                data=body,
            )

            self.assertEqual(response.status_code, 507)
            self.assertEqual(response.headers["Retry-After"], "1")
            self.assertTrue(response.get_json()["retryable"])

    def test_actual_loopback_http_upload_returns_durable_receipt(self):
        from werkzeug.serving import make_server

        from document_parser.server.s0_http import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, pipeline, service = self.make_stack(root)
            scan, bundle = self.prepare_bundle(root, s0)
            metadata, manifest, digest, files = upload_parts(bundle, "device-1")
            body, boundary = multipart_body(metadata, manifest, files)
            app = create_app(s0, "secret", pipeline, v4_service=service)
            server = make_server("127.0.0.1", 0, app, threaded=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/v1/scan-sessions/{scan.scan_session_id}/spreads",
                    data=body,
                    method="POST",
                    headers={
                        "X-API-Key": "secret",
                        "Idempotency-Key": "loopback-upload-1",
                        "X-ASL-Upload-Digest": digest,
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                    },
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read())
                    status = response.status
            finally:
                server.shutdown()
                thread.join(timeout=5)

            self.assertEqual(status, 201)
            self.assertEqual(payload["status"], "acked")
            self.assertEqual(len(pipeline.list_spreads(scan.scan_session_id)), 1)


if __name__ == "__main__":
    unittest.main()

"""Forward-only SQLite migrations for the Server S0 control plane."""

from __future__ import annotations


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE devices (
            device_id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE datapacks (
            datapack_id TEXT PRIMARY KEY,
            storage_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','finalizing','ready','error')),
            current_revision INTEGER NULL CHECK(current_revision IS NULL OR current_revision >= 0),
            title_audio_ref TEXT NULL,
            created_by_device_id TEXT NULL REFERENCES devices(device_id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_code TEXT NULL,
            error_detail TEXT NULL
        );

        CREATE TABLE datapack_revisions (
            datapack_id TEXT NOT NULL REFERENCES datapacks(datapack_id),
            revision INTEGER NOT NULL CHECK(revision >= 0),
            status TEXT NOT NULL CHECK(status IN ('staging','ready','superseded','error')),
            root_relative_path TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            published_at TEXT NULL,
            PRIMARY KEY(datapack_id, revision)
        );

        CREATE TABLE scan_sessions (
            scan_session_id TEXT PRIMARY KEY,
            datapack_id TEXT NOT NULL REFERENCES datapacks(datapack_id),
            device_id TEXT NOT NULL REFERENCES devices(device_id),
            base_revision INTEGER NULL CHECK(base_revision IS NULL OR base_revision >= 0),
            status TEXT NOT NULL CHECK(status IN ('open','sealing','sealed','error')),
            through_sequence INTEGER NULL CHECK(through_sequence IS NULL OR through_sequence >= 0),
            open_operation_id TEXT NOT NULL,
            seal_operation_id TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_code TEXT NULL,
            error_detail TEXT NULL
        );

        CREATE UNIQUE INDEX one_active_scan_per_datapack
            ON scan_sessions(datapack_id)
            WHERE status IN ('open','sealing');

        CREATE TABLE reading_sessions (
            reading_session_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL REFERENCES devices(device_id),
            datapack_id TEXT NOT NULL REFERENCES datapacks(datapack_id),
            revision INTEGER NOT NULL CHECK(revision >= 0),
            viewport_size INTEGER NOT NULL CHECK(viewport_size > 0),
            status TEXT NOT NULL CHECK(status IN ('open','closed','error')),
            open_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE TABLE reading_progress (
            device_id TEXT NOT NULL REFERENCES devices(device_id),
            datapack_id TEXT NOT NULL REFERENCES datapacks(datapack_id),
            revision_seen INTEGER NOT NULL CHECK(revision_seen >= 0),
            cursor_json TEXT NOT NULL,
            cursor_version INTEGER NOT NULL CHECK(cursor_version > 0),
            updated_at TEXT NOT NULL,
            PRIMARY KEY(device_id, datapack_id)
        );

        CREATE TABLE command_receipts (
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(scope_type, scope_id, command_id)
        );

        CREATE INDEX catalog_order_idx ON datapacks(updated_at DESC, datapack_id ASC);
        CREATE INDEX reading_session_lookup_idx
            ON reading_sessions(device_id, datapack_id, revision, viewport_size, status);
        """,
    ),
    (
        2,
        """
        ALTER TABLE scan_sessions ADD COLUMN published_revision INTEGER NULL;
        ALTER TABLE scan_sessions ADD COLUMN finalize_run_id TEXT NULL;
        ALTER TABLE scan_sessions ADD COLUMN finalize_error_code TEXT NULL;
        ALTER TABLE scan_sessions ADD COLUMN finalize_error_detail TEXT NULL;
        ALTER TABLE scan_sessions ADD COLUMN finalize_started_at TEXT NULL;
        ALTER TABLE scan_sessions ADD COLUMN finalize_completed_at TEXT NULL;

        CREATE TABLE scan_spreads (
            scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
            sequence INTEGER NOT NULL CHECK(sequence > 0),
            artifact_id TEXT NOT NULL UNIQUE,
            spread_id TEXT NOT NULL,
            source_frame_id TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            bundle_relative_path TEXT NOT NULL,
            receipt_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('received','processing','ready','rejected','error')),
            received_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_code TEXT NULL,
            error_detail TEXT NULL,
            PRIMARY KEY(scan_session_id, sequence)
        );

        CREATE TABLE page_fragments (
            scan_session_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence > 0),
            side TEXT NOT NULL CHECK(side IN ('left','right')),
            page_id TEXT NOT NULL UNIQUE,
            image_relative_path TEXT NOT NULL,
            image_sha256 TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','processing','ready','rejected','error')),
            page_ir_relative_path TEXT NULL,
            accessible_page_relative_path TEXT NULL,
            parser_engine_json TEXT NULL,
            validation_json TEXT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
            lease_owner TEXT NULL,
            lease_until TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            terminal_at TEXT NULL,
            error_code TEXT NULL,
            error_detail TEXT NULL,
            PRIMARY KEY(scan_session_id, sequence, side),
            FOREIGN KEY(scan_session_id, sequence)
                REFERENCES scan_spreads(scan_session_id, sequence)
        );

        CREATE TABLE finalize_runs (
            finalize_run_id TEXT PRIMARY KEY,
            scan_session_id TEXT NOT NULL UNIQUE REFERENCES scan_sessions(scan_session_id),
            datapack_id TEXT NOT NULL REFERENCES datapacks(datapack_id),
            base_revision INTEGER NULL CHECK(base_revision IS NULL OR base_revision >= 0),
            target_revision INTEGER NULL CHECK(target_revision IS NULL OR target_revision > 0),
            through_sequence INTEGER NOT NULL CHECK(through_sequence >= 0),
            status TEXT NOT NULL CHECK(status IN ('waiting','assembling','validating','promoted','published','error')),
            staging_relative_path TEXT NULL,
            final_relative_path TEXT NULL,
            manifest_sha256 TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            published_at TEXT NULL,
            error_code TEXT NULL,
            error_detail TEXT NULL
        );

        CREATE INDEX fragment_claim_idx
            ON page_fragments(status, lease_until, created_at);
        CREATE INDEX spread_status_idx
            ON scan_spreads(scan_session_id, status, sequence);
        CREATE INDEX finalize_claim_idx
            ON finalize_runs(status, updated_at);
        """,
    ),
    (
        3,
        """
        CREATE TABLE device_presence_sessions (
            device_id TEXT NOT NULL REFERENCES devices(device_id),
            presence_session_id TEXT NOT NULL,
            boot_id TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,
            client_version TEXT NOT NULL,
            platform TEXT NOT NULL,
            capabilities_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','disconnected')),
            last_heartbeat_sequence INTEGER NOT NULL CHECK(last_heartbeat_sequence >= 0),
            last_heartbeat_sha256 TEXT NOT NULL,
            started_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            disconnected_at TEXT NULL,
            PRIMARY KEY(device_id, presence_session_id)
        );

        CREATE INDEX device_presence_status_idx
            ON device_presence_sessions(status, last_seen_at);
        CREATE INDEX device_presence_device_idx
            ON device_presence_sessions(device_id, status, last_seen_at);
        """,
    ),
)

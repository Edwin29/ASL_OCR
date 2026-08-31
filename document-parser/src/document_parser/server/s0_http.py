"""Versioned HTTP boundary for the persistent Server S0 control plane."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from document_parser.server.c0_presence import DevicePresenceService
from document_parser.server.s0_domain import S0Error, S0ValidationError
from document_parser.server.s0_services import S0ControlPlane


def register_routes(
    app: Any,
    control_plane: S0ControlPlane,
    api_key: str,
    s1_pipeline: Any | None = None,
    presence_service: DevicePresenceService | None = None,
) -> None:
    from flask import jsonify, request

    presence = presence_service or DevicePresenceService(control_plane.store)
    server_instance_id = f"server-{uuid.uuid4().hex}"

    def guarded(handler: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any):
            if request.headers.get("X-API-Key") != api_key:
                return jsonify(_error("UNAUTHORIZED", "missing or invalid X-API-Key header")), 401
            try:
                return handler(*args, **kwargs)
            except S0Error as exc:
                return jsonify(exc.to_dict()), exc.http_status

        wrapped.__name__ = f"s0_{handler.__name__}"
        return wrapped

    def json_body() -> dict[str, Any]:
        if (request.content_length or 0) > 64 * 1024 or len(request.get_data(cache=True)) > 64 * 1024:
            raise S0Error(
                "PAYLOAD_TOO_LARGE",
                "request body exceeds 65536 bytes",
                http_status=413,
            )
        if not request.is_json:
            raise S0ValidationError("JSON_REQUIRED", "request Content-Type must be application/json")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise S0ValidationError("JSON_OBJECT_REQUIRED", "request body must be a JSON object")
        return payload

    def idempotency_key() -> str:
        value = request.headers.get("Idempotency-Key")
        if not value:
            raise S0ValidationError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required")
        return value

    @app.get("/api/v1/health", endpoint="s0_health")
    def health():
        try:
            return jsonify(
                {
                    "status": "ok",
                    "service": "asl-ocr-server",
                    "api_versions": ["v1"],
                    "server_instance_id": server_instance_id,
                    **control_plane.store.health(),
                }
            )
        except S0Error as exc:
            return jsonify(
                {
                    "status": "degraded",
                    "service": "asl-ocr-server",
                    "api_versions": ["v1"],
                    "server_instance_id": server_instance_id,
                    **exc.to_dict(),
                }
            ), exc.http_status

    @app.post("/api/v1/devices/<device_id>/presence-sessions", endpoint="c0_presence_start")
    @guarded
    def start_presence(device_id: str):
        return jsonify(presence.start_session(device_id, json_body())), 201

    @app.put(
        "/api/v1/devices/<device_id>/presence-sessions/<presence_session_id>",
        endpoint="c0_presence_heartbeat",
    )
    @guarded
    def heartbeat_presence(device_id: str, presence_session_id: str):
        return jsonify(presence.heartbeat(device_id, presence_session_id, json_body()))

    @app.delete(
        "/api/v1/devices/<device_id>/presence-sessions/<presence_session_id>",
        endpoint="c0_presence_disconnect",
    )
    @guarded
    def disconnect_presence(device_id: str, presence_session_id: str):
        return jsonify(presence.disconnect(device_id, presence_session_id))

    @app.get("/api/v1/devices/<device_id>/presence", endpoint="c0_presence_get")
    @guarded
    def get_presence(device_id: str):
        return jsonify(presence.get_device(device_id))

    @app.get("/api/v1/devices", endpoint="c0_presence_list")
    @guarded
    def list_presence():
        raw_limit = request.args.get("limit", "100")
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise S0ValidationError("DEVICE_LIMIT_INVALID", "limit must be an integer") from exc
        return jsonify({"devices": list(presence.list_devices(limit=limit))})

    @app.get("/api/v1/devices/<device_id>/datapacks", endpoint="s0_catalog_list")
    @guarded
    def list_datapacks(device_id: str):
        return jsonify({"datapacks": [_catalog(row) for row in control_plane.list_datapacks(device_id)]})

    @app.post("/api/v1/devices/<device_id>/datapacks", endpoint="s0_catalog_create")
    @guarded
    def create_datapack(device_id: str):
        json_body()
        row = control_plane.create_datapack(device_id, idempotency_key())
        return jsonify(_catalog(row)), 201

    @app.post("/api/v1/datapacks/<datapack_id>/scan-sessions", endpoint="s0_scan_open")
    @guarded
    def open_scan(datapack_id: str):
        payload = json_body()
        row = control_plane.open_scan(payload.get("device_id"), datapack_id, idempotency_key())
        return jsonify(_scan(row)), 201

    @app.get("/api/v1/scan-sessions/<scan_session_id>", endpoint="s0_scan_get")
    @guarded
    def get_scan(scan_session_id: str):
        if s1_pipeline is not None:
            return jsonify(s1_pipeline.get_scan_view(scan_session_id))
        return jsonify(_scan(control_plane.get_scan(scan_session_id)))

    @app.get("/api/v1/scan-sessions/<scan_session_id>/spreads", endpoint="s1_spread_list")
    @guarded
    def list_spreads(scan_session_id: str):
        if s1_pipeline is None:
            raise S0Error("S1_NOT_CONFIGURED", "incremental pipeline is not configured", http_status=503, retryable=True)
        return jsonify({"spreads": list(s1_pipeline.list_spreads(scan_session_id))})

    @app.post("/api/v1/scan-sessions/<scan_session_id>/seal-intent", endpoint="s0_scan_seal")
    @guarded
    def seal_scan(scan_session_id: str):
        payload = json_body()
        if s1_pipeline is not None:
            return jsonify(s1_pipeline.request_seal(scan_session_id, payload.get("through_sequence"))), 202
        row = control_plane.request_seal(scan_session_id, payload.get("through_sequence"))
        return jsonify(_scan(row)), 202

    @app.post("/api/v1/reading-sessions", endpoint="s0_reading_open")
    @guarded
    def open_reading():
        payload = json_body()
        response = control_plane.open_reading(
            payload.get("device_id"),
            payload.get("datapack_id"),
            payload.get("viewport_size"),
            idempotency_key(),
        )
        return jsonify(response), 201

    @app.get("/api/v1/reading-sessions/<reading_session_id>", endpoint="s0_reading_get")
    @guarded
    def get_reading(reading_session_id: str):
        return jsonify(control_plane.get_reading(reading_session_id))

    @app.post("/api/v1/reading-sessions/<reading_session_id>/commands", endpoint="s0_reading_command")
    @guarded
    def reading_command(reading_session_id: str):
        payload = json_body()
        command_id = payload.get("command_id") or request.headers.get("Idempotency-Key")
        if not command_id:
            raise S0ValidationError("COMMAND_ID_REQUIRED", "command_id or Idempotency-Key is required")
        response = control_plane.send_reading_command(
            reading_session_id,
            command_id,
            payload.get("button"),
            payload.get("action", "SHORT"),
        )
        return jsonify(response)


def create_app(
    control_plane: S0ControlPlane,
    api_key: str,
    s1_pipeline: Any | None = None,
    presence_service: DevicePresenceService | None = None,
):
    from flask import Flask

    app = Flask(__name__)
    register_routes(app, control_plane, api_key, s1_pipeline, presence_service)
    return app


def _catalog(row: Any) -> dict[str, object]:
    return {
        "datapack_id": row.datapack_id,
        "title": row.title,
        "status": row.status.value,
        "revision": row.current_revision,
        "title_audio_ref": row.title_audio_ref,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _scan(row: Any) -> dict[str, object]:
    return {
        "scan_session_id": row.scan_session_id,
        "datapack_id": row.datapack_id,
        "device_id": row.device_id,
        "base_revision": row.base_revision,
        "status": row.status.value,
        "through_sequence": row.through_sequence,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _error(code: str, message: str) -> dict[str, object]:
    return {"code": code, "message": message, "retryable": False, "details": {}}

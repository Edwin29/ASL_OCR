"""Observable coordinator and semantic feedback events."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .types import DetailItems, DeviceFlowState, _freeze_details, _require_text


class CoordinatorEventType(str, Enum):
    STATE_CHANGED = "state_changed"
    CATALOG_LOADED = "catalog_loaded"
    CATALOG_HIGHLIGHT_CHANGED = "catalog_highlight_changed"
    OPERATING_MODE_CHANGED = "operating_mode_changed"
    DATAPACK_CREATED = "datapack_created"
    SCAN_SESSION_OPENED = "scan_session_opened"
    SCANNER_STARTED = "scanner_started"
    SCAN_INPUT_EXHAUSTED = "scan_input_exhausted"
    SPREAD_QUEUED = "spread_queued"
    SPREAD_DELIVERY_CONFIRMED = "spread_delivery_confirmed"
    SCAN_STOP_REQUESTED = "scan_stop_requested"
    UPLOAD_FLUSH_COMPLETED = "upload_flush_completed"
    DATAPACK_FINALIZING = "datapack_finalizing"
    DATAPACK_READY = "datapack_ready"
    READING_SESSION_OPENED = "reading_session_opened"
    READING_RESUMED = "reading_resumed"
    RETURNED_TO_SELECTION = "returned_to_selection"
    RECOVERABLE_ERROR = "recoverable_error"
    FATAL_ERROR = "fatal_error"
    SERVER_CONNECTING = "server_connecting"
    SERVER_ONLINE = "server_online"
    SERVER_CONNECTION_LOST = "server_connection_lost"
    SERVER_RETRY_SCHEDULED = "server_retry_scheduled"
    SERVER_RECOVERED = "server_recovered"


class FeedbackCode(str, Enum):
    SCREEN_CHANGED = "screen_changed"
    SPEAK_CATALOG_TITLE = "speak_catalog_title"
    OPERATING_MODE_CHANGED = "operating_mode_changed"
    NO_READABLE_DATAPACK = "no_readable_datapack"
    CONFIRM_SELECTION = "confirm_selection"
    SCAN_STARTED = "scan_started"
    CAMERA_OPENED = "camera_opened"
    SCANNER_GUIDANCE = "scanner_guidance"
    CANDIDATE_SELECTED = "candidate_selected"
    IDENTITY_COLLECTION_STARTED = "identity_collection_started"
    IDENTITY_COLLECTION_PROGRESS = "identity_collection_progress"
    IDENTITY_COLLECTION_DECIDED = "identity_collection_decided"
    IDENTITY_COLLECTION_ABORTED = "identity_collection_aborted"
    SCAN_INPUT_EXHAUSTED = "scan_input_exhausted"
    SPREAD_SENT = "spread_sent"
    SCAN_STOPPING = "scan_stopping"
    FINALIZING = "finalizing"
    DATAPACK_SAVED = "datapack_saved"
    SERVER_RETRYING = "server_retrying"
    SERVER_CONNECTING = "server_connecting"
    SERVER_CONNECTION_LOST = "server_connection_lost"
    SERVER_RECOVERED = "server_recovered"
    SERVER_AUTH_FAILED = "server_auth_failed"
    PARSER_REJECTED = "parser_rejected"
    READING_RESUMED = "reading_resumed"
    READING_AUDIO_FETCH_STARTED = "reading_audio_fetch_started"
    READING_AUDIO_CACHE_HIT = "reading_audio_cache_hit"
    READING_AUDIO_PLAYBACK_STARTED = "reading_audio_playback_started"
    READING_AUDIO_INTERRUPTED = "reading_audio_interrupted"
    READING_AUDIO_PLAYBACK_COMPLETED = "reading_audio_playback_completed"
    READING_AUDIO_FAILED = "reading_audio_failed"
    FATAL_ERROR = "fatal_error"


@dataclass(frozen=True, slots=True)
class CoordinatorEvent:
    event_id: str
    event_type: CoordinatorEventType
    at_monotonic: float
    state: DeviceFlowState
    details: DetailItems = ()

    def __post_init__(self) -> None:
        _require_text("coordinator event_id", self.event_id)
        if not isinstance(self.event_type, CoordinatorEventType):
            raise TypeError("event_type must be a CoordinatorEventType")
        if isinstance(self.at_monotonic, bool) or not isinstance(self.at_monotonic, (int, float)) or not math.isfinite(self.at_monotonic) or self.at_monotonic < 0:
            raise ValueError("at_monotonic must be finite and non-negative")
        if not isinstance(self.state, DeviceFlowState):
            raise TypeError("state must be a DeviceFlowState")
        object.__setattr__(self, "details", _freeze_details(self.details))


@dataclass(frozen=True, slots=True)
class FeedbackEvent:
    code: FeedbackCode
    at_monotonic: float
    details: DetailItems = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, FeedbackCode):
            raise TypeError("code must be a FeedbackCode")
        if isinstance(self.at_monotonic, bool) or not isinstance(self.at_monotonic, (int, float)) or not math.isfinite(self.at_monotonic) or self.at_monotonic < 0:
            raise ValueError("at_monotonic must be finite and non-negative")
        object.__setattr__(self, "details", _freeze_details(self.details))

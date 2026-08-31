"""Poll-driven startup handshake, heartbeat, and reconnect state machine."""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .connectivity_config import DeviceConnectivityConfig


class ConnectivityState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    PROBING = "probing"
    AUTHENTICATING = "authenticating"
    ONLINE = "online"
    RETRY_WAIT = "retry_wait"
    FATAL = "fatal"
    SHUTTING_DOWN = "shutting_down"


class ConnectivityEventType(str, Enum):
    CONNECTING = "connecting"
    SERVER_ONLINE = "server_online"
    SERVER_CONNECTION_LOST = "server_connection_lost"
    SERVER_RETRY_SCHEDULED = "server_retry_scheduled"
    SERVER_AUTH_FAILED = "server_auth_failed"
    SERVER_INCOMPATIBLE = "server_incompatible"
    SERVER_RECOVERED = "server_recovered"
    STOPPED = "stopped"


class RetryableConnectivityError(RuntimeError):
    pass


class FatalConnectivityError(RuntimeError):
    def __init__(self, message: str, *, code: str = "CONNECTIVITY_FATAL") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ConnectivityEvent:
    event_type: ConnectivityEventType
    at_monotonic: float
    detail: str | None = None
    retry_after_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ConnectivitySnapshot:
    state: ConnectivityState
    presence_session_id: str
    boot_id: str
    heartbeat_sequence: int
    retry_attempt: int
    next_action_at: float | None
    server_instance_id: str | None
    fatal_code: str | None = None

    @property
    def online(self) -> bool:
        return self.state is ConnectivityState.ONLINE


class MonotonicClock(Protocol):
    def monotonic(self) -> float: ...


class ConnectivityTransport(Protocol):
    def probe_health(self) -> dict[str, object]: ...

    def start_presence(
        self,
        *,
        device_id: str,
        presence_session_id: str,
        boot_id: str,
        client_version: str,
        platform: str,
        capabilities: tuple[str, ...],
    ) -> dict[str, object]: ...

    def heartbeat(
        self,
        *,
        device_id: str,
        presence_session_id: str,
        boot_id: str,
        sequence: int,
    ) -> dict[str, object]: ...

    def disconnect(self, *, device_id: str, presence_session_id: str) -> None: ...


class DeviceConnectivitySupervisor:
    def __init__(
        self,
        config: DeviceConnectivityConfig,
        transport: ConnectivityTransport,
        clock: MonotonicClock,
        *,
        presence_session_id: str | None = None,
        boot_id: str | None = None,
        client_version: str = "0.1.0",
        platform: str = "windows-laptop",
        capabilities: tuple[str, ...] = ("scanner", "coordinator"),
        random_unit: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self.clock = clock
        self.presence_session_id = presence_session_id or f"presence-{uuid.uuid4().hex}"
        self.boot_id = boot_id or f"process-{uuid.uuid4().hex}"
        self.client_version = client_version
        self.platform = platform
        self.capabilities = tuple(capabilities)
        self._random = random_unit or random.random
        self._state = ConnectivityState.STOPPED
        self._heartbeat_sequence = 0
        self._retry_attempt = 0
        self._next_action_at: float | None = None
        self._server_instance_id: str | None = None
        self._fatal_code: str | None = None
        self._was_online = False

    def start(self) -> tuple[ConnectivityEvent, ...]:
        if self._state is not ConnectivityState.STOPPED:
            raise RuntimeError(f"cannot start connectivity from {self._state.value}")
        now = self.clock.monotonic()
        self._state = ConnectivityState.STARTING
        self._next_action_at = now
        return (ConnectivityEvent(ConnectivityEventType.CONNECTING, now),)

    def poll(self) -> tuple[ConnectivityEvent, ...]:
        now = self.clock.monotonic()
        if self._state in {ConnectivityState.STOPPED, ConnectivityState.FATAL, ConnectivityState.SHUTTING_DOWN}:
            return ()
        if self._next_action_at is not None and now < self._next_action_at:
            return ()
        if self._state in {ConnectivityState.STARTING, ConnectivityState.RETRY_WAIT}:
            return self._connect(now)
        if self._state is ConnectivityState.ONLINE:
            return self._send_heartbeat(now)
        return ()

    def stop(self) -> tuple[ConnectivityEvent, ...]:
        if self._state is ConnectivityState.STOPPED:
            return ()
        now = self.clock.monotonic()
        self._state = ConnectivityState.SHUTTING_DOWN
        try:
            if self._was_online:
                self.transport.disconnect(
                    device_id=self.config.device_id.value,
                    presence_session_id=self.presence_session_id,
                )
        except Exception:
            pass
        self._state = ConnectivityState.STOPPED
        self._next_action_at = None
        return (ConnectivityEvent(ConnectivityEventType.STOPPED, now),)

    def current_status(self) -> ConnectivitySnapshot:
        return ConnectivitySnapshot(
            state=self._state,
            presence_session_id=self.presence_session_id,
            boot_id=self.boot_id,
            heartbeat_sequence=self._heartbeat_sequence,
            retry_attempt=self._retry_attempt,
            next_action_at=self._next_action_at,
            server_instance_id=self._server_instance_id,
            fatal_code=self._fatal_code,
        )

    def _connect(self, now: float) -> tuple[ConnectivityEvent, ...]:
        self._state = ConnectivityState.PROBING
        try:
            health = self.transport.probe_health()
            instance = health.get("server_instance_id")
            if not isinstance(instance, str) or not instance:
                raise FatalConnectivityError("server health lacks instance identity", code="SERVER_INCOMPATIBLE")
            self._server_instance_id = instance
            self._state = ConnectivityState.AUTHENTICATING
            response = self.transport.start_presence(
                device_id=self.config.device_id.value,
                presence_session_id=self.presence_session_id,
                boot_id=self.boot_id,
                client_version=self.client_version,
                platform=self.platform,
                capabilities=self.capabilities,
            )
            accepted = response.get("accepted_heartbeat_sequence")
            if response.get("status", "active") != "active":
                raise FatalConnectivityError("presence session is not active", code="SERVER_INCOMPATIBLE")
            if isinstance(accepted, bool) or not isinstance(accepted, int) or accepted < 0:
                raise FatalConnectivityError("presence start response is malformed", code="SERVER_INCOMPATIBLE")
        except RetryableConnectivityError as exc:
            return self._schedule_retry(now, str(exc), lost=self._was_online)
        except FatalConnectivityError as exc:
            self._state = ConnectivityState.FATAL
            self._next_action_at = None
            self._fatal_code = exc.code
            event_type = (
                ConnectivityEventType.SERVER_AUTH_FAILED
                if exc.code == "SERVER_AUTH_FAILED"
                else ConnectivityEventType.SERVER_INCOMPATIBLE
            )
            return (ConnectivityEvent(event_type, now, str(exc)),)
        recovered = self._was_online
        self._was_online = True
        self._state = ConnectivityState.ONLINE
        self._retry_attempt = 0
        self._heartbeat_sequence = accepted
        self._next_action_at = now + self.config.heartbeat_interval_seconds
        return (
            ConnectivityEvent(
                ConnectivityEventType.SERVER_RECOVERED if recovered else ConnectivityEventType.SERVER_ONLINE,
                now,
            ),
        )

    def _send_heartbeat(self, now: float) -> tuple[ConnectivityEvent, ...]:
        sequence = self._heartbeat_sequence + 1
        try:
            response = self.transport.heartbeat(
                device_id=self.config.device_id.value,
                presence_session_id=self.presence_session_id,
                boot_id=self.boot_id,
                sequence=sequence,
            )
            if response.get("accepted_heartbeat_sequence") != sequence:
                raise FatalConnectivityError("heartbeat response is malformed", code="SERVER_INCOMPATIBLE")
        except RetryableConnectivityError as exc:
            return self._schedule_retry(now, str(exc), lost=True)
        except FatalConnectivityError as exc:
            self._state = ConnectivityState.FATAL
            self._next_action_at = None
            self._fatal_code = exc.code
            event_type = (
                ConnectivityEventType.SERVER_AUTH_FAILED
                if exc.code == "SERVER_AUTH_FAILED"
                else ConnectivityEventType.SERVER_INCOMPATIBLE
            )
            return (ConnectivityEvent(event_type, now, str(exc)),)
        self._heartbeat_sequence = sequence
        self._retry_attempt = 0
        self._next_action_at = now + self.config.heartbeat_interval_seconds
        return ()

    def _schedule_retry(self, now: float, detail: str, *, lost: bool) -> tuple[ConnectivityEvent, ...]:
        base = min(
            self.config.retry_max_seconds,
            self.config.retry_initial_seconds * (2 ** self._retry_attempt),
        )
        random_value = self._random()
        if not isinstance(random_value, (int, float)) or not math.isfinite(random_value) or not 0 <= random_value <= 1:
            raise ValueError("random_unit must return a finite value in [0, 1]")
        factor = 1 + ((2 * float(random_value)) - 1) * self.config.retry_jitter_fraction
        delay = max(0.001, base * factor)
        self._retry_attempt += 1
        self._state = ConnectivityState.RETRY_WAIT
        self._next_action_at = now + delay
        events: list[ConnectivityEvent] = []
        if lost:
            events.append(ConnectivityEvent(ConnectivityEventType.SERVER_CONNECTION_LOST, now, detail))
        events.append(
            ConnectivityEvent(
                ConnectivityEventType.SERVER_RETRY_SCHEDULED,
                now,
                detail,
                retry_after_seconds=delay,
            )
        )
        return tuple(events)

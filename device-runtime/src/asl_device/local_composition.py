"""E0-Core composition root for the current local development host."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .adapters.book_scanner_runtime import BookScannerEngineFactory, BookScannerRuntimeAdapter
from .adapters.http_connectivity import HttpConnectivityTransport
from .adapters.http_s0 import (
    S0CatalogHttpAdapter,
    S0HttpClient,
    S0ReadingHttpAdapter,
    S0ScanHttpAdapter,
)
from .adapters.http_v4 import V4HttpClient
from .adapters.local_controls import ConsoleControlSource, ControlSource
from .adapters.local_feedback import (
    CompositeFeedbackSink,
    JsonLineFeedbackSink,
    JsonLineReadingPresenter,
    WindowsAudioFeedbackSink,
)
from .adapters.reading_audio import (
    S0AudioResourceHttpAdapter,
    S0SystemAudioResourceHttpAdapter,
    SoundDeviceWavPlayer,
)
from .adapters.stm_serial import StmSerialControlSource
from .app_config import DeviceAppConfig, ScannerHostConfig
from .application import DeviceApplication, ReadingPresenter
from .connectivity import DeviceConnectivitySupervisor
from .coordinator import DeviceFlowCoordinator
from .delivery import DurableDeliveryPort
from .delivery_store import DeliveryStore
from .protocols import Clock, FeedbackSink
from .reading_audio import AudioResourceCache, ReadingAudioController
from .types import DeviceOperatingMode


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(frozen=True, slots=True)
class LocalDeviceComposition:
    config: DeviceAppConfig
    application: DeviceApplication
    coordinator: DeviceFlowCoordinator
    scanner: BookScannerRuntimeAdapter
    delivery: DurableDeliveryPort
    reading_audio: ReadingAudioController | None = None


def build_local_device(
    config_path: str | Path,
    *,
    scanner_factory: BookScannerEngineFactory | None = None,
    controls: ControlSource | None = None,
    presenter: ReadingPresenter | None = None,
    feedback: FeedbackSink | None = None,
    clock: Clock | None = None,
    initial_mode: DeviceOperatingMode = DeviceOperatingMode.CAPTURE,
) -> LocalDeviceComposition:
    config = DeviceAppConfig.from_toml(config_path)
    clock_value = clock or SystemClock()
    api_key = config.connectivity.load_api_key()
    connectivity_transport = HttpConnectivityTransport(
        config.connectivity.server_base_url,
        api_key,
        timeout_seconds=config.connectivity.request_timeout_seconds,
        health_timeout_seconds=config.connectivity.connect_timeout_seconds,
    )
    capabilities = ["scanner", "coordinator", "durable_upload"]
    if config.controls_mode == "stm_serial":
        capabilities.extend(("stm_serial", "braille_display"))
    if config.feedback_mode == "windows_audio":
        capabilities.append("audio_feedback")
    if config.reading_audio.enabled:
        capabilities.extend(("reading_audio", "piper_system_audio"))
    connectivity = DeviceConnectivitySupervisor(
        config.connectivity,
        connectivity_transport,
        clock_value,
        platform="windows-device-host",
        capabilities=tuple(capabilities),
    )
    s0_client = S0HttpClient(
        config.connectivity.server_base_url,
        api_key,
        timeout_seconds=config.connectivity.request_timeout_seconds,
    )
    delivery_store = DeliveryStore(config.delivery.outbox_db_path)
    delivery_transport = V4HttpClient(
        config.connectivity.server_base_url,
        api_key,
        config.delivery,
        allow_insecure_http=config.connectivity.allow_insecure_http,
    )
    delivery = DurableDeliveryPort(
        config.connectivity.device_id,
        config.delivery,
        delivery_store,
        delivery_transport,
        clock_value.monotonic,
    )
    factory = scanner_factory or _default_scanner_factory(config.scanner)
    scanner = BookScannerRuntimeAdapter(factory, config.delivery.artifact_root)
    base_feedback = feedback if feedback is not None else _default_feedback(config)
    feedback_sink = base_feedback
    reading_audio = None
    if config.reading_audio.enabled:
        reading_audio = ReadingAudioController(
            S0AudioResourceHttpAdapter(
                config.connectivity.server_base_url,
                api_key,
                timeout_seconds=config.reading_audio.request_timeout_seconds,
                max_resource_bytes=config.reading_audio.max_resource_bytes,
                chunk_bytes=config.reading_audio.download_chunk_bytes,
            ),
            SoundDeviceWavPlayer(),
            AudioResourceCache(
                max_bytes=config.reading_audio.max_cache_bytes,
                max_entries=config.reading_audio.max_cache_entries,
            ),
            device_id=config.connectivity.device_id,
            system_resource_port=S0SystemAudioResourceHttpAdapter(
                config.connectivity.server_base_url,
                api_key,
                timeout_seconds=config.reading_audio.request_timeout_seconds,
                max_resource_bytes=config.reading_audio.max_resource_bytes,
                chunk_bytes=config.reading_audio.download_chunk_bytes,
            ),
            feedback=base_feedback,
            monotonic=clock_value.monotonic,
        )
        feedback_sink = CompositeFeedbackSink(base_feedback, reading_audio)
    controls_value = controls
    presenter_value = presenter
    default_console = controls_value is None and config.controls_mode == "console"
    if controls_value is None:
        if config.controls_mode == "stm_serial":
            assert config.stm_serial is not None
            stm = StmSerialControlSource(config.stm_serial)
            controls_value = stm
            if presenter_value is None:
                presenter_value = stm
        else:
            controls_value = ConsoleControlSource(event_namespace=connectivity.boot_id)
    if presenter_value is None and default_console and config.feedback_mode == "jsonl":
        presenter_value = JsonLineReadingPresenter()
    coordinator = DeviceFlowCoordinator(
        device_id=config.connectivity.device_id,
        viewport_size=config.viewport_size,
        clock=clock_value,
        catalog_port=S0CatalogHttpAdapter(s0_client),
        scan_session_port=S0ScanHttpAdapter(s0_client),
        scanner=scanner,
        delivery=delivery,
        reading=S0ReadingHttpAdapter(s0_client),
        feedback=feedback_sink,
        connectivity=connectivity,
        initial_mode=initial_mode,
    )
    application = DeviceApplication(
        coordinator,
        controls_value,
        poll_interval_seconds=config.poll_interval_ms / 1000.0,
        presenter=presenter_value,
        audio_presenter=reading_audio,
        closeables=(feedback_sink,),
    )
    return LocalDeviceComposition(
        config, application, coordinator, scanner, delivery, reading_audio
    )


def _default_feedback(config: DeviceAppConfig) -> FeedbackSink:
    if config.feedback_mode == "windows_audio":
        return WindowsAudioFeedbackSink(config.laptop_audio)
    return JsonLineFeedbackSink()


def _default_scanner_factory(config: ScannerHostConfig) -> BookScannerEngineFactory:
    try:
        from book_scanner.video.runtime_composition import (
            LocalBookScannerEngineFactory,
            LocalScannerRuntimeConfig,
        )
    except ImportError as exc:
        raise RuntimeError(
            "book-scanner must be installed beside asl-device-runtime for E0 local composition"
        ) from exc
    return LocalBookScannerEngineFactory(
        LocalScannerRuntimeConfig(
            profile=config.profile,
            staging_root=config.staging_root,
            ready_root=config.ready_root,
            uvdoc_runtime_path=config.uvdoc_runtime_path,
            uvdoc_checkpoint_path=config.uvdoc_checkpoint_path,
            uvdoc_device=config.uvdoc_device,
            m1_model_dir=config.m1_model_dir,
            m1_model_manifest=config.m1_model_manifest,
            replay_path=config.replay_path,
            image_paths=config.image_paths,
            camera_index=config.camera_index,
            camera_width=config.camera_width,
            camera_height=config.camera_height,
            camera_fps=config.camera_fps,
            camera_selector=config.camera_selector,
            camera_backend=config.camera_backend,
            camera_fallback_index=config.camera_fallback_index,
            camera_fourcc=config.camera_fourcc,
            camera_rotation=config.camera_rotation,
            camera_mirror=config.camera_mirror,
            camera_warmup_frames=config.camera_warmup_frames,
            camera_reopen_attempts=config.camera_reopen_attempts,
            camera_reopen_initial_ms=config.camera_reopen_initial_ms,
            operator_preview_enabled=config.operator_preview_enabled,
            operator_preview_max_width=config.operator_preview_max_width,
            sample_interval_ms=config.sample_interval_ms,
            opaque_identity_max_collection_ms=config.opaque_identity_max_collection_ms,
        )
    )

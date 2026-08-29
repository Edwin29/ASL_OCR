#!/usr/bin/env python3
"""Keep Raspberry Pi CPU and memory utilization in a bounded target band."""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


LOG = logging.getLogger("raspberry-pi-load")


@dataclass(frozen=True)
class Settings:
    cpu_target: float = 84.0
    memory_target: float = 84.0
    upper_limit: float = 89.0
    temperature_limit: float = 80.0
    interval: float = 1.0
    memory_chunk_mb: int = 8
    minimum_available_mb: int = 256

    def validate(self) -> None:
        for name, value in (
            ("cpu_target", self.cpu_target),
            ("memory_target", self.memory_target),
            ("upper_limit", self.upper_limit),
        ):
            if not 0 < value < 100:
                raise ValueError(f"{name} must be between 0 and 100")
        if self.cpu_target >= self.upper_limit or self.memory_target >= self.upper_limit:
            raise ValueError("targets must be below upper_limit")
        if self.upper_limit > 89.0:
            raise ValueError("upper_limit cannot exceed 89 percent")
        if self.interval < 0.2:
            raise ValueError("interval must be at least 0.2 seconds")
        if self.memory_chunk_mb < 1 or self.minimum_available_mb < 128:
            raise ValueError("unsafe memory settings")


def read_cpu_times() -> tuple[int, int]:
    fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()[1:]
    values = [int(value) for value in fields]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def cpu_percent(previous: tuple[int, int], current: tuple[int, int]) -> float:
    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    if total_delta <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta))


def read_memory() -> tuple[int, int, float]:
    info: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        key, value = line.split(":", 1)
        info[key] = int(value.split()[0]) * 1024
    total = info["MemTotal"]
    available = info["MemAvailable"]
    used_percent = 100.0 * (total - available) / total
    return total, available, used_percent


def read_temperature() -> float | None:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return int(path.read_text(encoding="ascii").strip()) / 1000.0
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def cpu_worker(duty: mp.sharedctypes.Synchronized, stop: mp.synchronize.Event) -> None:
    period = 0.1
    while not stop.is_set():
        cycle_start = time.monotonic()
        busy_for = period * max(0.0, min(1.0, duty.value))
        while time.monotonic() - cycle_start < busy_for:
            # Integer arithmetic gives repeatable load without allocating memory.
            _ = 317 * 331
        remaining = period - (time.monotonic() - cycle_start)
        if remaining > 0:
            stop.wait(remaining)


class LoadController:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stop = mp.Event()
        self.duty = mp.Value("d", 0.10, lock=True)
        self.workers: list[mp.Process] = []
        self.memory_blocks: list[bytearray] = []
        self.memory_lock = threading.Lock()
        self.memory_thread: threading.Thread | None = None

    def start(self) -> None:
        core_count = os.cpu_count() or 1
        self.workers = [
            mp.Process(target=cpu_worker, args=(self.duty, self.stop), daemon=True)
            for _ in range(core_count)
        ]
        for worker in self.workers:
            worker.start()
        self.memory_thread = threading.Thread(target=self._memory_loop, daemon=True)
        self.memory_thread.start()
        LOG.info("started with %d CPU workers", core_count)
        self._cpu_loop()

    def shutdown(self) -> None:
        if self.stop.is_set():
            return
        self.stop.set()
        with self.duty.get_lock():
            self.duty.value = 0.0
        if self.memory_thread:
            self.memory_thread.join(timeout=3)
        with self.memory_lock:
            self.memory_blocks.clear()
        for worker in self.workers:
            worker.join(timeout=2)
            if worker.is_alive():
                worker.terminate()
        LOG.info("stopped and released allocated memory")

    def _cpu_loop(self) -> None:
        previous = read_cpu_times()
        while not self.stop.wait(self.settings.interval):
            current = read_cpu_times()
            measured = cpu_percent(previous, current)
            previous = current
            temperature = read_temperature()

            with self.duty.get_lock():
                if measured >= self.settings.upper_limit:
                    self.duty.value = max(0.0, self.duty.value - 0.20)
                elif temperature is not None and temperature >= self.settings.temperature_limit:
                    self.duty.value = max(0.0, self.duty.value - 0.15)
                else:
                    error = self.settings.cpu_target - measured
                    self.duty.value = max(0.0, min(0.95, self.duty.value + error * 0.008))
                duty = self.duty.value

            _, available, memory = read_memory()
            LOG.info(
                "cpu=%.1f%% memory=%.1f%% available=%dMiB temp=%s duty=%.2f",
                measured,
                memory,
                available // (1024 * 1024),
                "n/a" if temperature is None else f"{temperature:.1f}C",
                duty,
            )

    def _memory_loop(self) -> None:
        chunk_size = self.settings.memory_chunk_mb * 1024 * 1024
        reserve = self.settings.minimum_available_mb * 1024 * 1024
        while not self.stop.wait(self.settings.interval):
            _, available, measured = read_memory()
            with self.memory_lock:
                if measured >= self.settings.upper_limit or available <= reserve:
                    release_count = min(4, len(self.memory_blocks))
                    if release_count:
                        del self.memory_blocks[-release_count:]
                    continue
                if measured < self.settings.memory_target - 0.5 and available > reserve + chunk_size:
                    try:
                        block = bytearray(chunk_size)
                        # Touch every page so Linux commits physical memory.
                        for offset in range(0, chunk_size, 4096):
                            block[offset] = 1
                        self.memory_blocks.append(block)
                    except MemoryError:
                        LOG.warning("memory allocation refused; backing off")
                        if self.memory_blocks:
                            self.memory_blocks.pop()
                elif measured > self.settings.memory_target + 1.0 and self.memory_blocks:
                    self.memory_blocks.pop()


def parse_args() -> Settings:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-target", type=float, default=84.0)
    parser.add_argument("--memory-target", type=float, default=84.0)
    parser.add_argument("--upper-limit", type=float, default=89.0)
    parser.add_argument("--temperature-limit", type=float, default=80.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--memory-chunk-mb", type=int, default=8)
    parser.add_argument("--minimum-available-mb", type=int, default=256)
    args = parser.parse_args()
    settings = Settings(**vars(args))
    settings.validate()
    return settings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        settings = parse_args()
    except ValueError as exc:
        LOG.error("invalid configuration: %s", exc)
        return 2

    controller = LoadController(settings)

    def handle_signal(_signum: int, _frame: object) -> None:
        controller.shutdown()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        controller.start()
    finally:
        controller.shutdown()
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())

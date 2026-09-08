"""Compile exact RX ring/drain functions from main.c with deterministic stubs."""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[3]
MAIN = ROOT / "hardware/stm32/kitel2026final/Core/Src/main.c"
OUT = ROOT / "docs/evidence/h23-1c-20260908/rx-ring-fixture"


def extract_function(source: str, name: str) -> str:
    match = re.search(
        rf"^static [^\n]+ {re.escape(name)}\([^;]*\)\n\{{",
        source,
        flags=re.MULTILINE,
    )
    if match is None:
        raise RuntimeError(f"definition not found for {name}")
    start = match.start()
    brace = source.index("{", match.start())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise RuntimeError(f"unterminated function {name}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    functions = "\n\n".join(
        extract_function(source, name)
        for name in (
            "BluetoothRxPushToken",
            "BluetoothRxQueueResync",
            "BluetoothRxHandleByte",
            "PumpBluetoothInput",
        )
    )
    fixture = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>

#define BT_RX_LINE_SIZE 256U
#define BT_RX_RING_SIZE 1024U
#define BT_RX_RESYNC_TOKEN 0x100U
#define __DMB() ((void)0)

static char bt_rx_line[BT_RX_LINE_SIZE];
static uint16_t bt_rx_line_length;
static uint8_t bt_rx_discarding;
static volatile uint16_t bt_rx_ring[BT_RX_RING_SIZE];
static volatile uint16_t bt_rx_ring_head;
static volatile uint16_t bt_rx_ring_tail;
static volatile uint8_t bt_rx_drop_until_newline;
static volatile uint8_t bt_rx_resync_pending;
static volatile uint32_t bt_rx_overrun_errors;
static volatile uint32_t bt_rx_frame_errors;
static volatile uint32_t bt_rx_noise_errors;
static volatile uint32_t bt_rx_parity_errors;
static volatile uint32_t bt_rx_ring_overflows;
static char accepted[4][256];
static unsigned accepted_count;
static unsigned transport_reports;

static void ProcessHostLine(char *line) {
    if (accepted_count < 4U) strcpy(accepted[accepted_count++], line);
}
static void Debug_Print(const char *text) {(void)text;}
static void Debug_Printf(const char *fmt, ...) {
    (void)fmt;
    transport_reports++;
}
''' + functions + r'''

static void feed(const char *text, uint32_t error_at) {
    uint32_t index = 0U;
    while (*text) {
        BluetoothRxHandleByte((uint8_t)*text++, index == error_at ? 1U : 0U);
        index++;
    }
}
static void drain(void) {
    unsigned guard = 10000U;
    while (bt_rx_ring_tail != bt_rx_ring_head && guard-- > 0U)
        PumpBluetoothInput();
}
static void reset_all(void) {
    memset((void *)bt_rx_ring, 0, sizeof(bt_rx_ring));
    memset(bt_rx_line, 0, sizeof(bt_rx_line));
    memset(accepted, 0, sizeof(accepted));
    bt_rx_line_length = 0U;
    bt_rx_discarding = 0U;
    bt_rx_ring_head = bt_rx_ring_tail = 0U;
    bt_rx_drop_until_newline = bt_rx_resync_pending = 0U;
    bt_rx_ring_overflows = 0U;
    accepted_count = transport_reports = 0U;
}
int main(void) {
    unsigned i;
    reset_all();
    feed("ACK,1\nFRAME,0,1,0,0,7,1,2,3,4,5,6,7,8,9,10\n", UINT32_MAX);
    drain();
    if (accepted_count != 2U || strcmp(accepted[0], "ACK,1") ||
        strcmp(accepted[1], "FRAME,0,1,0,0,7,1,2,3,4,5,6,7,8,9,10")) return 1;

    reset_all();
    feed("FRAME,BROKEN", 5U);
    feed(",SUFFIX\nACK,9\n", UINT32_MAX);
    drain();
    if (accepted_count != 1U || strcmp(accepted[0], "ACK,9") || transport_reports != 1U) return 2;

    reset_all();
    for (i = 0U; i < BT_RX_RING_SIZE; i++) BluetoothRxHandleByte('X', 0U);
    BluetoothRxHandleByte('\n', 0U);
    drain();
    feed("ACK,10\n", UINT32_MAX);
    drain();
    if (bt_rx_ring_overflows != 1U || accepted_count != 1U ||
        strcmp(accepted[0], "ACK,10") || transport_reports != 1U) return 3;

    puts("rx_ring_fixture_pass");
    return 0;
}
'''
    OUT.mkdir(parents=True, exist_ok=True)
    c_path = OUT / "fixture.c"
    exe_path = OUT / "fixture.exe"
    c_path.write_text(fixture, encoding="utf-8", newline="\n")
    compiler = pathlib.Path(
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.43.34808\bin\Hostx64\x64\cl.exe"
    )
    vcvars = pathlib.Path(
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
    )
    setup = subprocess.run(
        f'cmd /d /s /c "call "{vcvars}" >nul && set"',
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    environment = os.environ.copy()
    for line in setup.stdout.splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            environment[key] = value
    compile_result = subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/W4",
            "/WX",
            "/D_CRT_SECURE_NO_WARNINGS",
            str(c_path),
            f"/Fe:{exe_path}",
        ],
        cwd=OUT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    run_result = None
    if compile_result.returncode == 0:
        run_result = subprocess.run(
            [str(exe_path)],
            cwd=OUT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    result = {
        "source": str(MAIN),
        "compiler": str(compiler),
        "compile_exit_code": compile_result.returncode,
        "compile_stdout": compile_result.stdout,
        "compile_stderr": compile_result.stderr,
        "run_exit_code": None if run_result is None else run_result.returncode,
        "run_stdout": None if run_result is None else run_result.stdout,
        "run_stderr": None if run_result is None else run_result.stderr,
        "cases": ["queued_order", "uart_error_resync", "ring_overflow_resync"],
    }
    (OUT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if compile_result.returncode != 0 or run_result is None or run_result.returncode != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

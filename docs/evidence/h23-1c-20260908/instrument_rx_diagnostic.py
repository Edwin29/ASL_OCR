from __future__ import annotations

import pathlib
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: instrument_rx_diagnostic.py <main.c>")

    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "static uint16_t bt_rx_line_length = 0U;\n",
        """static uint16_t bt_rx_line_length = 0U;

/* Diagnostic-only counters. This isolated evidence build does not change
 * protocol, buffering, UART ownership, or actuator configuration. */
static uint32_t diag_rx_bytes = 0U;
static uint32_t diag_rx_lines = 0U;
static uint32_t diag_rx_ore = 0U;
static uint32_t diag_rx_fe = 0U;
static uint32_t diag_rx_ne = 0U;
static uint32_t diag_rx_hal_errors = 0U;
static uint32_t diag_frame_format_errors = 0U;
static uint32_t diag_line_overflows = 0U;
static uint32_t diag_last_pump_at = 0U;
static uint32_t diag_max_pump_gap_ms = 0U;
static uint32_t diag_last_apply_ms = 0U;
static uint32_t diag_max_apply_ms = 0U;
""",
        "counter globals",
    )

    text = replace_once(
        text,
        """    last_frame_apply_ok = ApplyBrailleFrame(current_cells);
    if (last_frame_apply_ok)
        last_applied_generation = nav_state.generation;
""",
        """    {
        uint32_t apply_started_at = HAL_GetTick();
        last_frame_apply_ok = ApplyBrailleFrame(current_cells);
        diag_last_apply_ms = HAL_GetTick() - apply_started_at;
        if (diag_last_apply_ms > diag_max_apply_ms)
            diag_max_apply_ms = diag_last_apply_ms;
    }
    if (last_frame_apply_ok)
        last_applied_generation = nav_state.generation;
""",
        "apply duration",
    )

    text = replace_once(
        text,
        """        if (!ParseAndApplyFrame(line))
            Debug_Print("FRAME FORMAT ERROR\\r\\n");
""",
        """        if (!ParseAndApplyFrame(line))
        {
            diag_frame_format_errors++;
            Debug_Print("FRAME FORMAT ERROR\\r\\n");
        }
""",
        "frame format counter",
    )

    text = replace_once(
        text,
        """static void PumpBluetoothInput(void)
{
    uint8_t ch;
    uint8_t processed = 0U;

    while (processed < 64U)
    {
        HAL_StatusTypeDef status = HAL_UART_Receive(&huart1, &ch, 1U, 1U);
""",
        """static void PumpBluetoothInput(void)
{
    uint8_t ch;
    uint8_t processed = 0U;
    uint32_t now = HAL_GetTick();

    if (diag_last_pump_at != 0U)
    {
        uint32_t gap = now - diag_last_pump_at;
        if (gap > diag_max_pump_gap_ms)
            diag_max_pump_gap_ms = gap;
    }
    diag_last_pump_at = now;

    while (processed < 64U)
    {
        uint32_t status_register = huart1.Instance->SR;
        HAL_StatusTypeDef status;
        if ((status_register & USART_SR_ORE) != 0U)
            diag_rx_ore++;
        if ((status_register & USART_SR_FE) != 0U)
            diag_rx_fe++;
        if ((status_register & USART_SR_NE) != 0U)
            diag_rx_ne++;
        status = HAL_UART_Receive(&huart1, &ch, 1U, 1U);
""",
        "pump entry and status sampling",
    )

    text = replace_once(
        text,
        """        if (status != HAL_OK)
        {
            bt_connected = 0U;
""",
        """        if (status != HAL_OK)
        {
            diag_rx_hal_errors++;
            bt_connected = 0U;
""",
        "HAL error counter",
    )

    text = replace_once(
        text,
        """        processed++;
        if (ch == '\\r')
""",
        """        processed++;
        diag_rx_bytes++;
        if (ch == '\\r')
""",
        "byte counter",
    )

    text = replace_once(
        text,
        """        if (ch == '\\n')
        {
            bt_rx_line[bt_rx_line_length] = '\\0';
            if (!bt_rx_discarding)
                ProcessHostLine(bt_rx_line);
            bt_rx_line_length = 0U;
            bt_rx_discarding = 0U;
            continue;
        }
""",
        """        if (ch == '\\n')
        {
            bt_rx_line[bt_rx_line_length] = '\\0';
            diag_rx_lines++;
            if (!bt_rx_discarding)
                ProcessHostLine(bt_rx_line);
            Debug_Printf(
                "RXSTAT bytes=%lu lines=%lu ore=%lu fe=%lu ne=%lu hal=%lu fmt=%lu ovf=%lu gap=%lu apply=%lu maxapply=%lu\\r\\n",
                (unsigned long)diag_rx_bytes,
                (unsigned long)diag_rx_lines,
                (unsigned long)diag_rx_ore,
                (unsigned long)diag_rx_fe,
                (unsigned long)diag_rx_ne,
                (unsigned long)diag_rx_hal_errors,
                (unsigned long)diag_frame_format_errors,
                (unsigned long)diag_line_overflows,
                (unsigned long)diag_max_pump_gap_ms,
                (unsigned long)diag_last_apply_ms,
                (unsigned long)diag_max_apply_ms);
            bt_rx_line_length = 0U;
            bt_rx_discarding = 0U;
            continue;
        }
""",
        "line summary",
    )

    text = replace_once(
        text,
        """            bt_rx_line_length = 0U;
            bt_rx_discarding = 1U;
            Debug_Print("BT RX LINE TOO LONG\\r\\n");
""",
        """            bt_rx_line_length = 0U;
            bt_rx_discarding = 1U;
            diag_line_overflows++;
            Debug_Print("BT RX LINE TOO LONG\\r\\n");
""",
        "overflow counter",
    )

    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

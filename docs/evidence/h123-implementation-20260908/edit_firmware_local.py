"""Only parser/line recovery and bus-result bookkeeping; no RX IRQ/LUT/pin changes."""
from pathlib import Path
p=Path(__file__).resolve().parents[3]/'hardware/stm32/kitel2026final/Core/Src/main.c'
s=p.read_text(encoding='utf-8')
s=s.replace('#include <stdlib.h>','#include <stdlib.h>\n#include <errno.h>')
s=s.replace('static uint8_t current_motor_state[MOTOR_COUNT];','''static uint8_t current_motor_state[MOTOR_COUNT];
/* Requested FRAME acceptance is distinct from successful PCA bus application.
 * Volatile counters are observable in a debugger without adding UART traffic. */
static volatile uint8_t last_frame_apply_ok = 0U;
static volatile uint32_t pca_apply_failures = 0U;
static volatile uint32_t last_applied_generation = 0U;
static uint8_t bt_rx_discarding = 0U;''')
s=s.replace('static void ApplyBrailleFrame(', 'static uint8_t ApplyBrailleFrame(')
start=s.index('static uint8_t ApplyBrailleFrame(const uint8_t cells[BRAILLE_CELL_COUNT])\n{')
end=s.index('\n/* ===',start)
part=s[start:end].replace('    uint8_t changed = 0U;', '    uint8_t changed = 0U;\n    uint8_t applied = 1U;')
for motor,state in [('top_motor','top_state'),('bottom_motor','bottom_state')]:
    target=f'                current_motor_state[{motor}] = {state};'
    assert target in part
    part=part.replace(target,target+'\n            else\n            {\n                applied = 0U;\n                pca_apply_failures++;\n            }')
idx=part.rfind('}')
part=part[:idx]+'    return applied;\n'+part[idx:]
s=s[:start]+part+s[end:]
start=s.index('static uint8_t ParseAndApplyFrame(char *line)\n{')
end=s.index('\n/* ===',start)
s=s[:start]+r'''static uint8_t ParseAndApplyFrame(char *line)
{
    char *cursor;
    unsigned long values[5U + BRAILLE_CELL_COUNT];
    uint8_t i;

    if (line == NULL || strncmp(line, "FRAME,", 6U) != 0)
        return 0U;
    cursor = line + 6U;
    for (i = 0U; i < (5U + BRAILLE_CELL_COUNT); i++)
    {
        char *end_ptr;
        if (*cursor < '0' || *cursor > '9')
            return 0U;
        errno = 0;
        values[i] = strtoul(cursor, &end_ptr, 10);
        if (errno == ERANGE || end_ptr == cursor)
            return 0U;
        if (i + 1U < (5U + BRAILLE_CELL_COUNT))
        {
            if (*end_ptr != ',')
                return 0U;
            cursor = end_ptr + 1;
        }
        else if (*end_ptr != '\0')
            return 0U;
    }
    if (values[0] > UINT16_MAX || values[1] > UINT16_MAX ||
        values[2] > UINT16_MAX || values[3] > UINT16_MAX || values[4] > UINT32_MAX)
        return 0U;
    /* Validate all fields before committing requested state or touching PCA. */
    for (i = 0U; i < BRAILLE_CELL_COUNT; i++)
        if (values[5U + i] > 63U)
            return 0U;

    nav_state.page = (uint16_t)values[0];
    nav_state.node = (uint16_t)values[1];
    nav_state.span = (uint16_t)values[2];
    nav_state.offset = (uint16_t)values[3];
    nav_state.generation = (uint32_t)values[4];
    for (i = 0U; i < BRAILLE_CELL_COUNT; i++)
        current_cells[i] = (uint8_t)values[5U + i];

    last_frame_apply_ok = ApplyBrailleFrame(current_cells);
    if (last_frame_apply_ok)
        last_applied_generation = nav_state.generation;
    ShowCurrentState();
    return 1U;
}
'''.replace("'\\0'", "'\0'")+s[end:]
# Above Python replacement must leave textual C backslash-zero, never a NUL.
s=s.replace("'\x00'", "'\\0'")
at=s.index('static void ResetControlTransport(void)\n{')
end=s.index('\nstatic uint8_t QueueControlAction',at)
part=s[at:end].replace('    bt_rx_line_length = 0U;', '    bt_rx_line_length = 0U;\n    bt_rx_discarding = 0U;')
s=s[:at]+part+s[end:]
at=s.index('static void PumpBluetoothInput(void)\n{')
end=s.index('\n/* Keep legacy',at)
part=s[at:end].replace('            ProcessHostLine(bt_rx_line);','            if (!bt_rx_discarding)\n                ProcessHostLine(bt_rx_line);')
part=part.replace('            bt_rx_line_length = 0U;\n            continue;', '            bt_rx_line_length = 0U;\n            bt_rx_discarding = 0U;\n            continue;',1)
part=part.replace('        if (bt_rx_line_length >=', '        if (bt_rx_discarding)\n            continue;\n        if (bt_rx_line_length >=',1)
part=part.replace('            Debug_Print("BT RX LINE TOO LONG', '            bt_rx_discarding = 1U;\n            Debug_Print("BT RX LINE TOO LONG',1)
s=s[:at]+part+s[end:]
assert '\x00' not in s
p.write_text(s,encoding='utf-8')

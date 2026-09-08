
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
static uint8_t BluetoothRxPushToken(uint16_t token)
{
    uint16_t next = (uint16_t)(bt_rx_ring_head + 1U);

    if (next >= BT_RX_RING_SIZE)
        next = 0U;
    if (next == bt_rx_ring_tail)
        return 0U;
    bt_rx_ring[bt_rx_ring_head] = token;
    __DMB();
    bt_rx_ring_head = next;
    return 1U;
}

static void BluetoothRxQueueResync(void)
{
    if (!BluetoothRxPushToken(BT_RX_RESYNC_TOKEN))
        bt_rx_resync_pending = 1U;
}

static void BluetoothRxHandleByte(uint8_t ch, uint32_t errors)
{
    if (bt_rx_resync_pending)
    {
        if (!BluetoothRxPushToken(BT_RX_RESYNC_TOKEN))
        {
            bt_rx_drop_until_newline = 1U;
            return;
        }
        bt_rx_resync_pending = 0U;
    }

    if (bt_rx_drop_until_newline)
    {
        if (ch == '\n')
        {
            bt_rx_drop_until_newline = 0U;
            BluetoothRxQueueResync();
        }
        return;
    }

    if (errors != 0U)
    {
        bt_rx_drop_until_newline = 1U;
        if (ch == '\n')
        {
            bt_rx_drop_until_newline = 0U;
            BluetoothRxQueueResync();
        }
        return;
    }

    if (!BluetoothRxPushToken((uint16_t)ch))
    {
        bt_rx_ring_overflows++;
        bt_rx_drop_until_newline = 1U;
        if (ch == '\n')
        {
            bt_rx_drop_until_newline = 0U;
            BluetoothRxQueueResync();
        }
    }
}

static void PumpBluetoothInput(void)
{
    uint16_t token;
    uint8_t processed = 0U;

    while (processed < 64U)
    {
        uint16_t tail = bt_rx_ring_tail;
        uint16_t next;

        if (tail == bt_rx_ring_head)
            break;
        token = bt_rx_ring[tail];
        next = (uint16_t)(tail + 1U);
        if (next >= BT_RX_RING_SIZE)
            next = 0U;
        __DMB();
        bt_rx_ring_tail = next;
        processed++;
        if (token == BT_RX_RESYNC_TOKEN)
        {
            bt_rx_line_length = 0U;
            bt_rx_discarding = 0U;
            Debug_Printf(
                "BT RX TRANSPORT ERROR ORE=%lu FE=%lu NE=%lu PE=%lu OVF=%lu\r\n",
                (unsigned long)bt_rx_overrun_errors,
                (unsigned long)bt_rx_frame_errors,
                (unsigned long)bt_rx_noise_errors,
                (unsigned long)bt_rx_parity_errors,
                (unsigned long)bt_rx_ring_overflows);
            continue;
        }
        {
            uint8_t ch = (uint8_t)token;
            if (ch == '\r')
                continue;
            if (ch == '\n')
            {
                bt_rx_line[bt_rx_line_length] = '\0';
                if (!bt_rx_discarding)
                    ProcessHostLine(bt_rx_line);
                bt_rx_line_length = 0U;
                bt_rx_discarding = 0U;
                continue;
            }
            if (bt_rx_discarding)
                continue;
            if (bt_rx_line_length >= (BT_RX_LINE_SIZE - 1U))
            {
                bt_rx_line_length = 0U;
                bt_rx_discarding = 1U;
                Debug_Print("BT RX LINE TOO LONG\r\n");
                continue;
            }
            bt_rx_line[bt_rx_line_length++] = (char)ch;
        }
    }
}

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

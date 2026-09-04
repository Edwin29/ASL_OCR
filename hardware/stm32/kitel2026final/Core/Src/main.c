#include "main.h"

#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stdlib.h>

/* ============================================================
 * FINAL HARDWARE - ST MORPHO MALE PINS ONLY
 *
 * NUCLEO-F446RE의 수핀 헤더(ST Morpho CN7/CN10)만 외부 배선에 사용.
 * Arduino 암헤더(A0/A1/A2/A3, D핀)는 외부 배선에 사용하지 않음.
 *
 * [CN10 - male]
 * CN10-3  = PB8  = I2C1_SCL  -> PCA9685 #1/#2 SCL
 * CN10-5  = PB9  = I2C1_SDA  -> PCA9685 #1/#2 SDA
 * CN10-21 = PA9  = USART1_TX -> HC-05 RXD
 * CN10-24 = PB1  = PAGE NEXT button
 * CN10-33 = PA10 = USART1_RX <- HC-05 TXD
 *
 * [CN7 - male]
 * CN7-28 = PA0 = UP button
 * CN7-30 = PA1 = DOWN button
 * CN7-32 = PA4 = LEFT button
 * CN7-34 = PB0 = RIGHT button
 *
 * Additional active-low inputs (verify physical Morpho header positions
 * against the NUCLEO-F446RE board schematic before wiring):
 * PC0 = PAGE PREVIOUS, PC1 = CONFIRM, PC2 = MODE LEVER
 *
 * Power examples on male Morpho header:
 * CN7-16 = +3.3V
 * CN7-18 = +5V
 * CN7-8 / 19 / 20 / 22 = GND
 * CN10-9 / 20 = GND
 *
 * Tera Term debug = USART2 / ST-LINK VCP
 * PA2/PA3 are still configured for USART2, but no external jumper is needed.
 * ============================================================ */

/* HC-05 data-mode UART baud.
 * Most unmodified HC-05 breakout modules use 9600 baud in data mode.
 * If your module was configured to another baud, change only this value.
 */
#define HC05_UART_BAUD          9600U

#define DEBUG_UART_BAUD         115200U

/* Retry Raspberry Pi / Bluetooth handshake when disconnected. */
#define BT_RETRY_MS             2000U
#define FRAME_TIMEOUT_MS        5000U
#define VERSIONED_HANDSHAKE_TIMEOUT_MS 1200U
#define ACK_TIMEOUT_MS          500U
#define ACK_RETRY_LIMIT         3U
#define CONTROL_QUEUE_CAPACITY  16U
#define BT_RX_LINE_SIZE         256U

/* ============================================================
 * Peripheral handles
 * ============================================================ */
I2C_HandleTypeDef hi2c1;
UART_HandleTypeDef huart1;      /* HC-05 */
UART_HandleTypeDef huart2;      /* Tera Term */

/* ============================================================
 * PCA9685
 * ============================================================ */
#define PCA1_ADDR               (0x40U << 1)
#define PCA2_ADDR               (0x41U << 1)

#define PCA_MODE1               0x00U
#define PCA_MODE2               0x01U
#define PCA_LED0_ON_L           0x06U
#define PCA_PRESCALE            0xFEU

#define PCA_MODE1_SLEEP         0x10U
#define PCA_MODE1_AI            0x20U
#define PCA_MODE2_OUTDRV        0x04U

/* ============================================================
 * Servo / Braille display
 *
 * NEW PCA WIRING
 * PCA #1 (0x40) CH0~CH9 = TOP motors, Cell 1~10
 * PCA #2 (0x41) CH0~CH9 = BOTTOM motors, Cell 1~10
 * ============================================================ */
#define MOTOR_COUNT             20U
#define BRAILLE_CELL_COUNT      10U

#define SERVO_FREQ_HZ           50U
#define SERVO_MIN_US            700U
#define SERVO_MAX_US            2300U

/* Move changed servos in small groups to reduce peak current. */
#define SERVO_BATCH_SIZE        4U
#define SERVO_BATCH_DELAY_MS    100U

/*
 * 3-bit mechanical pattern -> servo state.
 *
 * 000 -> state 0 ->   0 deg
 * 001 -> state 1 ->  22.5 deg
 * ...
 * 111 -> state 7 -> 157.5 deg
 *
 * If the physical octagonal cams are mounted in a different order,
 * modify only this table.
 */
static const uint8_t SERVO_STATE_LUT[8] =
{
    0U, 1U, 2U, 3U,
    4U, 5U, 6U, 7U
};

/*
 * IMPORTANT: the bottom motor is physically below dots 4,5,6.
 *
 * Braille cell numbering:
 *
 *   1 4
 *   2 5
 *   3 6
 *
 * Left motor is above dots 1,2,3:
 *   001 -> dot1 (nearest)
 *   010 -> dot2
 *   100 -> dot3
 *
 * Bottom motor is below dots 4,5,6:
 *   001 -> dot6 (nearest)
 *   010 -> dot5
 *   100 -> dot4
 *
 * GitHub encodes the bottom/right side in dot4,dot5,dot6 order, therefore
 * the 3 bits must be reversed before converting to a servo state.
 */
static const uint8_t BOTTOM_REVERSE_LUT[8] =
{
    0U, 4U, 2U, 6U,
    1U, 5U, 3U, 7U
};

/* ============================================================
 * Buttons - ST Morpho MALE header only
 *
 * CN7-28 / PA0 = UP
 * CN7-30 / PA1 = DOWN
 * CN7-32 / PA4 = LEFT
 * CN7-34 / PB0 = RIGHT
 * CN10-24 / PB1 = PAGE NEXT
 * PC0 = PAGE PREVIOUS
 * PC1 = CONFIRM
 * PC2 = MODE LEVER (LOW=capture, HIGH=reading)
 *
 * GPIO Input + Pull-up.
 * Each button connects GPIO <-> switch <-> GND.
 *
 * Key-repeat behavior:
 *   - debounced press: one immediate step
 *   - keep holding >= BUTTON_REPEAT_DELAY_MS:
 *       repeat every BUTTON_REPEAT_INTERVAL_MS
 *   - release: stop immediately
 *
 * NOTE:
 * Navigation/page LONG commands are intentionally not used. Their long hold
 * means auto-repeat SHORT steps. CONFIRM alone emits one LONG on release.
 * ============================================================ */
#define BUTTON_DEBOUNCE_MS          30U
#define BUTTON_REPEAT_DELAY_MS      650U
#define BUTTON_REPEAT_INTERVAL_MS   180U

#define UP_PORT                     UP_GPIO_Port
#define UP_PIN                      UP_Pin

#define DOWN_PORT                   DOWN_GPIO_Port
#define DOWN_PIN                    DOWN_Pin

#define LEFT_PORT                   LEFT_GPIO_Port
#define LEFT_PIN                    LEFT_Pin

#define RIGHT_PORT                  RIGHT_GPIO_Port
#define RIGHT_PIN                   RIGHT_Pin

#define PAGE_NEXT_PORT              PAGE_NEXT_GPIO_Port
#define PAGE_NEXT_PIN               PAGE_NEXT_Pin

#define PAGE_PREVIOUS_PORT          PAGE_PREVIOUS_GPIO_Port
#define PAGE_PREVIOUS_PIN           PAGE_PREVIOUS_Pin

#define CONFIRM_PORT                CONFIRM_GPIO_Port
#define CONFIRM_PIN                 CONFIRM_Pin

#define MODE_LEVER_PORT             MODE_LEVER_GPIO_Port
#define MODE_LEVER_PIN              MODE_LEVER_Pin

typedef struct
{
    GPIO_TypeDef *port;
    uint16_t pin;

    GPIO_PinState last_raw;
    GPIO_PinState stable_state;

    uint32_t last_change_time;
    uint32_t press_start_time;
    uint32_t next_repeat_time;
} Button;

static Button button_up =
{
    UP_PORT, UP_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

static Button button_down =
{
    DOWN_PORT, DOWN_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

static Button button_left =
{
    LEFT_PORT, LEFT_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

static Button button_right =
{
    RIGHT_PORT, RIGHT_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

static Button button_page_next =
{
    PAGE_NEXT_PORT, PAGE_NEXT_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

static Button button_page_previous =
{
    PAGE_PREVIOUS_PORT, PAGE_PREVIOUS_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

static Button button_confirm =
{
    CONFIRM_PORT, CONFIRM_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

static Button button_mode_lever =
{
    MODE_LEVER_PORT, MODE_LEVER_PIN,
    GPIO_PIN_SET, GPIO_PIN_SET,
    0U, 0U, 0U
};

/* ============================================================
 * GitHub navigation state returned by Raspberry Pi
 * ============================================================ */
typedef struct
{
    uint16_t page;
    uint16_t node;
    uint16_t span;
    uint16_t offset;
    uint32_t generation;
} NavigationState;

static NavigationState nav_state = {0};
static uint8_t current_cells[BRAILLE_CELL_COUNT] = {0};
static uint8_t current_motor_state[MOTOR_COUNT];
static uint8_t bt_connected = 0U;
static uint32_t last_bt_retry = 0U;
static uint8_t bt_protocol_v2 = 0U;
static uint8_t bt_protocol_v3 = 0U;
static uint32_t next_control_sequence = 1U;

typedef struct
{
    char control;
    char action;
    uint32_t sequence;
} ControlCommand;

static ControlCommand control_queue[CONTROL_QUEUE_CAPACITY];
static uint8_t control_queue_head = 0U;
static uint8_t control_queue_tail = 0U;
static uint8_t control_queue_count = 0U;
static ControlCommand control_in_flight = {0};
static uint8_t control_has_in_flight = 0U;
static uint8_t control_retry_count = 0U;
static uint32_t control_sent_at = 0U;
static char bt_rx_line[BT_RX_LINE_SIZE];
static uint16_t bt_rx_line_length = 0U;

/* ============================================================
 * Prototypes
 * ============================================================ */
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);

static void Debug_Print(const char *text);
static void Debug_Printf(const char *fmt, ...);

static HAL_StatusTypeDef PCA_WriteReg(uint16_t addr, uint8_t reg, uint8_t val);
static HAL_StatusTypeDef PCA_Init(uint16_t addr);
static HAL_StatusTypeDef PCA_SetPWM(uint16_t addr, uint8_t channel, uint16_t off_count);
static HAL_StatusTypeDef Motor_SetState(uint8_t motor, uint8_t state);
static void ApplyBrailleFrame(const uint8_t cells[BRAILLE_CELL_COUNT]);

static uint8_t ButtonPollStep(Button *button);
static uint8_t ButtonPollEdge(Button *button, char *action);
static uint8_t ButtonPollConfirm(Button *button, char *action);
static uint8_t ModeLeverPoll(Button *lever, char *action);

static uint8_t HC05_ReadLine(char *buf, uint16_t buf_size, uint32_t timeout_ms);
static uint8_t ReceiveFrameFromPi(uint32_t timeout_ms);
static uint8_t ParseAndApplyFrame(char *line);
static void ProcessHostLine(char *line);
static void PumpBluetoothInput(void);
static void ResetControlTransport(void);
static uint8_t QueueControlAction(char control, char action);
static void ServiceControlTransmit(void);
static uint8_t SendControlAction(char control, char action);
static uint8_t TryBluetoothHandshake(void);
static void ShowCurrentState(void);

/* ============================================================
 * Debug UART2
 * ============================================================ */
static void Debug_Print(const char *text)
{
    HAL_UART_Transmit(
        &huart2,
        (uint8_t *)text,
        (uint16_t)strlen(text),
        1000U);
}

static void Debug_Printf(const char *fmt, ...)
{
    char buf[256];
    va_list ap;

    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    Debug_Print(buf);
}

/* ============================================================
 * PCA9685
 * ============================================================ */
static HAL_StatusTypeDef PCA_WriteReg(uint16_t addr, uint8_t reg, uint8_t val)
{
    return HAL_I2C_Mem_Write(
        &hi2c1,
        addr,
        reg,
        I2C_MEMADD_SIZE_8BIT,
        &val,
        1U,
        100U);
}

static HAL_StatusTypeDef PCA_Init(uint16_t addr)
{
    /* ~50 Hz with nominal 25 MHz PCA9685 oscillator */
    const uint8_t prescale = 121U;

    if (PCA_WriteReg(addr, PCA_MODE1, PCA_MODE1_SLEEP | PCA_MODE1_AI) != HAL_OK)
        return HAL_ERROR;

    if (PCA_WriteReg(addr, PCA_PRESCALE, prescale) != HAL_OK)
        return HAL_ERROR;

    if (PCA_WriteReg(addr, PCA_MODE2, PCA_MODE2_OUTDRV) != HAL_OK)
        return HAL_ERROR;

    if (PCA_WriteReg(addr, PCA_MODE1, PCA_MODE1_AI) != HAL_OK)
        return HAL_ERROR;

    HAL_Delay(5U);
    return HAL_OK;
}

static HAL_StatusTypeDef PCA_SetPWM(uint16_t addr, uint8_t channel, uint16_t off_count)
{
    uint8_t data[4];
    uint8_t reg;

    if (channel > 15U)
        return HAL_ERROR;

    if (off_count > 4095U)
        off_count = 4095U;

    data[0] = 0U; /* ON_L  */
    data[1] = 0U; /* ON_H  */
    data[2] = (uint8_t)(off_count & 0xFFU);
    data[3] = (uint8_t)((off_count >> 8U) & 0x0FU);

    reg = (uint8_t)(PCA_LED0_ON_L + (4U * channel));

    return HAL_I2C_Mem_Write(
        &hi2c1,
        addr,
        reg,
        I2C_MEMADD_SIZE_8BIT,
        data,
        4U,
        100U);
}

/* ============================================================
 * Servo control
 * ============================================================ */
static HAL_StatusTypeDef Motor_SetState(uint8_t motor, uint8_t state)
{
    uint16_t pca_addr;
    uint8_t channel;
    uint16_t angle_x10;
    uint32_t pulse_us;
    uint32_t pwm_count;

    if (motor >= MOTOR_COUNT || state > 7U)
        return HAL_ERROR;

    if (motor < 10U)
    {
        pca_addr = PCA1_ADDR;
        channel = motor;
    }
    else
    {
        pca_addr = PCA2_ADDR;
        channel = (uint8_t)(motor - 10U);
    }

    /* state 0..7 -> 0,22.5,...157.5 degrees */
    angle_x10 = (uint16_t)state * 225U;

    pulse_us = SERVO_MIN_US +
               (((uint32_t)(SERVO_MAX_US - SERVO_MIN_US) *
                 (uint32_t)angle_x10) / 1800U);

    pwm_count =
        (pulse_us * 4096U * SERVO_FREQ_HZ) /
        1000000U;

    return PCA_SetPWM(pca_addr, channel, (uint16_t)pwm_count);
}

/* ============================================================
 * 10 Braille cells -> 20 motors
 *
 * NEW CHANNEL MAP:
 *   Cell 1 top    -> PCA1 CH0
 *   Cell 2 top    -> PCA1 CH1
 *   ...
 *   Cell 10 top   -> PCA1 CH9
 *
 *   Cell 1 bottom -> PCA2 CH0
 *   Cell 2 bottom -> PCA2 CH1
 *   ...
 *   Cell 10 bottom-> PCA2 CH9
 *
 * GitHub / Unicode Braille 6-bit encoding:
 * bit0=dot1 bit1=dot2 bit2=dot3 bit3=dot4 bit4=dot5 bit5=dot6
 * ============================================================ */
static void ApplyBrailleFrame(const uint8_t cells[BRAILLE_CELL_COUNT])
{
    uint8_t i;
    uint8_t changed = 0U;

    for (i = 0U; i < BRAILLE_CELL_COUNT; i++)
    {
        uint8_t packed = (uint8_t)(cells[i] & 0x3FU);

        /* TOP motor: dots 1,2,3. Motor is above, so keep normal order. */
        uint8_t top_pattern = (uint8_t)(packed & 0x07U);

        /* BOTTOM motor raw order from GitHub: dot4,dot5,dot6. */
        uint8_t bottom_raw = (uint8_t)((packed >> 3U) & 0x07U);

        /* Bottom motor is physically below -> reverse to dot6,dot5,dot4. */
        uint8_t bottom_pattern = BOTTOM_REVERSE_LUT[bottom_raw];

        uint8_t top_state = SERVO_STATE_LUT[top_pattern];
        uint8_t bottom_state = SERVO_STATE_LUT[bottom_pattern];

        /*
         * NEW WIRING:
         * top_motor    0..9   -> PCA1 CH0..9
         * bottom_motor 10..19 -> PCA2 CH0..9
         */
        uint8_t top_motor = i;
        uint8_t bottom_motor = (uint8_t)(10U + i);

        if (current_motor_state[top_motor] != top_state)
        {
            if (Motor_SetState(top_motor, top_state) == HAL_OK)
                current_motor_state[top_motor] = top_state;

            changed++;
        }

        if (current_motor_state[bottom_motor] != bottom_state)
        {
            if (Motor_SetState(bottom_motor, bottom_state) == HAL_OK)
                current_motor_state[bottom_motor] = bottom_state;

            changed++;
        }

        if (changed >= SERVO_BATCH_SIZE)
        {
            HAL_Delay(SERVO_BATCH_DELAY_MS);
            changed = 0U;
        }
    }
}

/* ============================================================
 * Button poll with auto-repeat
 *
 * Pull-up wiring:
 *   released = HIGH
 *   pressed  = LOW
 *
 * Return 1 when one movement step should be executed.
 * ============================================================ */
static uint8_t ButtonPollStep(Button *button)
{
    uint32_t now = HAL_GetTick();
    GPIO_PinState raw = HAL_GPIO_ReadPin(button->port, button->pin);

    if (raw != button->last_raw)
    {
        button->last_raw = raw;
        button->last_change_time = now;
    }

    if ((now - button->last_change_time) < BUTTON_DEBOUNCE_MS)
        return 0U;

    if (raw != button->stable_state)
    {
        button->stable_state = raw;

        if (raw == GPIO_PIN_RESET)
        {
            button->press_start_time = now;
            button->next_repeat_time = now + BUTTON_REPEAT_DELAY_MS;
            return 1U;
        }

        return 0U;
    }

    if (button->stable_state == GPIO_PIN_RESET)
    {
        if ((int32_t)(now - button->next_repeat_time) >= 0)
        {
            button->next_repeat_time = now + BUTTON_REPEAT_INTERVAL_MS;
            return 1U;
        }
    }

    return 0U;
}

/* Confirm is the only input whose hold duration has semantic meaning.
 * Emit exactly one SHORT/LONG command on release; never auto-repeat it. */
static uint8_t ButtonPollConfirm(Button *button, char *action)
{
    uint32_t now = HAL_GetTick();
    GPIO_PinState raw = HAL_GPIO_ReadPin(button->port, button->pin);

    if (raw != button->last_raw)
    {
        button->last_raw = raw;
        button->last_change_time = now;
    }

    if ((now - button->last_change_time) < BUTTON_DEBOUNCE_MS)
        return 0U;

    if (raw == button->stable_state)
        return 0U;

    button->stable_state = raw;
    if (raw == GPIO_PIN_RESET)
    {
        button->press_start_time = now;
        return 0U;
    }

    if (action == NULL)
        return 0U;

    *action = ((now - button->press_start_time) >= BUTTON_REPEAT_DELAY_MS) ? 'L' : 'S';
    return 1U;
}

/* A maintained active-low lever selects capture when LOW and reading when HIGH. */
static uint8_t ModeLeverPoll(Button *lever, char *action)
{
    uint32_t now = HAL_GetTick();
    GPIO_PinState raw = HAL_GPIO_ReadPin(lever->port, lever->pin);

    if (raw != lever->last_raw)
    {
        lever->last_raw = raw;
        lever->last_change_time = now;
    }

    if ((now - lever->last_change_time) < BUTTON_DEBOUNCE_MS || raw == lever->stable_state)
        return 0U;

    lever->stable_state = raw;
    if (action == NULL)
        return 0U;
    *action = (raw == GPIO_PIN_RESET) ? 'A' : 'R';
    return 1U;
}

/* ============================================================
 * HC-05 UART line receive
 * ============================================================ */
static uint8_t HC05_ReadLine(char *buf, uint16_t buf_size, uint32_t timeout_ms)
{
    uint32_t start = HAL_GetTick();
    uint16_t idx = 0U;
    uint8_t ch;

    if (buf == NULL || buf_size < 2U)
        return 0U;

    while ((HAL_GetTick() - start) < timeout_ms)
    {
        HAL_StatusTypeDef st = HAL_UART_Receive(&huart1, &ch, 1U, 20U);

        if (st == HAL_TIMEOUT)
            continue;

        if (st != HAL_OK)
            return 0U;

        if (ch == '\r')
            continue;

        if (ch == '\n')
        {
            buf[idx] = '\0';
            return 1U;
        }

        if (idx >= (uint16_t)(buf_size - 1U))
            return 0U;

        buf[idx++] = (char)ch;
    }

    return 0U;
}

/* ============================================================
 * Pi -> STM frame
 *
 * FRAME,page,node,span,offset,gen,c0,c1,...,c9
 * ============================================================ */
static uint8_t ReceiveFrameFromPi(uint32_t timeout_ms)
{
    char line[256];

    if (!HC05_ReadLine(line, sizeof(line), timeout_ms))
        return 0U;

    Debug_Printf("BT RX: %s\r\n", line);
    return ParseAndApplyFrame(line);
}

/* V3 DOWN lifecycle: emit one edge after debounce and never repeat locally. */
static uint8_t ButtonPollEdge(Button *button, char *action)
{
    uint32_t now = HAL_GetTick();
    GPIO_PinState raw = HAL_GPIO_ReadPin(button->port, button->pin);

    if (raw != button->last_raw)
    {
        button->last_raw = raw;
        button->last_change_time = now;
    }
    if ((now - button->last_change_time) < BUTTON_DEBOUNCE_MS)
        return 0U;
    if (raw == button->stable_state)
        return 0U;

    button->stable_state = raw;
    *action = (raw == GPIO_PIN_RESET) ? 'A' : 'R';
    return 1U;
}

static uint8_t ParseAndApplyFrame(char *line)
{
    char *token;
    unsigned long values[5U + BRAILLE_CELL_COUNT];
    uint8_t i;

    if (line == NULL)
        return 0U;

    token = strtok(line, ",");

    if (token == NULL || strcmp(token, "FRAME") != 0)
    {
        Debug_Print("FRAME FORMAT ERROR\r\n");
        return 0U;
    }

    for (i = 0U; i < (5U + BRAILLE_CELL_COUNT); i++)
    {
        char *end_ptr;

        token = strtok(NULL, ",");
        if (token == NULL)
            return 0U;

        values[i] = strtoul(token, &end_ptr, 10);

        if (*end_ptr != '\0')
            return 0U;
    }

    /* Reject unexpected extra fields. */
    if (strtok(NULL, ",") != NULL)
        return 0U;

    nav_state.page = (uint16_t)values[0];
    nav_state.node = (uint16_t)values[1];
    nav_state.span = (uint16_t)values[2];
    nav_state.offset = (uint16_t)values[3];
    nav_state.generation = (uint32_t)values[4];

    for (i = 0U; i < BRAILLE_CELL_COUNT; i++)
    {
        if (values[5U + i] > 63U)
            return 0U;

        current_cells[i] = (uint8_t)values[5U + i];
    }

    ApplyBrailleFrame(current_cells);
    ShowCurrentState();

    return 1U;
}

/* ============================================================
 * Version 2/3 host transport
 *
 *   HELLO,3                       -> ACK,HELLO,3
 *   NAV,<control>,<action>,<seq> -> ACK,<seq>
 *   FRAME,... arrives independently whenever presentation changes.
 *
 * One in-flight command plus a bounded FIFO preserves button order without
 * blocking GPIO polling. A missing ACK is retried with the same sequence, so
 * the host can acknowledge duplicates without applying them twice.
 * ============================================================ */
static void ResetControlTransport(void)
{
    control_queue_head = 0U;
    control_queue_tail = 0U;
    control_queue_count = 0U;
    control_has_in_flight = 0U;
    control_retry_count = 0U;
    control_sent_at = 0U;
    bt_rx_line_length = 0U;
    next_control_sequence = 1U;
}

static uint8_t QueueControlAction(char control, char action)
{
    ControlCommand *command;

    /* V3 reserves one FIFO slot for DOWN release so unrelated input cannot
     * leave the host repeat controller active after the physical button is
     * released. */
    if (control_queue_count >= CONTROL_QUEUE_CAPACITY ||
        (bt_protocol_v3 &&
         control_queue_count >= (CONTROL_QUEUE_CAPACITY - 1U) &&
         !(control == 'D' && action == 'R')))
    {
        Debug_Print("BT TX QUEUE FULL\r\n");
        return 0U;
    }

    command = &control_queue[control_queue_tail];
    command->control = control;
    command->action = action;
    command->sequence = next_control_sequence++;
    if (next_control_sequence == 0U)
        next_control_sequence = 1U;

    control_queue_tail = (uint8_t)((control_queue_tail + 1U) % CONTROL_QUEUE_CAPACITY);
    control_queue_count++;
    return 1U;
}

static void ServiceControlTransmit(void)
{
    char packet[48];
    uint32_t now;

    if (!bt_connected || !bt_protocol_v2)
        return;

    now = HAL_GetTick();
    if (control_has_in_flight)
    {
        if ((now - control_sent_at) < ACK_TIMEOUT_MS)
            return;
        if (control_retry_count >= ACK_RETRY_LIMIT)
        {
            Debug_Print("NO ACK -> BLUETOOTH DISCONNECTED\r\n");
            bt_connected = 0U;
            ResetControlTransport();
            return;
        }
        control_retry_count++;
    }
    else
    {
        if (control_queue_count == 0U)
            return;
        control_in_flight = control_queue[control_queue_head];
        control_queue_head = (uint8_t)((control_queue_head + 1U) % CONTROL_QUEUE_CAPACITY);
        control_queue_count--;
        control_has_in_flight = 1U;
        control_retry_count = 0U;
    }

    snprintf(
        packet,
        sizeof(packet),
        "NAV,%c,%c,%lu\n",
        control_in_flight.control,
        control_in_flight.action,
        (unsigned long)control_in_flight.sequence);
    Debug_Printf("BT TX: %s", packet);
    if (HAL_UART_Transmit(
            &huart1,
            (uint8_t *)packet,
            (uint16_t)strlen(packet),
            1000U) != HAL_OK)
    {
        bt_connected = 0U;
        ResetControlTransport();
        return;
    }
    control_sent_at = now;
}

static void ProcessHostLine(char *line)
{
    unsigned long sequence;
    char trailing;

    if (line == NULL || line[0] == '\0')
        return;

    Debug_Printf("BT RX: %s\r\n", line);
    if (sscanf(line, "ACK,%lu%c", &sequence, &trailing) == 1)
    {
        if (control_has_in_flight && sequence == control_in_flight.sequence)
        {
            control_has_in_flight = 0U;
            control_retry_count = 0U;
            Debug_Printf("BT ACK: %lu\r\n", sequence);
        }
        return;
    }
    if (sscanf(line, "NACK,%lu,BUSY%c", &sequence, &trailing) == 1)
    {
        if (control_has_in_flight && sequence == control_in_flight.sequence)
            control_sent_at = HAL_GetTick();
        return;
    }
    if (strncmp(line, "FRAME,", 6U) == 0)
    {
        if (!ParseAndApplyFrame(line))
            Debug_Print("FRAME FORMAT ERROR\r\n");
        return;
    }
    Debug_Print("BT RX UNKNOWN\r\n");
}

static void PumpBluetoothInput(void)
{
    uint8_t ch;
    uint8_t processed = 0U;

    while (processed < 64U)
    {
        HAL_StatusTypeDef status = HAL_UART_Receive(&huart1, &ch, 1U, 1U);
        if (status == HAL_TIMEOUT)
            break;
        if (status != HAL_OK)
        {
            bt_connected = 0U;
            ResetControlTransport();
            return;
        }
        processed++;
        if (ch == '\r')
            continue;
        if (ch == '\n')
        {
            bt_rx_line[bt_rx_line_length] = '\0';
            ProcessHostLine(bt_rx_line);
            bt_rx_line_length = 0U;
            continue;
        }
        if (bt_rx_line_length >= (BT_RX_LINE_SIZE - 1U))
        {
            bt_rx_line_length = 0U;
            Debug_Print("BT RX LINE TOO LONG\r\n");
            continue;
        }
        bt_rx_line[bt_rx_line_length++] = (char)ch;
    }
}

/* Keep legacy blocking response semantics only when an old host answers HELLO. */
static uint8_t SendControlAction(char control, char action)
{
    char packet[32];

    if (bt_protocol_v2)
        return QueueControlAction(control, action);

    snprintf(packet, sizeof(packet), "NAV,%c,%c\n", control, action);
    Debug_Printf("BT TX: %s", packet);
    if (HAL_UART_Transmit(
            &huart1,
            (uint8_t *)packet,
            (uint16_t)strlen(packet),
            1000U) != HAL_OK)
        return 0U;

    if (!ReceiveFrameFromPi(FRAME_TIMEOUT_MS))
    {
        Debug_Print("NO FRAME -> BLUETOOTH DISCONNECTED\r\n");
        bt_connected = 0U;
        return 0U;
    }
    return 1U;
}

/* ============================================================
 * Initial / reconnect handshake with legacy fallback
 * ============================================================ */
static uint8_t TryBluetoothHandshake(void)
{
    static const char hello_v2[] = "HELLO,2\n";
    static const char hello_v1[] = "HELLO\n";
    char line[64];
    GPIO_PinState lever_state;

    ResetControlTransport();
    bt_protocol_v2 = 0U;
    bt_protocol_v3 = 0U;
    {
        static const char hello_v3[] = "HELLO,3\n";
        Debug_Print("BT: HELLO V3...\r\n");
        HAL_UART_Transmit(
            &huart1,
            (uint8_t *)hello_v3,
            (uint16_t)(sizeof(hello_v3) - 1U),
            1000U);
    }

    if (HC05_ReadLine(line, sizeof(line), VERSIONED_HANDSHAKE_TIMEOUT_MS) &&
        strcmp(line, "ACK,HELLO,3") == 0)
    {
        bt_protocol_v2 = 1U;
        bt_protocol_v3 = 1U;
        bt_connected = 1U;
        Debug_Print("BT: HOST CONNECTED (V3 EDGES)\r\n");
    }
    else
    {
        Debug_Print("BT: V3 UNAVAILABLE, TRY V2\r\n");
        bt_protocol_v3 = 0U;
        Debug_Print("BT: HELLO V2...\r\n");
        HAL_UART_Transmit(
            &huart1,
            (uint8_t *)hello_v2,
            (uint16_t)(sizeof(hello_v2) - 1U),
            1000U);

        if (HC05_ReadLine(line, sizeof(line), VERSIONED_HANDSHAKE_TIMEOUT_MS) &&
            strcmp(line, "ACK,HELLO,2") == 0)
        {
            bt_protocol_v2 = 1U;
            bt_connected = 1U;
            Debug_Print("BT: HOST CONNECTED (V2 ASYNC)\r\n");
        }
        else
        {
            Debug_Print("BT: V2 UNAVAILABLE, TRY LEGACY\r\n");
            HAL_UART_Transmit(
                &huart1,
                (uint8_t *)hello_v1,
                (uint16_t)(sizeof(hello_v1) - 1U),
                1000U);
            if (!ReceiveFrameFromPi(VERSIONED_HANDSHAKE_TIMEOUT_MS))
            {
                bt_connected = 0U;
                Debug_Print("BT: WAITING FOR PI / HC-05 LINK\r\n");
                return 0U;
            }
            bt_protocol_v2 = 0U;
            bt_connected = 1U;
            Debug_Print("BT: HOST CONNECTED (V1 LEGACY)\r\n");
        }
    }

    lever_state = HAL_GPIO_ReadPin(MODE_LEVER_PORT, MODE_LEVER_PIN);
    button_mode_lever.last_raw = lever_state;
    button_mode_lever.stable_state = lever_state;
    button_mode_lever.last_change_time = HAL_GetTick();
    if (!SendControlAction('V', (lever_state == GPIO_PIN_RESET) ? 'A' : 'R'))
        return 0U;
    ServiceControlTransmit();
    return 1U;
}

/* ============================================================
 * Debug state
 * ============================================================ */
static void ShowCurrentState(void)
{
    uint8_t i;

    Debug_Print(
        "\r\n"
        "========================================\r\n");

    Debug_Printf("PAGE   = %u\r\n", nav_state.page);
    Debug_Printf("NODE   = %u\r\n", nav_state.node);
    Debug_Printf("SPAN   = %u\r\n", nav_state.span);
    Debug_Printf("OFFSET = %u\r\n", nav_state.offset);
    Debug_Printf("GEN    = %lu\r\n", (unsigned long)nav_state.generation);

    Debug_Print("CELLS  = ");

    for (i = 0U; i < BRAILLE_CELL_COUNT; i++)
    {
        Debug_Printf("%u", current_cells[i]);

        if (i < (BRAILLE_CELL_COUNT - 1U))
            Debug_Print(",");
    }

    Debug_Print(
        "\r\n"
        "========================================\r\n");
}

/* ============================================================
 * MAIN
 * ============================================================ */
int main(void)
{
    HAL_Init();
    SystemClock_Config();

    MX_GPIO_Init();
    MX_I2C1_Init();
    MX_USART1_UART_Init();
    MX_USART2_UART_Init();

    HAL_Delay(100U);

    Debug_Print(
        "\r\n\r\n"
        "========================================\r\n"
        " BRAILLE DISPLAY - HC05 + GITHUB NAV\r\n"
        " PCA1=TOP / PCA2=BOTTOM\r\n"
        "========================================\r\n");

    Debug_Printf("HC-05 UART = %lu baud\r\n", (unsigned long)HC05_UART_BAUD);

    /* PCA presence check */
    if (HAL_I2C_IsDeviceReady(&hi2c1, PCA1_ADDR, 3U, 100U) != HAL_OK)
    {
        Debug_Print("PCA 0x40 NOT FOUND\r\n");
        Error_Handler();
    }
    Debug_Print("PCA 0x40 FOUND\r\n");

    if (HAL_I2C_IsDeviceReady(&hi2c1, PCA2_ADDR, 3U, 100U) != HAL_OK)
    {
        Debug_Print("PCA 0x41 NOT FOUND\r\n");
        Error_Handler();
    }
    Debug_Print("PCA 0x41 FOUND\r\n");

    if (PCA_Init(PCA1_ADDR) != HAL_OK)
    {
        Debug_Print("PCA 0x40 INIT ERROR\r\n");
        Error_Handler();
    }

    if (PCA_Init(PCA2_ADDR) != HAL_OK)
    {
        Debug_Print("PCA 0x41 INIT ERROR\r\n");
        Error_Handler();
    }

    Debug_Print("PCA INIT OK\r\n");
    Debug_Print("PCA1 0x40 CH0~9 = TOP Cell1~10\r\n");
    Debug_Print("PCA2 0x41 CH0~9 = BOTTOM Cell1~10\r\n");

    /* Force the first received frame to update all motors. */
    memset(current_motor_state, 0xFF, sizeof(current_motor_state));
    memset(current_cells, 0, sizeof(current_cells));

    Debug_Print(
        "\r\nBUTTONS\r\n"
        "CN7-28 / PA0 = UP\r\n"
        "CN7-30 / PA1 = DOWN\r\n"
        "CN7-32 / PA4 = LEFT\r\n"
        "CN7-34 / PB0 = RIGHT\r\n"
        "CN10-24 / PB1 = PAGE NEXT\r\n"
        "PC0 = PAGE PREVIOUS\r\n"
        "PC1 = CONFIRM (release sends SHORT or LONG)\r\n"
        "PC2 = MODE LEVER (LOW=capture, HIGH=reading)\r\n"
        "Tap = 1 step\r\n"
        "Hold >= 650ms = auto-repeat every 180ms\r\n\r\n");

    /* First connection attempt. Failure is NOT fatal. */
    TryBluetoothHandshake();
    last_bt_retry = HAL_GetTick();

    while (1)
    {
        /* Auto-reconnect without rebooting STM32. */
        if (!bt_connected)
        {
            if ((HAL_GetTick() - last_bt_retry) >= BT_RETRY_MS)
            {
                last_bt_retry = HAL_GetTick();
                TryBluetoothHandshake();
            }

            HAL_Delay(1U);
            continue;
        }

        /* V2 host responses never block button polling. ACK clears the one
         * in-flight command; FRAME updates braille whenever the host state
         * changes. Legacy mode continues to receive inside SendControlAction. */
        if (bt_protocol_v2)
        {
            PumpBluetoothInput();
            ServiceControlTransmit();
            if (!bt_connected)
                continue;
        }

        /* ---------------- UP ---------------- */
        if (ButtonPollStep(&button_up))
        {
            Debug_Print("UP STEP\r\n");
            SendControlAction('U', 'S');
        }

        /* ---------------- DOWN ---------------- */
        if (bt_protocol_v3)
        {
            char action;
            if (ButtonPollEdge(&button_down, &action))
            {
                Debug_Printf("DOWN %s\r\n", (action == 'A') ? "PRESS" : "RELEASE");
                SendControlAction('D', action);
            }
        }
        else if (ButtonPollStep(&button_down))
        {
            Debug_Print("DOWN STEP\r\n");
            SendControlAction('D', 'S');
        }

        /* ---------------- LEFT ---------------- */
        if (ButtonPollStep(&button_left))
        {
            Debug_Print("LEFT STEP\r\n");
            SendControlAction('L', 'S');
        }

        /* ---------------- RIGHT ---------------- */
        if (ButtonPollStep(&button_right))
        {
            Debug_Print("RIGHT STEP\r\n");
            SendControlAction('R', 'S');
        }

        /* ---------------- PAGE NEXT ---------------- */
        if (ButtonPollStep(&button_page_next))
        {
            Debug_Print("PAGE NEXT STEP\r\n");
            SendControlAction('N', 'S');
        }

        /* ---------------- PAGE PREVIOUS ---------------- */
        if (ButtonPollStep(&button_page_previous))
        {
            Debug_Print("PAGE PREVIOUS STEP\r\n");
            SendControlAction('P', 'S');
        }

        /* ---------------- CONFIRM ---------------- */
        {
            char action;
            if (ButtonPollConfirm(&button_confirm, &action))
            {
                Debug_Printf("CONFIRM %s\r\n", (action == 'L') ? "LONG" : "SHORT");
                SendControlAction('C', action);
            }
        }

        /* ---------------- MODE LEVER ---------------- */
        {
            char action;
            if (ModeLeverPoll(&button_mode_lever, &action))
            {
                Debug_Printf("MODE %s\r\n", (action == 'A') ? "CAPTURE" : "READING");
                SendControlAction('V', action);
            }
        }

        if (bt_protocol_v2)
        {
            PumpBluetoothInput();
            ServiceControlTransmit();
        }

        HAL_Delay(1U);
    }
}

/* ============================================================
 * CLOCK: HSI 16 MHz -> SYSCLK 84 MHz
 * ============================================================ */
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE3);

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
    RCC_OscInitStruct.PLL.PLLM = 16;
    RCC_OscInitStruct.PLL.PLLN = 336;
    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
    RCC_OscInitStruct.PLL.PLLQ = 7;

    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
        Error_Handler();

    RCC_ClkInitStruct.ClockType =
        RCC_CLOCKTYPE_HCLK |
        RCC_CLOCKTYPE_SYSCLK |
        RCC_CLOCKTYPE_PCLK1 |
        RCC_CLOCKTYPE_PCLK2;

    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * I2C1 via ST Morpho male CN10:
 * CN10-3 = PB8 SCL
 * CN10-5 = PB9 SDA
 * 100 kHz
 * Pins are configured by CubeMX-generated HAL MSP code.
 * ============================================================ */
static void MX_I2C1_Init(void)
{
    hi2c1.Instance = I2C1;
    hi2c1.Init.ClockSpeed = 100000;
    hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
    hi2c1.Init.OwnAddress1 = 0;
    hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    hi2c1.Init.OwnAddress2 = 0;
    hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;

    if (HAL_I2C_Init(&hi2c1) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * USART1 -> HC-05
 * PA9 TX / PA10 RX
 * ============================================================ */
static void MX_USART1_UART_Init(void)
{
    huart1.Instance = USART1;
    huart1.Init.BaudRate = HC05_UART_BAUD;
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits = UART_STOPBITS_1;
    huart1.Init.Parity = UART_PARITY_NONE;
    huart1.Init.Mode = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart1.Init.OverSampling = UART_OVERSAMPLING_16;

    if (HAL_UART_Init(&huart1) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * USART2 -> Tera Term / ST-LINK VCP
 * PA2 TX / PA3 RX
 * ============================================================ */
static void MX_USART2_UART_Init(void)
{
    huart2.Instance = USART2;
    huart2.Init.BaudRate = DEBUG_UART_BAUD;
    huart2.Init.WordLength = UART_WORDLENGTH_8B;
    huart2.Init.StopBits = UART_STOPBITS_1;
    huart2.Init.Parity = UART_PARITY_NONE;
    huart2.Init.Mode = UART_MODE_TX_RX;
    huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart2.Init.OverSampling = UART_OVERSAMPLING_16;

    if (HAL_UART_Init(&huart2) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * GPIO buttons
 * ============================================================ */
static void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    /* PA0 / PA1 / PA4 */
    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    /* PB0 = RIGHT, PB1 = PAGE NEXT */
    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* PC0 = PAGE PREVIOUS, PC1 = CONFIRM, PC2 = MODE LEVER */
    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
}

/* ============================================================
 * Error handler
 * ============================================================ */
void Error_Handler(void)
{
    __disable_irq();

    while (1)
    {
    }
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
    (void)file;
    (void)line;
}
#endif

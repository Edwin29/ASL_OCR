
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <errno.h>
#define BRAILLE_CELL_COUNT 10
#define MOTOR_COUNT 20
#define SERVO_BATCH_SIZE 4
#define SERVO_BATCH_DELAY_MS 100
#define BT_RX_LINE_SIZE 256
typedef enum {HAL_OK,HAL_ERROR,HAL_TIMEOUT} HAL_StatusTypeDef;
typedef struct {uint16_t page,node,span,offset;uint32_t generation;} NavigationState;
static NavigationState nav_state;
static uint8_t current_cells[10],current_motor_state[20],bt_connected;
static char bt_rx_line[256];
static uint16_t bt_rx_line_length;
static unsigned delay_ms,motor_calls,accepted_suffix;
static HAL_StatusTypeDef motor_result=HAL_ERROR;
static int huart1;
static const unsigned char *wire;static size_t wire_at;
static void Debug_Print(const char *s){(void)s;}
static void ShowCurrentState(void){}
static void HAL_Delay(unsigned ms){delay_ms+=ms;}
static HAL_StatusTypeDef Motor_SetState(uint8_t motor,uint8_t state){(void)motor;(void)state;motor_calls++;return motor_result;}
static void ResetControlTransport(void){bt_rx_line_length=0;}
static void ProcessHostLine(char *line){if(strncmp(line,"FRAME,",6)==0)accepted_suffix++;}
static HAL_StatusTypeDef HAL_UART_Receive(int *uart,uint8_t *ch,unsigned count,unsigned timeout){
    (void)uart;(void)count;(void)timeout;
    if(!wire[wire_at])return HAL_TIMEOUT;
    *ch=wire[wire_at++];return HAL_OK;
}
static const uint8_t SERVO_STATE_LUT[8] =
{
    0U, 1U, 2U, 3U,
    4U, 5U, 6U, 7U
};
static const uint8_t BOTTOM_REVERSE_LUT[8] =
{
    0U, 4U, 2U, 6U,
    1U, 5U, 3U, 7U
};
static volatile uint8_t last_frame_apply_ok = 0U;
static volatile uint32_t pca_apply_failures = 0U;
static volatile uint32_t last_applied_generation = 0U;
static uint8_t bt_rx_discarding = 0U;
static uint8_t ApplyBrailleFrame(const uint8_t cells[BRAILLE_CELL_COUNT])
{
    uint8_t i;
    uint8_t changed = 0U;
    uint8_t applied = 1U;

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
            else
            {
                applied = 0U;
                pca_apply_failures++;
            }

            changed++;
        }

        if (current_motor_state[bottom_motor] != bottom_state)
        {
            if (Motor_SetState(bottom_motor, bottom_state) == HAL_OK)
                current_motor_state[bottom_motor] = bottom_state;
            else
            {
                applied = 0U;
                pca_apply_failures++;
            }

            changed++;
        }

        if (changed >= SERVO_BATCH_SIZE)
        {
            HAL_Delay(SERVO_BATCH_DELAY_MS);
            changed = 0U;
        }
    }
    return applied;
}
static uint8_t ParseAndApplyFrame(char *line)
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

int main(void){
    char invalid[]="FRAME,9,8,7,6,5,1,2,64,0,0,0,0,0,0,0";
    char valid[]="FRAME,1,2,3,4,6,1,1,1,1,1,1,1,1,1,1";
    char overflow[400];unsigned rejected,mutated,accepted,i;
    memset(current_cells,9,sizeof(current_cells));
    memset(current_motor_state,255,sizeof(current_motor_state));
    rejected=!ParseAndApplyFrame(invalid);
    mutated=nav_state.page!=0 || current_cells[0]!=9;
    memset(overflow,'X',256);
    strcpy(overflow+256,"FRAME,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0\n");
    wire=(unsigned char*)overflow;
    while(wire[wire_at])PumpBluetoothInput();
    accepted=ParseAndApplyFrame(valid);
    for(i=0;i<20;i++)if(current_motor_state[i]!=255)return 3;
    printf("{\"invalid_rejected\":%u,\"rejected_state_mutated\":%u,\"overflow_suffix_dispatched\":%u,\"valid_parse_accepted\":%u,\"hal_failed_calls\":%u,\"modeled_delay_ms\":%u",rejected,mutated,accepted_suffix,accepted,motor_calls,delay_ms);
printf(",\"last_frame_apply_ok\":%u,\"pca_apply_failures\":%lu",last_frame_apply_ok,(unsigned long)pca_apply_failures);

    {
        const char *bad[]={
          "FRAME,1,,2,3,4,5,0,0,0,0,0,0,0,0,0,0",
          "FRAME,65536,0,0,0,1,0,0,0,0,0,0,0,0,0,0",
          "FRAME,0,0,0,0,4294967296,0,0,0,0,0,0,0,0,0,0",
          "FRAME,0,0,0,0,1,-1,0,0,0,0,0,0,0,0,0",
          "FRAME,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,",
          "FRAME,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,1"
        };
        unsigned n;
        for(n=0;n<sizeof(bad)/sizeof(bad[0]);n++){
            NavigationState previous=nav_state;
            uint8_t cells_before[10];char input[256];unsigned calls_before=motor_calls;
            memcpy(cells_before,current_cells,10);strcpy(input,bad[n]);
            if(ParseAndApplyFrame(input) || memcmp(&previous,&nav_state,sizeof(previous)) ||
               memcmp(cells_before,current_cells,10) || motor_calls!=calls_before)return 4;
        }
        printf(",\"malformed_atomic_cases\":%u",n);
    }
    {
        unsigned before_calls=motor_calls;
        motor_result=HAL_OK;
        if(!ParseAndApplyFrame(valid) || !last_frame_apply_ok || last_applied_generation!=6 || motor_calls-before_calls!=20)return 5;
        before_calls=motor_calls;
        if(!ParseAndApplyFrame(valid) || !last_frame_apply_ok || motor_calls!=before_calls)return 6;
        printf(",\"same_frame_bus_recovery\":true,\"unchanged_motor_cache\":true");
    }
puts("}");return 0;}

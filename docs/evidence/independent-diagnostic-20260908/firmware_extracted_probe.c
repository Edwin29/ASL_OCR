
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#define BRAILLE_CELL_COUNT 10U
#define BT_RX_LINE_SIZE 256U
#define SERVO_BATCH_SIZE 4U
#define SERVO_BATCH_DELAY_MS 100U
#define HAL_OK 0
#define HAL_TIMEOUT 1
typedef int HAL_StatusTypeDef;
static struct {uint16_t page,node,span,offset;uint32_t generation;} nav_state;
static uint8_t current_cells[10],current_motor_state[20];
static const uint8_t SERVO_STATE_LUT[8]={0,1,2,3,4,5,6,7};
static const uint8_t BOTTOM_REVERSE_LUT[8]={0,4,2,6,1,5,3,7};
static int huart1,bt_connected,control_has_in_flight,control_retry_count;
static uint32_t control_sent_at;
static struct {unsigned long sequence;} control_in_flight;
static char bt_rx_line[256];static unsigned bt_rx_line_length;
static const char *wire;static unsigned wirepos,wirelen;
static double now_ms,next_arrival,spacing;static int reg_full;static uint8_t reg_byte;
static unsigned dropped,applied,motor_calls;static int debug_timing=1,motor_fail=0;
static void advance(double dt){double end=now_ms+dt;while(wirepos<wirelen && next_arrival<=end){if(reg_full)dropped++;else{reg_full=1;reg_byte=wire[wirepos];}wirepos++;next_arrival+=spacing;}now_ms=end;}
static uint32_t HAL_GetTick(void){return (uint32_t)now_ms;}
static void HAL_Delay(uint32_t ms){advance(ms);}
static HAL_StatusTypeDef HAL_UART_Receive(int *u,uint8_t *ch,unsigned size,unsigned timeout){if(!reg_full){if(wirepos<wirelen && next_arrival<=now_ms+timeout)advance(next_arrival-now_ms);else{advance(timeout);return HAL_TIMEOUT;}}*ch=reg_byte;reg_full=0;return HAL_OK;}
static void Debug_Print(const char *s){if(debug_timing)advance(strlen(s)*10.0/115.2);}
static void Debug_Printf(const char *fmt,...){char b[512];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);Debug_Print(b);}
static int Motor_SetState(uint8_t m,uint8_t s){motor_calls++;return motor_fail?2:HAL_OK;}
static void ShowCurrentState(void){applied++;}
static void ResetControlTransport(void){bt_rx_line_length=0;}
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
static void reset(const char *data,double pace,int changed){wire=data;wirepos=0;wirelen=(unsigned)strlen(data);now_ms=0;next_arrival=pace;spacing=pace;reg_full=0;dropped=0;applied=0;motor_calls=0;bt_rx_line_length=0;memset(current_cells,0,10);memset(current_motor_state,changed?255:0,20);}
static void pump(void){for(int i=0;i<3000 && (wirepos<wirelen || reg_full);i++){PumpBluetoothInput();advance(1);}}
int main(void){
 const char *frame="FRAME,0,1,0,0,88,0,0,0,0,0,0,0,0,0,0\n";
 char train[256];snprintf(train,sizeof(train),"ACK,1\n%s%s",frame,frame);
 for(int changed=0;changed<=1;changed++)for(int pace=0;pace<2;pace++){reset(train,pace?20:10.0/9.6,changed);pump();printf("transport changed=%d pace_ms=%.5f dropped=%u applied=%u motor_calls=%u\n",changed,spacing,dropped,applied,motor_calls);}
 debug_timing=0;
 char oversize[512];memset(oversize,'X',256);strcpy(oversize+256,frame);reset(oversize,20,0);pump();printf("overflow_suffix_applied=%u\n",applied);
 reset("",20,0);char invalid[]="FRAME,9,8,7,6,123,1,2,3,4,5,6,7,8,9,64";int accepted=ParseAndApplyFrame(invalid);printf("invalid_accepted=%d nav_generation=%u partial_first_cell=%u last_cell=%u\n",accepted,nav_state.generation,current_cells[0],current_cells[9]);
 reset("",20,0);char empty[]="FRAME,,0,1,0,0,88,0,0,0,0,0,0,0,0,0,0";printf("empty_field_accepted=%u\n",ParseAndApplyFrame(empty));
 reset("",20,1);motor_fail=1;char zero[]="FRAME,0,1,0,0,88,0,0,0,0,0,0,0,0,0,0";accepted=ParseAndApplyFrame(zero);printf("i2c_all_fail_accepted=%d printed_state=%u motor_calls=%u motor_state0=%u\n",accepted,applied,motor_calls,current_motor_state[0]);
 return 0;
}

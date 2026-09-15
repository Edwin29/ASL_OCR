
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <limits.h>
#include <errno.h>
#include <assert.h>
typedef enum {HAL_OK, HAL_ERROR} HAL_StatusTypeDef;
typedef struct {uint16_t page,node,span,offset; uint32_t generation;} NavigationState;
static NavigationState nav_state;
static uint8_t current_motor_state[20],current_cells[10],last_frame_apply_ok;
static uint32_t pca_apply_failures,last_applied_generation;
static uint16_t values[2][10],last_addr,last_channel;
static unsigned writes,delay_ms;
static int fail_channel=-1;
static HAL_StatusTypeDef PCA_SetPWM(uint16_t addr,uint8_t ch,uint16_t value){
  unsigned b=addr==(0x41U<<1)?0:1;
  assert(addr==(0x41U<<1)||addr==(0x40U<<1)); assert(ch<10);
  last_addr=addr;last_channel=ch;writes++;
  if(b==0 && ch==fail_channel)return HAL_ERROR;
  values[b][ch]=value;return HAL_OK;
}
static void HAL_Delay(unsigned ms){delay_ms+=ms;}
static void ShowCurrentState(void){}
#define GPIOA 0
#define GPIOB 1
#define GPIOC 2
#define GPIO_PIN_0 1U
#define GPIO_PIN_1 2U
#define GPIO_PIN_2 4U
#define GPIO_PIN_4 16U
#define GPIO_PIN_8 256U
#define GPIO_MODE_INPUT 1
#define GPIO_PULLUP 1
#define __HAL_RCC_GPIOA_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOB_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOC_CLK_ENABLE() ((void)0)
typedef struct {unsigned Pin,Mode,Pull;} GPIO_InitTypeDef;
static unsigned gpio_masks[3];
static void HAL_GPIO_Init(unsigned port,GPIO_InitTypeDef *init){
 assert(init->Mode==GPIO_MODE_INPUT && init->Pull==GPIO_PULLUP);gpio_masks[port]|=init->Pin;
}
#define PCA1_ADDR               (0x41U << 1)
#define PCA2_ADDR               (0x40U << 1)
#define MOTOR_COUNT             20U
#define BRAILLE_CELL_COUNT      10U
#define SERVO_FREQ_HZ           50U
#define SERVO_CAL_POSITIONS     9U
#define SERVO_BATCH_SIZE        4U
#define SERVO_BATCH_DELAY_MS    100U
static const uint16_t PCA1_SERVO_LUT_US[10][SERVO_CAL_POSITIONS] =
{
    { 513U, 674U, 1001U, 1191U, 1558U, 1729U, 1997U, 2183U, 2358U },
    { 513U, 781U, 1030U, 1270U, 1587U, 1797U, 2046U, 2261U, 2437U },
    { 513U, 752U,  986U, 1167U, 1519U, 1704U, 2021U, 2231U, 2461U },
    { 513U, 586U,  957U, 1079U, 1475U, 1582U, 2011U, 2163U, 2329U },
    { 513U, 728U, 1001U, 1192U, 1470U, 1719U, 2080U, 2207U, 2422U },
    { 513U, 640U,  923U, 1099U, 1450U, 1675U, 1982U, 2168U, 2391U },
    { 513U, 718U, 1055U, 1279U, 1558U, 1787U, 2080U, 2310U, 2554U },
    { 513U, 693U,  952U, 1118U, 1421U, 1680U, 1973U, 2173U, 2446U },
    { 513U, 751U,  977U, 1201U, 1533U, 1831U, 2026U, 2280U, 2554U },
    { 513U, 605U, 1006U, 1133U, 1455U, 1727U, 2021U, 2153U, 2437U }
};
static const uint16_t PCA2_SERVO_LUT_US[10][SERVO_CAL_POSITIONS] =
{
    { 513U, 723U,  972U, 1118U, 1485U, 1689U, 2002U, 2222U, 2480U },
    { 513U, 723U,  972U, 1201U, 1553U, 1831U, 2134U, 2280U, 2480U },
    { 513U, 835U, 1050U, 1270U, 1616U, 1885U, 2075U, 2370U, 2431U },
    { 513U, 659U,  889U, 1162U, 1489U, 1774U, 2075U, 2319U, 2518U },
    { 513U, 864U, 1133U, 1396U, 1636U, 1963U, 2236U, 2422U, 2598U },
    { 513U, 762U, 1040U, 1287U, 1533U, 1880U, 2168U, 2314U, 2529U },
    { 513U, 711U, 1060U, 1240U, 1646U, 1934U, 2163U, 2339U, 2588U },
    { 513U, 718U,  996U, 1161U, 1455U, 1836U, 2163U, 2295U, 2515U },
    { 513U, 840U, 1152U, 1362U, 1636U, 1938U, 2236U, 2432U, 2588U },
    { 513U, 664U,  947U, 1147U, 1396U, 1694U, 2036U, 2202U, 2432U }
};static const uint8_t SERVO_STATE_LUT[8] =
{
    0U, 1U, 2U, 3U,
    4U, 5U, 6U, 7U
};
static const uint8_t BOTTOM_REVERSE_LUT[8] =
{
    0U, 4U, 2U, 6U,
    1U, 5U, 3U, 7U
};static const unsigned measured[20][9]={{513,674,1001,1191,1558,1729,1997,2183,2358},{513,781,1030,1270,1587,1797,2046,2261,2437},{513,752,986,1167,1519,1704,2021,2231,2461},{513,586,957,1079,1475,1582,2011,2163,2329},{513,728,1001,1192,1470,1719,2080,2207,2422},{513,640,923,1099,1450,1675,1982,2168,2391},{513,718,1055,1279,1558,1787,2080,2310,2554},{513,693,952,1118,1421,1680,1973,2173,2446},{513,751,977,1201,1533,1831,2026,2280,2554},{513,605,1006,1133,1455,1727,2021,2153,2437},{513,723,972,1118,1485,1689,2002,2222,2480},{513,723,972,1201,1553,1831,2134,2280,2480},{513,835,1050,1270,1616,1885,2075,2370,2431},{513,659,889,1162,1489,1774,2075,2319,2518},{513,864,1133,1396,1636,1963,2236,2422,2598},{513,762,1040,1287,1533,1880,2168,2314,2529},{513,711,1060,1240,1646,1934,2163,2339,2588},{513,718,996,1161,1455,1836,2163,2295,2515},{513,840,1152,1362,1636,1938,2236,2432,2588},{513,664,947,1147,1396,1694,2036,2202,2432}};

static HAL_StatusTypeDef Motor_SetState(uint8_t motor, uint8_t state)
{
    uint16_t pca_addr;
    uint8_t channel;
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

    /* Keep logical state/bit ordering; use the measured pulse for this motor. */
    pulse_us = (motor < 10U) ? PCA1_SERVO_LUT_US[channel][state]
                             : PCA2_SERVO_LUT_US[channel][state];

    pwm_count =
        (pulse_us * 4096U * SERVO_FREQ_HZ) /
        1000000U;

    return PCA_SetPWM(pca_addr, channel, (uint16_t)pwm_count);
}
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
         * Reverse logical cell order only. Calibration stays attached to
         * its measured physical motor/PCA channel.
         */
        uint8_t top_motor = (uint8_t)(BRAILLE_CELL_COUNT - 1U - i);
        uint8_t bottom_motor = (uint8_t)(10U + top_motor);

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

    /* PB0 = RIGHT, PB1 = PAGE NEXT, PB2 = PAGE PREVIOUS */
    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* PC0 = CONFIRM, PC8 = MODE LEVER */
    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_8;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
}
static void reset_fixture(void){
 memset(current_motor_state,255,20);memset(current_cells,0,10);memset(&nav_state,0,sizeof(nav_state));
 memset(values,0,sizeof(values));last_frame_apply_ok=0;last_applied_generation=0;pca_apply_failures=0;writes=0;fail_channel=-1;
}
int main(void){
 unsigned m,s,c,bits,prior,n;
 unsigned reverse[8]={0,4,2,6,1,5,3,7};
 char frame[256];
 reset_fixture(); MX_GPIO_Init();
 assert(gpio_masks[0]==19 && gpio_masks[1]==7 && gpio_masks[2]==257);
 for(m=0;m<20;m++)for(s=0;s<8;s++){
   assert(Motor_SetState((uint8_t)m,(uint8_t)s)==HAL_OK);
   assert(last_addr==(m<10?(0x41U<<1):(0x40U<<1)) && last_channel==m%10);
   assert(values[m/10][m%10]==(measured[m][s]*4096U*50U)/1000000U);
 }
 prior=writes; assert(Motor_SetState(20,0)==HAL_ERROR && Motor_SetState(0,8)==HAL_ERROR && writes==prior);
 for(c=0;c<10;c++)for(bits=0;bits<64;bits++){
   reset_fixture(); strcpy(frame,"FRAME,1,2,3,4,99");
   for(n=0;n<10;n++)sprintf(frame+strlen(frame),",%u",n==c?bits:0);
   assert(ParseAndApplyFrame(frame)); assert(last_frame_apply_ok && last_applied_generation==99 && writes==20);
   for(n=0;n<10;n++){
     unsigned left=n==(9-c)?(bits&7):0,right=n==(9-c)?reverse[bits>>3]:0;
     assert(values[0][n]==(measured[n][left]*4096U*50U)/1000000U);
     assert(values[1][n]==(measured[10+n][right]*4096U*50U)/1000000U);
   }
 }
 reset_fixture();fail_channel=3; memset(current_cells,63,10);
 assert(!ApplyBrailleFrame(current_cells));assert(pca_apply_failures==1 && current_motor_state[3]==255);
 fail_channel=-1;prior=writes;assert(ApplyBrailleFrame(current_cells) && writes==prior+1);
 prior=writes;assert(ApplyBrailleFrame(current_cells) && writes==prior);
 memset(current_cells,0,10);assert(ApplyBrailleFrame(current_cells));
 for(n=0;n<20;n++)assert(values[n/10][n%10]==(measured[n][0]*4096U*50U)/1000000U);
 prior=writes;assert(ApplyBrailleFrame(current_cells) && writes==prior);
 {
 const char *bad[]={"FRAME,1,,2,3,4,5,0,0,0,0,0,0,0,0,0,0", "FRAME,65536,0,0,0,1,0,0,0,0,0,0,0,0,0,0",
 "FRAME,0,0,0,0,4294967296,0,0,0,0,0,0,0,0,0,0", "FRAME,0,0,0,0,1,-1,0,0,0,0,0,0,0,0,0",
 "FRAME,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,", "FRAME,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,1",
 "FRAME,0,0,0,0,1,64,0,0,0,0,0,0,0,0,0"};
 for(n=0;n<sizeof(bad)/sizeof(bad[0]);n++){
   NavigationState saved=nav_state;uint8_t cells[10];memcpy(cells,current_cells,10);prior=writes;strcpy(frame,bad[n]);
   assert(!ParseAndApplyFrame(frame));assert(!memcmp(&saved,&nav_state,sizeof(saved)) && !memcmp(cells,current_cells,10) && writes==prior);
 }
 }
 puts("PASS: 160 motor states, 640 cell patterns, GPIO masks, 7 malformed frames, failed-channel-only retry, high-to-clear index0, cache");
 return 0;
}

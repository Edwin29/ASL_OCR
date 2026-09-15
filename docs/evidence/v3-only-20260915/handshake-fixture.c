
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#define VERSIONED_HANDSHAKE_TIMEOUT_MS 1200U
#define HAL_OK 0
#define GPIO_PIN_RESET 0
#define MODE_LEVER_PORT 0
#define MODE_LEVER_PIN 0
typedef int GPIO_PinState;
static uint8_t bt_protocol_v2,bt_protocol_v3,bt_connected;
static struct {int last_raw,stable_state;uint32_t last_change_time;} button_mode_lever;
static int huart1,scenario,tx,reads,started,mode_sent,junk;
static uint32_t tick;
static void ResetControlTransport(void){}
static uint32_t HAL_GetTick(void){return tick;}
static void Debug_Print(const char *s){}
static int HAL_UART_Transmit(int *h,uint8_t *data,uint16_t len,uint32_t timeout){
 assert(len==8 && !memcmp(data,"HELLO,3\n",8));tx++;return HAL_OK;
}
static uint8_t HC05_ReadLine(char *line,uint16_t size,uint32_t timeout){
 reads++;
 if(scenario==1 || (scenario==2 && tx==2) || (scenario==3 && junk++>0)){
  tick+=10;strcpy(line,"ACK,HELLO,3");return 1;
 }
 if(scenario==3 || scenario==4){tick+=100;strcpy(line,"ACK,HELLO,2");return 1;}
 tick+=timeout;return 0;
}
static void StartBluetoothInterruptReceive(void){started++;}
static GPIO_PinState HAL_GPIO_ReadPin(int p,int n){return 1;}
static uint8_t SendControlAction(char c,char a){assert(c=='V' && a=='R');mode_sent++;return 1;}
static void ServiceControlTransmit(void){}
static uint8_t TryBluetoothHandshake(void)
{
    static const char hello_v3[] = "HELLO,3\n";
    char line[64];
    GPIO_PinState lever_state;
    uint8_t attempt;

    ResetControlTransport();
    bt_protocol_v2 = 0U;
    bt_protocol_v3 = 0U;
    bt_connected = 0U;
    /* Production is V3-only. Each attempt has a fixed total deadline;
     * unrelated/late lines never renew it. The outer loop retries later. */
    for (attempt = 0U; attempt < 3U && !bt_connected; attempt++)
    {
        uint32_t started;
        Debug_Print("BT: HELLO V3...\r\n");
        if (HAL_UART_Transmit(&huart1, (uint8_t *)hello_v3,
                              (uint16_t)(sizeof(hello_v3) - 1U), 1000U) != HAL_OK)
            continue;
        started = HAL_GetTick();
        while (!bt_connected)
        {
            uint32_t elapsed = HAL_GetTick() - started;
            uint32_t remaining;
            if (elapsed >= VERSIONED_HANDSHAKE_TIMEOUT_MS)
                break;
            remaining = VERSIONED_HANDSHAKE_TIMEOUT_MS - elapsed;
            if (!HC05_ReadLine(line, sizeof(line), remaining))
                break;
            if (strcmp(line, "ACK,HELLO,3") == 0)
            {
                bt_protocol_v2 = 1U; /* Shared asynchronous transport machinery. */
                bt_protocol_v3 = 1U;
                bt_connected = 1U;
                break;
            }
        }
    }
    if (!bt_connected)
    {
        Debug_Print("BT: V3 REQUIRED, WAITING FOR LINK\r\n");
        return 0U;
    }
    Debug_Print("BT: HOST CONNECTED (V3 EDGES)\r\n");

    if (bt_protocol_v2)
        StartBluetoothInterruptReceive();

    lever_state = HAL_GPIO_ReadPin(MODE_LEVER_PORT, MODE_LEVER_PIN);
    button_mode_lever.last_raw = lever_state;
    button_mode_lever.stable_state = lever_state;
    button_mode_lever.last_change_time = HAL_GetTick();
    if (!SendControlAction('V', (lever_state == GPIO_PIN_RESET) ? 'A' : 'R'))
        return 0U;
    ServiceControlTransmit();
    return 1U;
}
int main(void){
 for(int test=0;test<6;test++){
  scenario=test==5?1:test;tx=reads=started=mode_sent=junk=0;
  tick=test==5?0xfffffff8U:0;
  int ok=TryBluetoothHandshake();
  assert(ok==(test==1||test==2||test==3||test==5));
  assert(tx==(test==0||test==4?3:test==2?2:1));
  assert(started==ok && mode_sent==ok && bt_protocol_v3==ok);
  if(!ok)assert(tick==3600 && !bt_connected);
 }
 puts("PASS: no host, immediate V3, missed first HELLO, unrelated ACK then V3, V2-only rejection, clock rollover");
 return 0;
}

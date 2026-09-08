"""Compile verbatim exercised firmware functions against deterministic fake HAL."""
import pathlib,re,subprocess,json,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[3];OUT=pathlib.Path(__file__).resolve().parent
src=(ROOT/'hardware/stm32/kitel2026final/Core/Src/main.c').read_text(encoding='utf-8')
def function(name):
 m=re.search(r'static (?:void|uint8_t) '+name+r'\([^;]*?\)\s*\{',src);assert m,name
 start=m.start();pos=m.end();depth=1
 while depth:
  depth+=(src[pos]=='{')-(src[pos]=='}');pos+=1
 return src[start:pos]
names=['ApplyBrailleFrame','ParseAndApplyFrame','ProcessHostLine','PumpBluetoothInput']
prefix=r'''
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
'''
suffix=r'''
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
'''
target=OUT/'firmware_extracted_probe.c';target.write_text(prefix+'\n\n'.join(function(n) for n in names)+suffix,encoding='utf-8')
vc=pathlib.Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat')
command=f'@echo off\ncall "{vc}" >nul\ncl /nologo /W3 /Fe:firmware_extracted_probe.exe firmware_extracted_probe.c\nif errorlevel 1 exit /b 1\nfirmware_extracted_probe.exe\n'
(OUT/'build-probe.cmd').write_text(command,encoding='utf-8')
p=subprocess.run(['cmd','/d','/c','build-probe.cmd'],cwd=OUT,capture_output=True,text=True)
(OUT/'firmware-probe-output.txt').write_text(p.stdout+p.stderr,encoding='utf-8')
(OUT/'firmware-probe-identity.json').write_text(json.dumps({'source_sha256':hashlib.sha256((ROOT/'hardware/stm32/kitel2026final/Core/Src/main.c').read_bytes()).hexdigest(),'functions':names,'compiler':'MSVC 14.43.34808 x64','exit_code':p.returncode,'model_limits':'single unread UART data register; ideal wire; mock I2C; no radio/ORE measurement; ShowCurrentState time omitted'},indent=2),encoding='utf-8')
print(p.stdout+p.stderr)
raise SystemExit(p.returncode)

"""Compile exact production actuator/parser/GPIO bodies with HAL stubs; no hardware IO."""
import hashlib, json, os, re, subprocess
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PROJECT=ROOT/'hardware/stm32/kitel2026final'
source=(PROJECT/'Core/Src/main.c').read_text(encoding='utf-8')
before=(OUT/'main-before-mapping.c').read_text(encoding='utf-8')
handoff=json.loads((ROOT/'docs/evidence/hardware-handoff-20260914/inspection.json').read_text(encoding='utf-8'))
def function(text,name):
    m=re.search(r'^(?:static )?(?:void|uint8_t|HAL_StatusTypeDef) '+name+r'\([^;]*?\)\s*\{',text,re.M)
    assert m,name
    at=text.index('{',m.start()); depth=1; end=at+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}'); end+=1
    return text[m.start():end]
preserved=['ParseAndApplyFrame','PumpBluetoothInput','BluetoothUartIrqHandler',
           'BluetoothRxPushToken','BluetoothRxHandleByte','ServiceControlTransmit','ProcessHostLine',
           'ButtonPollStep','ButtonPollEdge','ButtonPollConfirm','ModeLeverPoll','TryBluetoothHandshake']
assert all(function(source,n)==function(before,n) for n in preserved)
table_defs=[]; expected=[]
for name in ['PCA1_SERVO_LUT_US','PCA2_SERVO_LUT_US']:
    block=re.search(r'static const uint16_t '+name+r'\[10\]\[SERVO_CAL_POSITIONS\]\s*=\s*\{.*?\};',source,re.S)[0]
    rows=[[int(n) for n in re.findall(r'(\d+)U',r)] for r in re.findall(r'\{([^{}]+)\}',block)]
    assert rows==handoff['calibration'][name]['rows']
    expected+=rows; table_defs.append(block)
header=(PROJECT/'Core/Inc/main.h').read_text(encoding='utf-8')
ioc=dict(line.split('=',1) for line in (PROJECT/'kitel2026final.ioc').read_text().splitlines() if '=' in line)
for label,pin in [('PAGE_PREVIOUS','PB2'),('CONFIRM','PC0'),('MODE_LEVER','PC8')]:
    assert ioc[pin+'.GPIO_Label']==label
    assert re.search(r'#define '+label+r'_Pin GPIO_PIN_'+pin[2:]+r'\b',header)
    assert re.search(r'#define '+label+r'_GPIO_Port GPIO'+pin[1]+r'\b',header)
assert 'PC1.Signal' not in ioc and 'PC2.Signal' not in ioc
pinlist=[v for k,v in ioc.items() if re.fullmatch(r'Mcu.Pin\d+',k)]
assert len(pinlist)==len(set(pinlist))==int(ioc['Mcu.PinsNb'])
defines='\n'.join(line for line in source.splitlines() if re.match(r'#define (PCA[12]_ADDR|SERVO_FREQ_HZ|SERVO_CAL_POSITIONS|MOTOR_COUNT|BRAILLE_CELL_COUNT|SERVO_BATCH_SIZE|SERVO_BATCH_DELAY_MS)\b',line))
luts='\n'.join(re.search(r'static const uint8_t '+n+r'\[8\]\s*=\s*\{.*?\};',source,re.S)[0] for n in ['SERVO_STATE_LUT','BOTTOM_REVERSE_LUT'])
prefix=r'''
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
'''
expected_c='static const unsigned measured[20][9]={'+','.join('{'+','.join(map(str,row))+'}' for row in expected)+'};\n'
main=r'''
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
'''
fixture=prefix+defines+'\n'+'\n'.join(table_defs)+luts+expected_c+'\n'+'\n'.join(function(source,n) for n in ['Motor_SetState','ApplyBrailleFrame','ParseAndApplyFrame','MX_GPIO_Init'])+main
folder=OUT/'fixture';folder.mkdir(exist_ok=True)
(folder/'fixture.c').write_text(fixture,encoding='utf-8')
vc=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC')
setup=subprocess.run(f'cmd /d /s /c "call "{vc / "Auxiliary/Build/vcvars64.bat"}" >nul && set"',capture_output=True,text=True,errors='replace',check=True)
env=os.environ.copy()
for line in setup.stdout.splitlines():
 if '=' in line and not line.startswith('='):
  k,v=line.split('=',1);env[k]=v
compiler=vc/'Tools/MSVC/14.43.34808/bin/Hostx64/x64/cl.exe'
build=subprocess.run([str(compiler),'/nologo','/W3','/D_CRT_SECURE_NO_WARNINGS','fixture.c','/Fe:fixture.exe'],cwd=folder,env=env,capture_output=True,text=True,errors='replace')
(folder/'build.txt').write_text(build.stdout+build.stderr,encoding='utf-8')
run=None if build.returncode else subprocess.run([str(folder/'fixture.exe')],cwd=folder,capture_output=True,text=True)
record={'compiler':str(compiler),'source_sha256':hashlib.sha256((PROJECT/'Core/Src/main.c').read_bytes()).hexdigest(),
 'measurement_values_exact_match':180,'unchanged_functions':preserved,'gpio_header_ioc_consistent':True,
 'compile_exit':build.returncode,'run_exit':None if run is None else run.returncode,'stdout':None if run is None else run.stdout,
 'stderr':None if run is None else run.stderr,'target':'Windows x64 extracted production C / HAL stubs, not physical proof'}
(OUT/'fixture-result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2));assert build.returncode==0 and run is not None and run.returncode==0


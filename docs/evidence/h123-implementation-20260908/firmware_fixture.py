"""Compile exact current C bodies with HAL stubs; never flash or open hardware."""
import hashlib,json,os,pathlib,re,subprocess,sys
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
source=(ROOT/'hardware/stm32/kitel2026final/Core/Src/main.c').read_text(encoding='utf-8')
label=sys.argv[1]
out=HERE/('firmware-'+label)
out.mkdir(exist_ok=False)
def function(name):
    match=re.search(r'static (?:void|uint8_t) '+name+r'\([^;]*?\)\s*\{',source)
    assert match,name
    start=match.start(); at=source.index('{',match.start()); depth=1; at+=1
    while depth:
        if source[at]=='{':depth+=1
        elif source[at]=='}':depth-=1
        at+=1
    return source[start:at]
funcs={name:function(name) for name in ['ApplyBrailleFrame','ParseAndApplyFrame','PumpBluetoothInput']}
luts='\n'.join(re.search(r'static const uint8_t '+name+r'\[8\]\s*=\s*\{.*?\};',source,re.S).group() for name in ['SERVO_STATE_LUT','BOTTOM_REVERSE_LUT'])
prefix=r'''
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
'''
extras='\n'.join(line for line in source.splitlines() if re.match(r'static (?:volatile )?(?:uint8_t|uint32_t) (?:bt_rx_discarding|last_frame_apply_ok|pca_apply_failures|last_applied_generation)\b',line))
main=r'''
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
'''
if 'last_frame_apply_ok' in extras:
    main+=r'''printf(",\"last_frame_apply_ok\":%u,\"pca_apply_failures\":%lu",last_frame_apply_ok,(unsigned long)pca_apply_failures);'''+'\n'
    main+=r'''
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
'''
main+='puts("}");return 0;}\n'
fixture=prefix+luts+'\n'+extras+'\n'+'\n'.join(funcs.values())+'\n'+main
(out/'fixture.c').write_text(fixture,encoding='utf-8')
vcvars=r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'
# Capture the build environment in memory only; never log environment secrets.
setup=subprocess.run('cmd /d /s /c "call "'+vcvars+'" >nul && set"',capture_output=True,text=True,encoding='utf-8',errors='replace',check=True)
env=os.environ.copy()
for line in setup.stdout.splitlines():
    if '=' in line and not line.startswith('='):
        key,value=line.split('=',1);env[key]=value
compiler=r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.43.34808\bin\Hostx64\x64\cl.exe'
build=subprocess.run([compiler,'/nologo','/W3','/D_CRT_SECURE_NO_WARNINGS','fixture.c','/Fe:fixture.exe'],cwd=out,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
(out/'build.txt').write_text(build.stdout+build.stderr,encoding='utf-8')
if build.returncode:print(build.stdout+build.stderr);raise SystemExit(build.returncode)
run=subprocess.run([str((out/'fixture.exe').resolve())],capture_output=True,text=True,check=True)
result={'compiler':compiler,'target':'Windows x64 / uint32 unsigned long; HAL stubs, not STM board execution',
        'function_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in funcs.items()},
        'result':json.loads(run.stdout)}
if label.startswith('after'):
    actual=result['result']
    assert actual['invalid_rejected']==1 and actual['rejected_state_mutated']==0
    assert actual['overflow_suffix_dispatched']==0 and actual['valid_parse_accepted']==1
    assert actual['last_frame_apply_ok']==0 and actual['pca_apply_failures']==20
    assert actual['malformed_atomic_cases']==6
    assert actual['same_frame_bus_recovery'] and actual['unchanged_motor_cache']
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))

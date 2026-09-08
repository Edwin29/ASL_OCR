"""Source-derived models, NOT a compiled MCU/driver or electrical reproduction."""
import pathlib,re,json
source=pathlib.Path(__file__).resolve().parents[3]/'hardware/stm32/kitel2026final/Core/Src/main.c'
text=source.read_text(encoding='utf-8')
def constant(name):return int(re.search(r'#define\s+'+name+r'\s+(\d+)U',text)[1])
capacity=constant('BT_RX_LINE_SIZE')
frame='FRAME,0,17,0,0,111,'+','.join(['0']*10)
line='';accepted=[];overflow=0
for ch in 'X'*capacity+frame+'\n':
 if ch=='\r':continue
 if ch=='\n':accepted.append(line);line='';continue
 if len(line)>=capacity-1:line='';overflow+=1;continue
 line+=ch
assert accepted==[frame]

# One receive data slot and perfect service outside the specified blocking span.
# Not a claim about actual ORE count or HC-05 scheduling.
def receive_model(block_ms):
 interval=1000*10/constant('HC05_UART_BAUD')
 pending=None;received=[];loss=0
 for i,ch in enumerate(frame+'\n'):
  at=i*interval
  if at>=block_ms and pending is not None:received.append(pending);pending=None
  if pending is not None:loss+=1
  else:pending=ch
 if pending is not None:received.append(pending)
 return {'blocking_ms':block_ms,'lost_bytes_in_model':loss,'received':''.join(received)}
out={'scope':'behavioral models only; firmware unchanged, no physical transmission',
     'constants':{n:constant(n) for n in ['HC05_UART_BAUD','DEBUG_UART_BAUD','BT_RX_LINE_SIZE','SERVO_BATCH_SIZE','SERVO_BATCH_DELAY_MS']},
     'overflow_suffix':{'overflow_events':overflow,'unexpected_accepted_suffix':accepted},
     'receive_models':[receive_model(0),receive_model(len('BT: HOST CONNECTED (V3 EDGES)\r\n')*1000*10/constant('DEBUG_UART_BAUD')),receive_model(5*constant('SERVO_BATCH_DELAY_MS'))],
     'limitations':['No compiled C/HAL execution','No measured UART ORE/FE/NE','No direct UART versus HC-05 comparison','No assertion of actual servo pulse or physical state']}
print(json.dumps(out,indent=2))

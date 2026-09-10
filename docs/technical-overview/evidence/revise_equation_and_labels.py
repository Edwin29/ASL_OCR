"""Documentation-only equation and bilingual-label revision."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[3]
doc=root/'docs/ASL_OCR_TECHNICAL_OVERVIEW.md'
s=(root/'docs/technical-overview/EQUATION_REVISION_BEFORE.md.snapshot').read_text(encoding='utf-8-sig')
start=s.index('분수 표기에는')
end=s.index('```mermaid',start)
s=s[:start]+'''방정식 `(x+1)^2=9`에는 등호 양쪽의 관계, 괄호로 묶은 덧셈, 그 전체를 밑으로 하는 거듭제곱이 있다. 수식 구조 트리(AST)는 최상위의 등호 관계(Relation), 왼쪽의 제곱(Power), 그 밑의 괄호 구조(Parenthesized)와 오른쪽 숫자(Number)를 구분한다. 따라서 제곱이 1에만 붙는지, 괄호 전체에 붙는지를 출력기마다 문자열에서 다시 추측할 필요가 없다.

현재 음성 규칙(speech rules)은 ‘괄호 열고 x 더하기 1 괄호 닫고의 2 제곱은 9와 같다’라는 문자열을 만든다. 점자 변환기(math_translator)는 같은 구조에서 13칸의 점자값을 만든다. 아래 도식은 구조의 주요 노드와 두 출력 경로를 보여 주며, 괄호 안의 개별 x·+·1 노드는 줄여 표시했다. 방정식의 해를 계산하는 도식은 아니다.

'''+s[end:]
diagrams=list(re.finditer(r'```mermaid\n([\s\S]*?)```',s))
ast='''flowchart TD
    Input["방정식 문자열<br/>(LaTeX)<br/>(x+1)^2=9"] --> Root["등호 관계<br/>(Relation)"]
    Root --> Left["왼쪽 거듭제곱<br/>(Power)"]
    Root --> Right["오른쪽 숫자 9<br/>(Number)"]
    Left --> Base["밑: 괄호 안 x+1<br/>(Parenthesized / Row)"]
    Left --> Exponent["지수: 숫자 2<br/>(Number)"]
    Root --> Speech["음성 규칙<br/>(math_rules)"]
    Root --> Braille["점자 변환<br/>(math_translator)"]
    Speech --> Words["방정식을 읽을 문장<br/>(spoken text)"]
    Braille --> Cells["13칸의 논리 점자값<br/>(braille cells)"]
    Cells --> Window["10칸 + 3칸의 두 창<br/>(viewport / offset)"]
'''
m=diagrams[3]
s=s[:m.start()]+'```mermaid\n'+ast+'```'+s[m.end():]
start=s.index('### ‘2분의 1’')
end=s.index('### 같은 작은 페이지',start)
s=s[:start]+'''### 방정식이 음성과 두 점자 창으로 바뀌는 예

사진 대신 방정식 `(x+1)^2=9`를 나타내는 문자열을 넣어 현재 코드의 변환 결과를 확인했다. [방정식 실행 기록](technical-overview/evidence/equation-examples.json)에 원문·구조·발화·점자 창을 보존했다. 실제 음성 합성이나 모터 동작 시험은 아니다.

| 단계 | 독자가 이해할 결과 | 기존 용어·코드 표기 |
|---|---|---|
| 수식 입력 | 괄호 안 x+1 전체를 제곱한 값이 9와 같음 | LaTeX `(x+1)^2=9` |
| 구조 해석 | 등호의 왼쪽은 괄호 전체의 제곱, 오른쪽은 숫자9. 오류·남은 기호 없음 | Relation → Power / Number, 밑은 Parenthesized, 상태 VALID |
| 음성용 문장 | ‘괄호 열고 x 더하기 1 괄호 닫고의 2 제곱은 9와 같다’ | speech rule output. x의 최종 발음 정리·Piper 합성 전 문자열 |
| 점자용 정보 | 전체 13칸의 점 위치를 생성 | `[38,45,34,60,1,52,24,60,3,18,18,60,10]` |
| 첫 번째 표시 창 | 앞의10칸, 다음 창 있음 | viewport=10, offset=0, cells=`[38,45,34,60,1,52,24,60,3,18]` |
| 오른쪽으로 창 이동 | 시작 위치10에서 나머지3칸, 다음 창 없음 | offset=10, cells=`[18,60,10]` |
| 장치 전달 형태 | 두 번째 창의 빈7칸을 0으로 채움 | `[18,60,10,0,0,0,0,0,0,0]`. 전송 형식 설명이며 실제 선로에 보내지 않음 |

숫자 배열은 각 칸의 여섯 점 중 올릴 점을 표현한 값이다. 현재 창은 점자칸 수를 기준으로 자르므로 하나의 기호가 쓰는 여러 칸이 창 경계에 걸릴 수도 있다. 이 예에서는 등호의 두 칸이 두 창에 나뉜다. 수학 기호마다 한 창 안에 온전히 넣는 별도의 줄바꿈 기능이 있다고 해석해서는 안 된다.

시스템은 방정식의 해를 계산해서 읽는 것이 아니라, 주어진 식의 구조를 발화와 점자값으로 옮긴다. 논리적인 값 생성과 실제 청취·핀 적용도 별개다. 지원하지 않는 기호가 있거나 식이 덜 끝난 경우는 아래의 불완전한 방정식 예와 비교할 수 있다.

'''+s[end:]
s=s.replace('지문·분수·선택지가','지문·방정식·선택지가').replace('분수 표기,','방정식 표기,').replace('분수의 AST,','방정식의 AST,')
s=s.replace('문제표식, ‘다음 분수의 분모를 고르시오.’라는 지문, 분수½,','문제표식, ‘다음 방정식의 양의 해를 고르시오.’라는 지문, 방정식 `(x+1)^2=9`,')
s=s.replace('수식에는 분자·분모 구조를 저장','수식에는 등호·괄호·거듭제곱 구조를 저장')
s=s.replace('| 분수½의 정상 표기 | 해석 완료, ‘2분의 1’ | 다섯 칸 생성 |','| `(x+1)^2=9` | 해석 완료(VALID), 괄호와 제곱을 포함한 방정식을 읽을 문장 | 13칸 생성 |')
s=s.replace('| x 더하기 미지원 명령 | 일부 해석, 불확실 안내와 해석 가능한 부분 | 비움 |','| `(x+\\unsupported)^2=9` | 일부 해석(PARTIAL), 불확실 안내와 해석 가능한 부분 | 비움 |')
s=s.replace('| 분수 명령 뒤 괄호가 끝나지 않은 표기 | 해석 실패, ‘수식 인식이 불확실합니다.’ | 비움 |','| `(x+1)^2=` | 해석 실패(INVALID), ‘수식 인식이 불확실합니다.’ | 비움 |')
s=s.replace('(technical-overview/evidence/core-principles-examples.json)','(technical-overview/evidence/equation-examples.json)')

# Diagram labels use short Korean lines plus exact or conventional terms.
labels={
'휴대폰 카메라':'휴대폰 카메라<br/>(Android IP Camera)', '노트북 단말':'노트북 단말 (Laptop)',
'촬영 판단과 좌우 페이지 보정':'촬영 판단·좌우 보정<br/>(Book Scanner)',
'사용자 입력과 작업 흐름 조정':'입력·작업 흐름 조정<br/>(Device Runtime)',
'전송 보관함':'전송 보관함<br/>(outbox)', '음성 파일 수신과 재생':'음성 수신·재생<br/>(reading_audio)',
'버튼 메시지 수신과 점자값 전송':'버튼 수신·점자 전송<br/>(stm_serial)',
'데스크톱 서버':'데스크톱 서버 (Desktop)', '자료 목록과 읽던 위치 관리':'자료 목록·읽던 위치<br/>(S0 catalog / cursor)',
'촬영 결과 저장과 수신 확인':'촬영 저장·수신 확인<br/>(V4 upload)', '글자 인식과 페이지 구조 해석':'글자 인식·구조 해석<br/>(S1 / PaddleOCR-VL)',
'음성 파일 생성':'음성 파일 생성<br/>(Piper / WAV)', '읽기 자료와 상태 저장소':'자료·상태 저장소<br/>(revision / SQLite)',
'블루투스 모듈 HC-05':'블루투스 모듈<br/>(HC-05)', 'STM32 버튼 입력과 점자 명령 해석':'버튼·점자 명령 해석<br/>(STM32 firmware)',
'모터 제어 보드 PCA9685 두 개':'모터 제어 보드 두 개<br/>(PCA9685)', '서보 20개와 점자 10칸':'서보20개·점자10칸<br/>(servos / cells)',
'계획 중인 Raspberry Pi 4':'이식 계획<br/>(Raspberry Pi 4)',
'새 촬영 후보':'새 촬영 후보<br/>(candidate)', '페이지가 잘 보이고 안정한가?':'품질·안정성 통과?<br/>(quality / stability)',
'안내 후 다시 관측':'안내·재관측<br/>(guidance)', '좌우 하단 인식 문자열 수집':'좌우 문자열 수집<br/>(raw pair)',
'같은 페이지인가?':'같은 페이지인가?<br/>(identity)', '다시 수집하거나 촬영 재시도':'재수집·촬영 재시도<br/>(local retry)',
'동일한 영상에서 좌우 이미지 준비':'동일 영상 좌우 준비<br/>(same-frame L/R)',
'전송한 페이지를 기준으로 변경 대기':'전송한 페이지 기준 대기<br/>(accepted reference)',
'결과 보관과 전송 후 수신 확인':'보관·전송·수신 확인<br/>(outbox / receipt)',
'새 영상과 좌우 문자열 관측':'새 영상·문자열 관측<br/>(preview / raw pair)',
'페이지 변경 판단':'페이지 변경 판단<br/>(page-change)',
'변화 기억을 지우고 다시 관측':'변화 기억 초기화<br/>(latch / rearm)',
'영상 변화 또는 번호 변화가 뒷받침하는가?':'영상 또는 번호 변화?<br/>(visual OR numeric)',
'촬영 원본과 영상 식별자':'촬영 원본·영상 식별자<br/>(frame / frame ID)',
'축소 영상과 페이지 영역 및 품질 정보':'축소 영상·영역·품질<br/>(preview / mask)',
'하단 번호 관측과 중복 판단':'하단 번호·중복 판단<br/>(footer identity)',
'동일한 영상에서 잘라낸 좌우 이미지':'동일 영상의 좌우 추출<br/>(same-frame crops)',
'책장 곡면을 보정한 이미지':'곡면 보정 이미지<br/>(UVDoc / unwarp)',
'촬영 파일 묶음과 검사 정보':'촬영 묶음·검사 정보<br/>(artifact / manifest)',
'전송 보관함과 서버 저장 확인':'보관·서버 저장 확인<br/>(outbox / receipt)',
'페이지별 글자와 수식 및 표 인식':'페이지별 내용 인식<br/>(VL blocks)',
'페이지 중간 표현과 수식 구조':'중간 표현·수식 구조<br/>(Page IR / AST)',
'선택해서 읽을 항목 목록':'선택할 읽기 항목<br/>(AccessiblePage)',
'검사를 마친 페이지와 음성 자료':'검사한 페이지·음성 자료<br/>(READY revision)',
'현재 위치와 음성 조회 키 및 점자 창':'현재 위치·음성 키·점자 창<br/>(reading snapshot)',
'음성 파일에서 스피커 재생까지':'음성 파일·재생<br/>(WAV / PCM)',
'점자 메시지에서 모터와 실제 핀까지':'점자 메시지·모터·핀<br/>(FRAME / PCA)',
'인증 후 영상 한 장 받기':'인증된 영상<br/>(snapshot)', '촬영 결과':'촬영 결과<br/>(artifact)',
'촬영 시작과 종료':'시작·중지<br/>(start / freeze)', '버튼 입력':'버튼 입력<br/>(DeviceInputEvent)',
'현재 읽기 상태':'현재 읽기 상태<br/>(snapshot)', '파일 전송':'파일 전송<br/>(upload)',
'수신 확인서':'수신 확인서<br/>(receipt)', '자료 선택과 탐색':'선택·탐색<br/>(catalog / reading)',
'인증된 음성 파일 요청과 응답':'인증된 음성 조회<br/>(audio_ref / WAV)', '노트북 역할 이식':'단말 이식<br/>(deployment)',
'판단 불가 또는 시간 초과':'판단 불가·시간 초과<br/>(UNKNOWN / timeout)',
'판단 불가':'판단 불가 (UNKNOWN)', '다름':'다름 (DIFFERENT)', '같음':'같음 (SAME)', '처리 허가':'처리 허가 (gate)',
}
def annotate_diagram(m):
    text=m.group(1)
    if text.startswith('flowchart LR'): text=text.replace('flowchart LR','flowchart TD',1)
    for old,new in sorted(labels.items(),key=lambda x:-len(x[0])):
        text=text.replace('"'+old+'"','"'+new+'"')
    if text.startswith('sequenceDiagram'):
        roles={'사용자':'사용자<br/>(User)','단말 흐름 조정':'단말 흐름 조정<br/>(Coordinator)',
               '촬영 판단':'촬영 판단<br/>(Scanner)','서버 수신':'서버 수신<br/>(V4)',
               '서버 페이지 처리':'서버 페이지 처리<br/>(S1)', '서버 읽기 관리':'서버 읽기 관리<br/>(S0)',
               '음성과 점자 출력':'음성·점자 출력<br/>(presenters)'}
        for old,new in roles.items():text=text.replace(' as '+old+'\n',' as '+new+'\n')
        msgs={
         '촬영 모드에서 새 자료 선택':'촬영 모드·새 자료 선택<br/>(capture / datapack)',
         '촬영 시작':'촬영 시작 (scan)', '품질과 중복 검사 후 좌우 이미지 준비':'품질·중복 검사 후 좌우 준비<br/>(candidate / identity / L/R)',
         '촬영 결과 묶음 전달':'촬영 결과 전달 (artifact)', '전송 보관함에 저장':'전송 보관함 저장 (enqueue)',
         '촬영 파일과 검사 정보 전송':'파일·검사 정보 전송<br/>(files / manifest)',
         '저장한 페이지의 처리 작업 등록':'페이지 처리 작업 등록<br/>(fragment)',
         '페이지 해석은 다음 촬영과 독립적으로 진행':'페이지 해석은 다음 촬영과<br/>독립적으로 진행 (worker)',
         '서버 저장 확인 응답':'저장 확인 응답 (receipt)', '수신 확인을 단말에도 저장':'단말 수신 확인 저장<br/>(ack commit)',
         '이 촬영의 전송 완료 통지':'전송 완료 통지<br/>(delivery confirmed)',
         '전송 완료 안내 요청':'전송 완료 안내<br/>(spread_sent)', '페이지가 바뀌었는지 관측':'페이지 변경 관측 (page-change)',
         '확인 버튼 길게 누르기':'확인 길게 (CONFIRM LONG)', '새 촬영 중지':'새 촬영 중지 (freeze)',
         '이번 촬영 범위의 남은 전송 완료 대기':'범위 내 남은 전송 대기<br/>(cutoff / flush)',
         '자료에 포함할 마지막 촬영 순번 확정':'마지막 촬영 순번 확정<br/>(seal / cutoff)',
         '페이지 처리 완료 대기와 음성 생성 및 검사':'페이지 완료·음성 생성·검사<br/>(assembly / validation)',
         '후속 상태 조회에서 읽기 준비 완료 확인':'후속 조회에서 준비 완료 확인<br/>(READY revision)',
         '자료 저장 완료 안내 요청':'자료 저장 완료 안내<br/>(datapack_saved)',
         '완성된 자료 선택과 읽기 조작':'자료 선택·읽기 조작<br/>(reading)',
         '읽던 위치 복구 또는 이동 요청':'위치 복구·이동 요청<br/>(resume / command)',
         '현재 위치와 음성 조회 키 및 점자값':'위치·음성 키·점자값<br/>(cursor / audio_ref / cells)',
         '같은 읽기 상태의 음성과 점자 전달':'같은 읽기 상태의 출력<br/>(generation)',
         '실제 청취와 점자 돌출 상태는 별도 확인':'실제 청취·돌출은 별도 확인<br/>(physical observation)'}
        for old,new in msgs.items():text=text.replace(': '+old+'\n',': '+new+'\n')
        text=text.replace('loop 펼친 두 페이지를 두 차례 촬영','loop 두 차례 촬영 (spread)')
    return '```mermaid\n'+text+'```'
s=re.sub(r'```mermaid\n([\s\S]*?)```',annotate_diagram,s)
s=s.replace('Serial -->|"버튼 입력<br/>(DeviceInputEvent)"| Device',
            'Serial <-->|"버튼 입력·점자 상태<br/>(DeviceInputEvent /<br/>snapshot)"| Device')
s=s.replace('        Device -->|"현재 읽기 상태<br/>(snapshot)"| Serial\n','')

# Each section retains Korean first. Add the original term on first unannotated use.
terms={'단말 실행 프로그램':'Device Runtime','촬영 프로그램':'Book Scanner',
'흐름 조정기':'Coordinator','전송 보관함':'outbox','수신 확인서':'receipt','촬영 결과 묶음':'artifact',
'페이지별 처리 단위':'fragment','읽기 자료 묶음':'datapack','게시 버전':'revision','읽던 위치':'cursor',
'출력 상태 번호':'generation','음성 조회 키':'audio_ref','점자 표시 창':'viewport','점자 시작 위치':'braille_offset',
'현재 읽기 항목':'focus','페이지 중간 표현':'Page IR','읽기 항목':'focus item',
'관심 영역':'ROI','영역 좌표':'bbox','외곽선':'contour','관측':'observation',
'책등 분리선':'seam','미리보기':'preview','수식 구조 트리':'AST','문제 단위':'PROBLEM_UNIT',
'형식 검사':'schema validation','해시값':'hash','저장 작업':'transaction','재생 작업 번호':'epoch',
'촬영 순번 상한':'cutoff','파일 검사 목록':'manifest','재시도':'retry','판단 불가':'UNKNOWN'}
sections=re.split(r'(?=^#{2,3} )',s,flags=re.M)
for n,section in enumerate(sections):
    parts=re.split(r'(```[\s\S]*?```|`[^`\n]+`|\[[^\]\n]+\]\([^\n)]+\))',section)
    used=set()
    for i in range(0,len(parts),2):
        for korean,english in sorted(terms.items(),key=lambda x:-len(x[0])):
            if korean in used:continue
            pattern=re.escape(korean)+r'(?!\s*\()'
            parts[i],count=re.subn(pattern,lambda m,e=english:m.group(0)+'('+e+')',parts[i],count=1)
            if count:used.add(korean)
    sections[n]=''.join(parts)
s=''.join(sections)
doc.write_text(s,encoding='utf-8')
print('Equation, bilingual terms and wrapped diagram labels written.')

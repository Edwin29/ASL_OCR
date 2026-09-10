"""Documentation-only terminology and presentation correction, preserving code links."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[3]
doc = root / 'docs/ASL_OCR_TECHNICAL_OVERVIEW.md'
text = (root / 'docs/technical-overview/READER_FEEDBACK_BEFORE.md.snapshot').read_text(encoding='utf-8-sig')

# Do not translate source paths, inline source identifiers or code examples.
# Long phrases precede individual words to preserve distinctions in the original.
translations = {
 'Desktop source':'문서를 대조한 데스크톱 소스', '파일별 source identity':'파일별 소스 해시 기록',
 '10-cell 점자 디스플레이':'점자 10칸 디스플레이', 'prototype':'시제품',
 'Windows Laptop':'윈도우 노트북', 'Desktop server':'데스크톱 서버',
 'Android camera':'안드로이드 카메라', 'Laptop':'노트북', 'Desktop':'데스크톱',
 'DeviceApplication/Coordinator':'단말 앱과 흐름 조정기(DeviceApplication/Coordinator)',
 'Device Runtime':'단말 실행 프로그램(Device Runtime)', 'Book Scanner':'촬영 프로그램(Book Scanner)',
 'full-resolution frame':'원본 해상도의 영상 한 장', 'source frame':'촬영 원본 영상',
 'camera source':'카메라 입력부', 'raw/effective dimensions':'입력·변환 후 크기',
 'source diagnostics':'입력 진단 기록', 'rotation·mirror·crop':'회전·좌우 반전·잘라내기',
 'width/height':'가로·세로 크기', 'frame ranking':'촬영 영상 우선순위',
 'mask confidence':'페이지 영역 판정 점수', 'connected component':'서로 이어진 화소 영역',
 'landmark 기반 손 모델':'손의 관절 위치를 찾는 모델',
 'page segmentation':'페이지 영역 분리', 'footer 숫자 인식':'페이지 하단 번호 인식',
 'raw pair':'좌우 인식 문자열 쌍', 'raw bank':'원문 관측 묶음',
 'reference bank':'기준 관측 묶음', 'normalized page label':'정규화한 페이지 번호',
 'normalized label':'정규화한 번호', 'raw text':'인식 원문',
 'query':'새 관측', 'reference':'기준 관측', 'consensus':'동일한 인식 결과의 반복 수',
 'page-change':'페이지 변경', 'visual change':'영상 변화',
 'coherent numeric difference':'앞뒤가 맞는 페이지 번호 변화',
 'numeric corroboration':'페이지 번호를 통한 추가 확인',
 'baseline preview':'기준 미리보기 영상', 'dynamic programming':'동적 계획법',
 'conservative crop':'내용을 보존하도록 여유를 둔 잘라내기',
 'uncertainty band':'경계가 불확실한 띠 영역', 'sampling grid':'화소를 옮길 위치 격자',
 'local retry':'해당 촬영 재시도', 'raw crop':'보정 전 잘라낸 이미지',
 'reading order':'읽기 순서', 'normalized text':'정규화한 글',
 'display formula':'독립된 수식', 'inline math':'문장 안 수식',
 'plain-text':'일반 글자', 'embedded text':'그림 안에서 인식된 글',
 'visited 집합':'이미 처리한 항목 목록', 'member':'구성 항목',
 'flattener':'읽기 항목 변환기', 'presentation AST':'수식 구조 트리(AST)',
 'Unknown node':'해석하지 못한 부분을 표시하는 노드',
 'degraded clear':'출력 실패를 기록하고 점자값을 비우는 처리',
 'naturalization':'자연스러운 표현으로 변환', 'logical dots':'논리적인 점 위치',
 'leaf AST':'하위 구조가 없는 단일 AST 항목',
 'immutable':'불변', 'idempotency key':'중복 요청을 식별하는 키',
 'inventory':'파일 목록', 'staging':'임시 수신 위치',
 'retryable':'재시도 가능한', 'durable':'재시작 뒤에도 남도록 저장된',
 'same-frame':'동일한 영상 한 장', 'scan session':'촬영 작업',
 'reading session':'읽기 작업', 'command receipt':'명령 처리 기록',
 'stable page/focus anchor':'저장된 페이지·읽기 항목 식별자',
 'stable':'유지되는', 'progress':'읽던 위치', 'cursor recovery':'읽던 위치 복구',
 'transaction-local':'저장 작업 안에서만 사용하는',
 'transaction':'함께 성공하거나 함께 취소되는 저장 작업',
 'OPEN session':'열려 있는 읽기 작업', 'snapshot':'현재 상태 묶음',
 'audio_ref':'음성 파일 조회 키(audio_ref)',
 'native stream':'운영체제 음성 출력 통로', 'playback owner':'재생 담당 작업',
 'callback':'음성 장치가 호출하는 처리 함수', 'PCM':'압축하지 않은 음성 표본(PCM)',
 'active/pending job':'실행 중이거나 대기 중인 재생 작업',
 'dedupe':'중복 제거', 'partial record':'아직 끝나지 않은 수신 메시지',
 'input queue':'입력 대기열', 'latest desired frame':'가장 최근에 요청한 점자 상태',
 'main loop':'주 실행 반복문', 'requested state':'요청된 상태',
 'physical closed-loop correction':'실제 핀 위치를 되읽어 보정하는 기능',
 'physical cell':'실제 점자칸', 'physical':'물리',
 'device_id':'단말 식별자(device_id)',
 'source_frame_id':'영상 식별자(source_frame_id)',
 'artifact_id':'촬영 결과 식별자(artifact_id)',
 'receipt_id':'수신 확인 식별자(receipt_id)',
 'page/focus ID':'페이지·읽기 항목 식별자',
 'page_index':'페이지 순번(page_index)',
 'preview rendering':'미리보기 표시', 'profile override':'실행 설정의 덮어쓰기',
 'entrypoint':'실행 시작점', 'fallback':'대체 처리',
 'early exit':'조건 충족 즉시 판단 종료', 'silent':'음성 없는',
 'backoff':'간격을 늘려 재시도', 'attempt cap':'시도 횟수 상한',
 'delay cap':'대기 시간 상한', 'timeout':'시간 초과',
 'retry':'재시도', 'fatal':'종료가 필요한 오류',
 'conflict':'저장 상태나 요청 내용의 충돌', 'reconnect':'재연결',
 'commit':'저장 확정', 'append':'추가 촬영', 'cutoff':'촬영 순번 상한',
 'seal':'촬영 범위 확정', 'flush':'남은 전송 완료 대기',
 'outbox':'전송 보관함', 'receipt':'수신 확인서',
 'datapack':'읽기 자료 묶음', 'revision':'게시 버전',
 'fragment':'페이지별 처리 단위', 'artifact':'촬영 결과 묶음',
 'spread':'펼친 두 페이지', 'session':'작업 상태', 'focus':'현재 읽기 항목',
 'generation':'출력 상태 번호', 'cursor':'읽던 위치 정보',
 'worker':'별도 처리 작업', 'queue':'대기열', 'metadata':'부가 정보',
 'manifest':'파일 구성·검사 목록', 'hash':'내용 확인용 해시값',
 'cache':'재사용 보관 공간', 'channel':'출력 경로',
 'preview':'미리보기', 'camera':'카메라', 'frame':'영상 한 장',
 'footer':'페이지 하단', 'crop':'잘라낸 이미지', 'seam':'책등 분리선',
 'bbox':'영역 좌표', 'grid':'격자', 'aspect':'가로세로 비율',
 'token':'수식을 나눈 기호 조각', 'issue':'진단 항목', 'parser':'구조 해석기',
 'cell':'칸', 'viewport':'점자 표시 창', 'offset':'점자 시작 위치',
 'span':'수식 구간', 'command':'명령', 'mode':'모드',
 'config':'설정', 'source':'입력', 'output':'출력', 'input':'입력',
 'status':'상태', 'identity':'동일 페이지 여부', 'accepted':'전송 확인된',
 'confidence':'판정 점수', 'clipping':'내용 잘림', 'mask':'페이지 영역 표시',
 'centroid':'영역 중심', 'coverage':'덮는 비율', 'edge':'경계선',
 'contour':'외곽선', 'profile':'실행 설정', 'pixel':'화소',
}

def translate_prose(segment):
    for old, new in sorted(translations.items(), key=lambda kv: -len(kv[0])):
        segment = re.sub(r'(?<![A-Za-z0-9_])'+re.escape(old)+r'(?![A-Za-z0-9_])', lambda m, v=new:v, segment)
    return segment

# Section 9 intentionally retains exact module names for source lookup.
head, tail = text.split('## 9. 개념과 실제 코드의 대응', 1)
parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`|\[[^\]\n]+\]\([^\n)]+\))', head)
head = ''.join(p if i % 2 else translate_prose(p) for i, p in enumerate(parts))
text = head + '## 9. 개념과 실제 코드의 대응' + tail

def replace_between(start, end, value):
    global text
    a, rest = text.split(start, 1)
    _, b = rest.split(end, 1)
    text = a + value + end + b

replace_between('이 문서에서 사용하는 주요 용어는 다음과 같다.', '## 2. 시스템 전체 구조', '''이 문서는 한국어 역할 이름을 먼저 쓰고, 로그나 코드에서 찾아야 할 이름은 괄호에 병기한다. 아래 용어는 서로 다른 처리 단계이므로 하나의 ‘완료’로 합쳐 읽지 않는다.

| 문서에서 부르는 이름 | 코드·로그 용어 | 뜻 |
|---|---|---|
| 펼친 두 페이지 | spread | 카메라 영상 한 장에 함께 담긴 왼쪽·오른쪽 페이지 |
| 촬영 결과 묶음 | artifact | 원본·좌우 이미지와 파일 검사 정보를 모은 전송 단위 |
| 페이지별 처리 단위 | fragment | 서버가 한 페이지를 인식·해석하는 작업 단위 |
| 읽기 자료 묶음 / 게시 버전 | datapack / revision | 사용자가 고르는 교재 자료 / 완성되어 게시된 내용의 버전 |
| 전송 보관함 / 수신 확인서 | outbox / receipt | 미전송 자료를 재시작 뒤에도 보관하는 곳 / 서버가 자료를 저장했다는 응답 |
| 읽기 준비 완료 | READY | 페이지와 음성 자료의 구성을 검사해 읽을 수 있도록 게시한 상태 |
| 현재 읽기 항목 / 읽던 위치 | focus / cursor | 지금 선택한 지문·수식·표 / 페이지와 항목, 점자 창 위치를 모은 정보 |
| 출력 상태 번호 | generation | 새 탐색 결과와 이전 출력 결과를 구분하는 번호 |
| 작업 상태 | session | 한 번의 촬영 또는 읽기를 이어가기 위해 관리하는 상태 |
| 수식 구조 트리 | AST | 수식의 분자·분모·밑·지수 같은 관계를 담는 표현 |
| 페이지 중간 표현 | Page IR | 인식한 글·수식·표와 순서·위치를 담은 중간 데이터 |
| 읽기용 페이지 | AccessiblePage | 방향키로 선택해 읽을 항목들을 정리한 페이지 데이터 |
| 점자칸 / 점자 표시 창 | cell / viewport | 여섯 점으로 문자를 나타내는 한 칸 / 한 번에 표시하는 여러 칸 |
| 점자 출력 메시지 | FRAME | 단말이 점자 장치에 보낼 상태 번호와 점자값을 담은 메시지 |
| 명령 수락 응답 | ACK | 입력 메시지를 받았다는 응답. 모터가 움직였다는 뜻은 아님 |

영상에서는 frame이 ‘영상 한 장’, 점자 통신에서는 대문자 FRAME이 ‘출력 메시지’를 뜻한다. 영상 snapshot은 한 장 촬영한 이미지이고, 읽기 snapshot은 현재 위치·음성 조회 키·점자값을 담은 상태 묶음이다. 본문에서는 두 의미를 구별해 쓴다.

''')

diagrams = [
'''flowchart LR
    Phone["휴대폰 카메라"] -->|"인증 후 영상 한 장 받기"| Scanner
    subgraph Laptop["노트북 단말"]
        Scanner["촬영 판단과 좌우 페이지 보정"]
        Device["사용자 입력과 작업 흐름 조정"]
        Outbox["전송 보관함"]
        Audio["음성 파일 수신과 재생"]
        Serial["버튼 메시지 수신과 점자값 전송"]
        Scanner -->|"촬영 결과"| Outbox
        Device -->|"촬영 시작과 종료"| Scanner
        Serial -->|"버튼 입력"| Device
        Device -->|"현재 읽기 상태"| Audio
        Device -->|"현재 읽기 상태"| Serial
    end
    subgraph Desktop["데스크톱 서버"]
        Control["자료 목록과 읽던 위치 관리"]
        Upload["촬영 결과 저장과 수신 확인"]
        Parse["글자 인식과 페이지 구조 해석"]
        Speech["음성 파일 생성"]
        Store["읽기 자료와 상태 저장소"]
        Upload --> Parse
        Parse --> Speech
        Parse --> Store
        Control <--> Store
    end
    Outbox -->|"파일 전송"| Upload
    Upload -->|"수신 확인서"| Outbox
    Device <-->|"자료 선택과 탐색"| Control
    Audio <-->|"인증된 음성 파일 요청과 응답"| Control
    Serial <--> Bluetooth["블루투스 모듈 HC-05"]
    Bluetooth <--> STM["STM32 버튼 입력과 점자 명령 해석"]
    STM --> PCA["모터 제어 보드 PCA9685 두 개"]
    PCA --> Cells["서보 20개와 점자 10칸"]
    Pi["계획 중인 Raspberry Pi 4"] -.->|"노트북 역할 이식"| Device
''',
'''sequenceDiagram
    actor User as 사용자
    participant D as 단말 흐름 조정
    participant C as 촬영 판단
    participant V as 서버 수신
    participant P as 서버 페이지 처리
    participant S as 서버 읽기 관리
    participant O as 음성과 점자 출력
    User->>D: 촬영 모드에서 새 자료 선택
    D->>C: 촬영 시작
    loop 펼친 두 페이지를 두 차례 촬영
        C->>C: 품질과 중복 검사 후 좌우 이미지 준비
        C->>D: 촬영 결과 묶음 전달
        D->>D: 전송 보관함에 저장
        D->>V: 촬영 파일과 검사 정보 전송
        V->>P: 저장한 페이지의 처리 작업 등록
        Note over P: 페이지 해석은 다음 촬영과 독립적으로 진행
        V-->>D: 서버 저장 확인 응답
        D->>D: 수신 확인을 단말에도 저장
        D->>C: 이 촬영의 전송 완료 통지
        D->>O: 전송 완료 안내 요청
        C->>C: 페이지가 바뀌었는지 관측
    end
    User->>D: 확인 버튼 길게 누르기
    D->>C: 새 촬영 중지
    D->>D: 이번 촬영 범위의 남은 전송 완료 대기
    D->>P: 자료에 포함할 마지막 촬영 순번 확정
    P->>P: 페이지 처리 완료 대기와 음성 생성 및 검사
    P-->>D: 후속 상태 조회에서 읽기 준비 완료 확인
    D->>O: 자료 저장 완료 안내 요청
    User->>D: 완성된 자료 선택과 읽기 조작
    D->>S: 읽던 위치 복구 또는 이동 요청
    S-->>D: 현재 위치와 음성 조회 키 및 점자값
    D->>O: 같은 읽기 상태의 음성과 점자 전달
    Note over O: 실제 청취와 점자 돌출 상태는 별도 확인
''',
'''flowchart TD
    Start["새 촬영 후보"] --> Quality{"페이지가 잘 보이고 안정한가?"}
    Quality -->|"아니오"| Observe["안내 후 다시 관측"]
    Observe --> Quality
    Quality -->|"예"| Candidate["좌우 하단 인식 문자열 수집"]
    Candidate --> Initial{"같은 페이지인가?"}
    Initial -->|"판단 불가 또는 시간 초과"| Retry["다시 수집하거나 촬영 재시도"]
    Retry --> Quality
    Initial -->|"다름"| Prepare["동일한 영상에서 좌우 이미지 준비"]
    Initial -->|"같음"| Wait["전송한 페이지를 기준으로 변경 대기"]
    Prepare --> Receipt["결과 보관과 전송 후 수신 확인"]
    Receipt --> Wait
    Wait --> Query["새 영상과 좌우 문자열 관측"]
    Query --> Decision{"페이지 변경 판단"}
    Decision -->|"판단 불가"| Wait
    Decision -->|"같음"| Rearm["변화 기억을 지우고 다시 관측"]
    Rearm --> Wait
    Decision -->|"다름"| Gate{"영상 변화 또는 번호 변화가 뒷받침하는가?"}
    Gate -->|"아니오"| Wait
    Gate -->|"예"| Start
''',
'''flowchart TD
    Full["촬영 원본과 영상 식별자"] --> Preview["축소 영상과 페이지 영역 및 품질 정보"]
    Preview --> Identity["하단 번호 관측과 중복 판단"]
    Full --> Crop["동일한 영상에서 잘라낸 좌우 이미지"]
    Identity -.->|"처리 허가"| Crop
    Crop --> Warp["책장 곡면을 보정한 이미지"]
    Warp --> Bundle["촬영 파일 묶음과 검사 정보"]
    Bundle --> Durable["전송 보관함과 서버 저장 확인"]
    Durable --> Blocks["페이지별 글자와 수식 및 표 인식"]
    Blocks --> IR["페이지 중간 표현과 수식 구조"]
    IR --> Access["선택해서 읽을 항목 목록"]
    Access --> Revision["검사를 마친 페이지와 음성 자료"]
    Revision --> Snapshot["현재 위치와 음성 조회 키 및 점자 창"]
    Snapshot --> PCM["음성 파일에서 스피커 재생까지"]
    Snapshot --> Frame["점자 메시지에서 모터와 실제 핀까지"]
''']
counter = iter(diagrams)
text = re.sub(r'```mermaid\n[\s\S]*?```', lambda _: '```mermaid\n'+next(counter)+'```', text)

replace_between('새 자료를 만드는 정상 경로는 다음과 같다.', '```mermaid\nsequenceDiagram', '''새 자료를 만드는 정상 경로는 다음과 같다. 이미 읽기 준비가 끝난 자료가 있으면 촬영을 생략하고 7단계에서 시작한다. ‘확인 버튼 길게 누르기’는 촬영 모드에서는 자료 생성 마감, 읽기 모드에서는 목록으로 돌아가기를 뜻한다.

| 단계 | 사용자가 하는 일과 시스템의 처리 |
|---|---|
| 1. 자료 선택 | 촬영 모드의 목록에서 새 자료 또는 추가 촬영할 자료를 선택한다. |
| 2. 촬영 시점 판단 | 시스템이 영상의 품질과 안정성, 이전에 전송한 페이지인지 확인한다. |
| 3. 이미지 준비 | 같은 영상 한 장에서 왼쪽과 오른쪽 페이지를 추출하고 보정한다. |
| 4. 전송과 확인 | 결과를 단말에 보관하고 서버에 전송한다. 서버 저장을 확인한 뒤 전송 완료를 안내한다. |
| 5. 다음 촬영 | 페이지 변경이 확인되면 다음 펼친 면을 촬영한다. 서버는 앞서 받은 페이지를 해석할 수 있다. |
| 6. 자료 생성 마감 | 확인 버튼을 길게 누른다. 마지막 촬영까지 전송을 마치고 페이지와 음성 자료를 검사해 게시한다. |
| 7. 읽기와 탐색 | 완성된 자료를 선택한다. 이전 위치를 복구하거나 첫 항목부터 페이지·지문·수식·표를 탐색한다. |
| 8. 출력 확인 | 현재 선택한 내용의 음성을 재생하고 점자값을 보낸다. 실제 청취와 핀 상태는 별도로 확인한다. |
| 9. 재진입 | 읽기를 나갔다 다시 들어오거나 앱을 재시작해도 저장한 위치에서 이어 읽는다. |

''')

replace_between('## 7. 대표 실행 사례', '## 8. 실패 처리와 현재 한계', '''## 7. 대표 실행 사례

### 두 번 촬영해 네 페이지의 읽기 자료 만들기

2026-09-08~09의 촬영 시험(H1)에서는 휴대폰 카메라와 실제 단말 프로그램을 사용했다. 버튼 조작은 콘솔에 명령을 입력하는 방식으로 대신했다. 다음 표는 당시 기록이며 이번 문서 수정 중 새로 수행한 시험이 아니다.

| 사용자 행동·상황 | 시스템 안에서 일어난 일 | 확인한 결과 |
|---|---|---|
| 첫 번째 펼친 면을 촬영 | 좌우 이미지가 서버에 저장되고 단말에도 수신 확인을 기록 | 첫 촬영의 전송 완료 확인 |
| 다음 페이지로 넘긴 뒤 대기 | 페이지 변경 판단이 지연됐으나 이후 추가 조작 없이 두 번째 촬영을 전송 | 두 번째 촬영의 저장 확인 |
| 두 촬영을 서버가 처리 | 왼쪽·오른쪽을 각각 해석해 총 네 페이지를 준비 | 네 페이지 모두 첫 처리 시도에서 준비 완료 |
| 확인 버튼을 길게 누름 | 두 번째 촬영까지 자료에 포함하도록 범위를 확정하고 최종 자료 생성 | 새 읽기 자료의 첫 게시 버전을 서버 저장소에서 확인 |
| 안내를 기다림 | 자료 생성 중 안내와 저장 완료 안내 재생 | 사용자가 두 안내를 들었다고 확인 |

영상이 세로 방향으로 들어와 방향을 다시 설정한 과정과, 두 번째 전송까지 오래 기다린 문제도 있었다. 결국 전송됐다는 사실만으로 지연 문제가 해결됐다고 보지는 않는다. 어떤 추가 판단 조건이 마지막에 충족됐는지는 당시 요약 로그만으로 확정하지 못했다.

정확한 자료 식별자와 수신 상태, 로그 위치는 [원시 실험 기록](H1_FRESH_ALIGNED_RUN_20260908.md)에서 추적할 수 있다. 이 사례는 물리 버튼과 점자 장치까지 모두 통과한 시험은 아니다.

### 같은 음성이 들려도 페이지는 바뀔 수 있다

사용자가 다음 페이지로 이동했는데 다시 `www.ebsi.co.kr`이라는 음성이 들렸다. 두 페이지의 첫 항목에 같은 웹 주소가 있었기 때문이다. 소리만 비교하면 이동 실패로 오해할 수 있으므로, 서버가 반환한 페이지 식별자와 출력 상태 번호도 달라졌는지 확인했다.

또한 앱을 종료하기 전에 읽던 페이지·항목을 저장하고 다시 실행했다. 처음부터 읽지 않고 저장된 위치와 대응 음성을 복구한 것을 확인했다. 당시 확인한 항목에는 표시할 점자값이 없었으므로, 이 결과가 긴 수식의 점자 창 이동이나 실제 핀 출력을 검증한 것은 아니다.

### ‘2분의 1’이 읽기 정보로 바뀌는 예

이 예의 입력은 사진이 아니라 분수 ½를 나타내는 수식 문자열이다. 기존 [변환 실행 기록](technical-overview/evidence/math-example.json)을 독자용으로 풀어 썼다. 실제 음성 합성이나 모터 동작 시험과는 구분한다.

| 단계 | 독자가 이해할 결과 | 구현과 연결할 때의 표기 |
|---|---|---|
| 수식 입력 | 분자가 1이고 분모가 2인 분수 | LaTeX `\\frac{1}{2}` |
| 구조 해석 | ‘분수’ 아래 분자 1과 분모 2의 관계를 저장. 해석 오류나 남은 기호 없음 | 수식 구조 트리(AST) |
| 음성용 문장 | `2분의 1`이라는 문장을 생성 | 음성 파일 자체를 생성·재생한 결과는 아님 |
| 점자용 정보 | 다섯 점자칸에 표시할 점 위치를 생성 | 점자값 `[60,3,12,60,1]` |
| 표시 창 선택 | 10칸 안에 다 들어가므로 다음 창이 필요 없음 | 시작 위치 0, 전체 길이 5칸 |
| 장치 전달 형태 | 남은 다섯 칸에는 빈 값을 채우는 형태 | `[60,3,12,60,1,0,0,0,0,0]`, 실제 전송하지 않음 |

여기서 숫자 배열은 각 칸의 여섯 점 중 어느 점을 올릴지 표현한 값이다. 계산으로 분수를 소수로 바꾸는 단계가 아니며, 논리적인 점자값이 만들어졌다는 사실과 실제 핀이 맞게 돌출됐다는 사실도 다르다.

해석하지 못한 기호가 남는 수식은 ‘일부 해석’ 또는 ‘해석 실패’로 구분한다. 일부 해석된 수식은 불확실 안내와 함께 지원되는 부분을 읽을 수 있지만 점자는 비운다. 관련 동작은 [음성 규칙 테스트](../document-parser/tests/unit/accessibility/test_speech_rules.py)와 [수식 해석 테스트](../document-parser/tests/unit/test_latex_ast.py)에 연결된다.

''')

doc.write_text(text, encoding='utf-8')
print('Updated documentation prose, four diagrams and reader examples.')

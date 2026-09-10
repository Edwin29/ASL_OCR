# 한국어 설명과 기존 영문·코드 용어 대응표

[Technical Overview](../ASL_OCR_TECHNICAL_OVERVIEW.md)의 한국어 설명을 그대로 읽으면서, 이전 문서·코드·로그의 표기를 찾기 위한 표다. 같은 개념의 검색용 표기이며 서로 다른 상태나 보장을 하나로 합치지는 않는다. 일반 용어와 정확한 코드 식별자를 구분했다.

## 실행 구성과 담당 역할

| 한국어 설명 | 대체 전 용어·코드 이름 | 범위 |
|---|---|---|
| 노트북 단말 / 데스크톱 서버 | Laptop / Desktop server | 현재 배포 역할 |
| 단말 실행 프로그램 | Device Runtime / `asl_device` | 입력·자료 선택·출력 조정 |
| 촬영 프로그램 | Book Scanner / `book_scanner` | 촬영 판단·좌우 추출·보정 |
| 단말 앱 / 흐름 조정기 | `DeviceApplication` / `DeviceFlowCoordinator` | 입력 처리 반복 / 작업 상태 전이 |
| 촬영 판단과 보정 | Scanner | 도식의 촬영 담당부 |
| 별도 처리 작업 / 실행 흐름 | worker / thread | 동시에 진행하는 처리 단위 |
| 입력·출력 담당부 | adapter / port / presenter | 경계 구현·호출 계약·출력 역할. 세 용어가 같은 클래스라는 뜻은 아님 |
| 실행 시작점 / 구성 | entrypoint / composition | 실제로 실행할 모듈과 연결 선택 |
| 실행 설정 | config / profile / runtime override | 기본값과 실행 시 덮어쓴 값 구분 |
| 장치 연결 확인 | C0 / presence | 서버에 연결 상태 알림 |
| 자료 목록·읽기 관리 | S0 / catalog / reading | 자료 선택·위치·음성 조회 |
| 촬영 결과 수신·저장 | V4 / durable upload | 파일 수신과 확인서 |
| 페이지 해석·자료 게시 | S1 / parser / assembler | 개별 처리와 전체 조립 |

## 카메라와 중복 판단

| 한국어 설명 | 대체 전 용어·코드 이름 | 범위 |
|---|---|---|
| 영상 한 장 / 한 장 촬영 이미지 | frame / camera snapshot | 읽기 상태 snapshot과 구분 |
| 원본 해상도 / 미리보기 | full-resolution / preview | 처리 크기와 화면 표시 |
| 회전·좌우 반전·잘라내기 | rotation / mirror / crop | 입력 영상 변환 |
| 관심 영역 / 영역 좌표 | ROI / bbox | 검사할 범위 / 사각형 좌표 |
| 페이지 영역 표시 / 외곽선 | mask / contour | 화소 영역 / 그 경계 |
| 영역 중심 / 덮는 비율 | centroid / coverage | 위치·크기 지표 |
| 내용 잘림 / 판정 점수 | clipping / confidence | 잘림 상태 / 해당 단계의 지표 |
| 촬영 후보 / 안정성 | candidate / stability | 적격 여부 / 최근 영상의 일관성 |
| 가중점수 / 우선순위 비교 | weighted score / lexicographic ranking | 영역 선택과 원본 선택의 서로 다른 비교 방식 |
| 펼친 두 페이지 / 좌우 | spread / L/R | 동일한 순간의 두 페이지 |
| 페이지 하단 번호 | footer / page number | 본문 글자 인식과 별도 |
| 하단 원문 쌍 전략 | M1 / `M1_SELECTED_RAW_PAIR` | 현재 중복 판단 구성 |
| 좌우 인식 문자열 쌍 | raw pair / `OpaqueFooterTokenPair` | 정규화한 번호와 구분 |
| 새 관측 / 기준 관측 묶음 | query / reference bank | 비교할 새 결과 / 이미 전송된 결과 |
| 동일 결과의 반복 수 | consensus / `novel_consensus_count` | 같은 새 쌍이 나온 수 |
| 같음 / 다름 / 판단 불가 | SAME / DIFFERENT / UNKNOWN | raw identity 판단 결과 |
| 페이지 변경 허가 | page-change gate | raw DIFFERENT만으로는 충분하지 않음 |
| 영상 변화 기억·재무장 | visual latch / rearm | 변화 이력 유지와 초기화 |
| 번호로 추가 확인 | numeric corroboration / `coherent_numeric_difference` | 연속된 번호 쌍의 변화 |
| 영상 요약 / 국소 특징 | pHash / projection / ORB | 모습·잉크 분포·특징점 비교 |
| 국소 대비 보정 | CLAHE | 하단 인식 후보 이미지 처리 |
| 책등 분리선 / 불확실 영역 | seam / uncertainty band | 좌우 경계와 경계 주변 |
| 여유를 둔 잘라내기 | conservative crop | 내용 보존을 위해 겹칠 수 있음 |
| 곡면 보정 / 화소 이동 격자 | unwarp / sampling grid / UVDoc | 모델과 그 보정 표현 |

## 파일 전송과 문서·수식 표현

| 한국어 설명 | 대체 전 용어·코드 이름 | 범위 |
|---|---|---|
| 촬영 결과 묶음 / 페이지별 처리 단위 | artifact / fragment | 파일 전송 단위 / 페이지 처리 단위 |
| 부가 정보 / 파일 목록·검사 목록 | metadata / inventory / manifest | 출처·구성과 검증 정보 |
| 내용 확인값 / 출처 연결 | hash / lineage | 파일 무결성 / 변환 계보 |
| 전송 보관함 / 수신 확인서 | outbox / receipt | 단말 보존 / 서버 응답 |
| 재시작 뒤에도 남는 저장 | durable / durability | 메모리 수락과 구분 |
| 수신 확인의 단말 저장 | ack commit / acked | 버튼 ACK와 별도 |
| 중복 요청 식별 | idempotency key / request identity | 같은 요청의 재시도 구별 |
| 자료 묶음 / 게시 버전 | datapack / revision | 내용의 식별자와 버전 |
| 촬영 순번 상한 / 범위 확정 | cutoff / seal / through_sequence | 마감할 촬영 범위 |
| 새 촬영 중지 / 남은 전송 대기 | freeze / flush | 마감 전 두 처리 |
| 읽기 준비 완료 | READY | 전체 자료 게시 상태 |
| 글자·영역 인식 모델 | PaddleOCR-VL / OCR | 문서 이미지에서 영역과 내용 인식 |
| 인식 영역 / 읽기 순서 | block / reading order | 모델 출력의 단위와 순서 |
| 페이지 중간 표현 | Page IR | 인식 결과와 탐색 표현 사이 |
| 읽기용 페이지 / 읽기 항목 변환 | AccessiblePage / flattening | 선택할 항목 목록으로 전개 |
| 글 / 수식 / 표 / 미지원 그림 | TEXT / MATH / TABLE / UNSUPPORTED_VISUAL | 내용 종류와 읽기 항목 종류 |
| 문제 단위 / 구성 항목 | PROBLEM_UNIT / member | 지문·조건·보기·선택지 연결 |
| 인식 원문 / 정규화한 글 | raw text / normalized text | 원본 보존과 교정 표현 |
| 문장 안 수식 / 독립 수식 | inline math / display formula | 수식 배치 형태 |
| 수식 표기 문자열 / 기호 조각 | LaTeX / token | 문자열 형식 / 해석 단위 |
| 수식 구조 트리 | AST / presentation_ast | 추상 구문 트리(Abstract Syntax Tree), 이 프로젝트에서는 표현 구조 |
| 분수·분자·분모 | Fraction / numerator / denominator | 수식 구조의 관계 |
| 등호 양쪽의 관계 | Relation / left / right | 방정식 예제의 최상위 구조와 양변 |
| 거듭제곱·밑·지수 | Power / base / exponent | 괄호 전체를 제곱하는 범위 |
| 괄호로 묶은 식 | Parenthesized / body | 괄호 안의 식을 하나의 구조로 유지 |
| 식의 나열·문자·연산자·숫자 | Row / Identifier / Operator / Number | 예제의 `x`, `+`, `1` 등을 구분하는 구조 요소 |
| 미해석 부분 / 진단 항목 | Unknown node / issue | 오류를 버리지 않고 남기는 표현 |
| 해석 완료·일부 해석·해석 실패 | VALID / PARTIAL / INVALID | 원문 정확도 등급이 아님 |
| 행·열 병합 | rowspan / colspan | 표 격자의 점유 관계 |
| 자연스러운 발화 변환 | naturalization / speech rules | 구조에서 읽을 문장 생성 |
| 음성 생성 프로그램 | Piper / synthesizer | 문장에서 음성 파일 생성 |

## 탐색·출력·오류 처리

| 한국어 설명 | 대체 전 용어·코드 이름 | 범위 |
|---|---|---|
| 읽던 위치 / 현재 항목 | cursor / focus | 저장 좌표 / 선택 대상 |
| 위치 기준 식별자 | stable anchor / page_id / focus_item_id | 다른 실행에서 같은 대상을 찾음 |
| 일반 문서 / 표 탐색 | DOCUMENT / TABLE mode | 조작 의미가 달라지는 모드 |
| 수식 구간 / 점자 시작 위치 | math span / braille_offset | 항목 안 수식 / 창의 시작 |
| 점자칸 / 표시 창 | cell / viewport | 여섯 점 한 칸 / 한 번에 표시할 크기 |
| 작업 상태 / 읽던 위치 저장 | session / progress | 열린 작업 / 단말·자료별 지속 상태 |
| 출력 상태 번호 / 재생 작업 번호 | generation / epoch | 서버 읽기 상태 / 단말 작업 권한 |
| 현재 읽기 상태 묶음 | reading snapshot | 위치·음성 조회 키·점자값을 묶은 응답 |
| 음성 조회 키 | audio_ref | 임의 URL이나 파일 본체가 아님 |
| 음성 파일 / 음성 표본 | WAV / PCM | 파일 형식 / 압축하지 않은 표본 |
| 재사용 보관 / 오래된 것부터 제거 | cache / LRU | 재수신·합성을 줄이는 보관 정책 |
| 음성 장치 처리 통로 | native stream / sounddevice / PortAudio | 재생 자원과 라이브러리 |
| 눌림·해제 / 짧게·길게 | ACTIVATED·RELEASED / SHORT·LONG | 물리 변화와 해석된 입력 구분 |
| 아래 누르기 반복 | hold repeat | 단말이 반복 이동을 생성 |
| 점자 출력 메시지 / 수락 응답 | FRAME / ACK | 점자 출력 요청 / 버튼 메시지 수락 |
| 버튼 이동 메시지 / 대기열 포화 | NAV / BUSY | 입력 packet / 수락할 여유가 없음 |
| 입력 대기열 / 최신 상태 우선 | input queue / latest desired frame | 입력 보관 / 중간 출력 대체 |
| 전부 함께 저장·취소 | transaction | 위치와 명령 처리 기록을 원자적으로 저장 |
| 저장 확정 / 저장 응답 재사용 | commit / receipt replay | 반영 / 중복 명령 재실행 방지 |
| 재시도·대기 증가·시간 초과 | retry / backoff / timeout | 실패 후 처리 |
| 복구 가능·영구·종료 오류 | recoverable / permanent / fatal | caller별 정책과 구분 |
| 대체 처리 / 안전하게 점자값 비움 | fallback / degraded clear | 대체 성공 허용 여부 / 실패 출력 처리 |
| 인터럽트·원형 버퍼·줄 복구 | IRQ / RX ring / newline resync | 펌웨어 수신 경계 |
| 각도표·연결 대응 | LUT / channel mapping | 모터 요청값과 물리 연결의 대응 |
| 전송 완료 / 자료 완료 안내 | spread_sent / datapack_saved | 저장 상태에 따른 별도 안내 |
| 음성 시작 / 완료 | reading_audio_playback_started / reading_audio_playback_completed | 호출 전 통지 / 유효 작업의 정상 반환 |

한국어로 같은 ‘번호’라고 부르더라도 촬영 순번(sequence), 페이지 순번(page_index), 읽기 상태 번호(generation), 단말 재생 작업 번호(epoch)는 서로 대체하지 않는다. 표는 설명 대응표이며 firmware protocol이나 설정값을 바꾸는 문서가 아니다.

# 프로토타입 정리 점검 및 최종보고서 SW 수록 후보

## 1. 점검 결론

**선정 교재를 촬영하고 Pi에서 음성·점자로 읽는 기본 시연 경로는 갖춰졌다.** 촬영부터 서버 수신, 새 READY 게시, 물리 버튼 탐색과 실제 출력까지 실행했고, 부팅 자동 실행과 전체 전원 재공급 후 읽던 위치 복구도 확인했다.

다만 범용 교재 인식 정확도, 모든 수식·표 지원, 모든 장애 상황의 무인 복구까지 검증한 것은 아니다. 공식 H4 체크리스트를 이번 정리로 일괄 PASS 처리하지 않는다. 현재는 기능 확장보다 **시연 조건 고정, 검증 결과 정리, 보고서 설명의 정확성 확보**가 우선이다.

이번 작업은 관련 source·문서·보존 evidence 및 현재 Pi 상태를 읽기 전용으로 대조했다. 새 촬영, 모터 구동, 서비스 재시작, 제품 수정은 하지 않았다. 첨부 DOCX는 참고자료로만 읽었으며 저장하거나 편집하지 않았다. 문서 안의 사진 요청과 작성 지침도 실행 명령으로 취급하지 않았다.

참고 보고서는 작품명 ‘점으로 보는 수학’이며, 1 제작 개요 / 2 H/W 설계 / 3 S/W 설계 / 4 문제 요인과 해결방안 / 5 고찰로 구성된다. 아래는 이 목차에 맞춘 **수록 후보 목록**이며 완성 본문이 아니다.

원본 해시와 추출 근거: [reference identity](evidence/prototype-review-20260916/reference-identity.json). 아래 P번호는 OOXML 추출 문단 위치이며 Word 페이지 번호가 아니다. 원문에는 Word 수식 5개와 drawing 3개가 있다. 텍스트 추출에서 수식이 비어 보이는 현상을 원본 누락으로 판단하지 않았으며, 인쇄 배치 검수는 이번 범위가 아니다.

## 2. 현재 시스템 구성

| 역할 | 현재 구성 | 보고서에서 구분할 점 |
|---|---|---|
| 영상 공급 | Android IP Camera, 인증된 HTTPS snapshot | 해당 카메라의 self-signed 허용이며 전역 TLS 해제가 아님 |
| 단말 | Raspberry Pi 4, Python 3.13.5, Device Runtime·Book Scanner | Laptop은 개발·검증 및 독립 미리보기 역할 |
| 단말 영상 처리 | OpenCV, 하단 번호 인식용 Paddle 모델, UVDoc | 서버의 본문 PaddleOCR-VL과 별개 |
| 서버 | Desktop, C0/S0/V4/S1, PaddleOCR-VL, Piper, SQLite·파일 저장 | 본문 OCR과 음성 합성까지 Pi에서 독립 수행하는 구조가 아님 |
| 출력 | Pi AUX, Bluetooth HC-05 → STM32 → PCA9685 2개 → 서보 20개·점자 10칸 | 명령 ACK·OS 전송 완료와 실제 돌출은 별도 확인 |
| 운용 | RFCOMM 부팅 준비 및 systemd production 서비스 | 외부 서버와 Android 앱은 별도 준비 필요 |

점검 당시 Pi는 PID1007 active, restart0이며 부팅 서비스 두 개가 enabled였다. 세 Python 패키지 import는 모두 `/home/user/ASL_OCR_PI/source` 아래였다. ARM OCR 단일 스레드 수정과 카메라 재연결 수정의 배포 해시도 일치했다. 전체 source 재검증이나 firmware 메모리 readback을 수행한 것은 아니다.

## 3. 기능과 제약 점검표

| 항목 | 판정 | 근거 및 범위 |
|---|---|---|
| 실제 촬영 → 새 자료 → 읽기 | 완료 확인 | #30의 26/27·28/29·30/31 원본 대조, receipt 3건, READY rev1, 새 자료 읽기 정상 관측 |
| 두 spread 생성·게시 | 완료 확인 | #32의 전송 2건, through_sequence2, READY rev1. 후속 2건의 이미지 내용은 최신 감사에서 별도 재검수하지 않음 |
| 물리 버튼·음성·점자 | 시연 경로 확인 | Pi 기존·새 READY 읽기 정상 관측. 모든 버튼/상태 조합의 전수 계측을 뜻하지 않음 |
| 읽기 재진입·전원 복구 | 완료 확인 | 새 boot-id, 동일 page/focus/offset/generation60 복구, 실제 출력 정상 보고 |
| 부팅 자동 실행 | 완료 확인 | 수동 실행 없이 서비스 시작. 체감 안내 시간 약 1~2분. 최초 로그는 capture 이후 reading 전환이므로 초기 MODE 동기화는 별도 보장하지 않음 |
| 카메라 단절 대응 | 수정·검사 및 사용자 복구 관측 | 재시도 가능 오류의 3회 fatal 상한 제거. 회귀 271개·Pi 모의검사 PASS. 실제 waiting/restored 표식이 없어 재시도 구간의 원시 증거는 부족 |
| 미완료 자료 보존 | 완료 확인 | #31의 receipt 2건 보존, 같은 세션에서 sequence3을 이어받아 게시 |
| 영상 조건·처리 시간 | 제약 유지 | 성공 조건은 조명 조정과 45초 수집 제한. 첫 전송에 4분48초가 걸린 사례도 있어 즉시 인식 보장 없음 |
| OCR·점역 품질 | 지원 범위 내 시연 | 이전 자료 대비 품질 차이가 크지 않다는 정성 관측. 정답률·전문 점역 검수 수치 없음 |
| 어려운 수식·표·그림 | 제한 유지 | PARTIAL/INVALID 수식 점자 비움, 미지원 기호·복잡한 표 수식·그림 의미 해석 제한 |
| 쓰기 중 전원 차단 | 미검증 | 완료된 읽기 상태의 전원 복구와 구분. 업로드·DB 쓰기 중 강제 차단 및 장기 반복 부팅은 미실행 |

근거: [촬영 결과](PI4_PRODUCTION_CAPTURE_RESULT_20260916.md), [부팅·전원](PI4_BOOT_POWER_VALIDATION_20260916.md), [재연결 수정](PI4_CAMERA_RECONNECT_CORRECTION_20260916.md), [이전 단절](PI4_CAMERA_INTERRUPTION_RESTART_20260916.md), [Pi 초기 통합](PI4_INITIAL_RUNTIME_STATUS_20260915.md).

## 4. S/W 설계에 넣을 내용 목록

설명은 ‘왜 필요한가 → 입력 → 판단·변환 → 출력’ 순서로 구성한다. 함수명은 개념 설명 이후 괄호나 구현 대응표에 둔다.

1. **전체 시스템과 역할 분담 — 필수.** Android → Pi 촬영 → Desktop 인식·구조화·Piper → Pi 출력. 최종 단말이 Pi임을 명시한다. P19~20 확장. 근거: `local_composition.py`, `combined_server.py`.
2. **촬영 모드와 읽기 모드 — 필수.** 새 자료·기존 자료 선택, 촬영 마감과 읽기 목록 복귀에서 CONFIRM LONG의 의미를 구분한다. 근거: `device-runtime/src/asl_device/coordinator.py`.
3. **촬영 시점 선택 — 필수.** 축소 영상으로 페이지·가림·안정성을 확인하고 원본을 보존한다. 후보 필터와 최종 원본의 우선순위 선택을 구분한다. P24~33 정리. 근거: `book-scanner/src/book_scanner/video/candidate.py`.
4. **같은 페이지 재촬영 억제 — 필수.** 좌우 문자열 쌍의 반복 수집, SAME 조기 차단, DIFFERENT와 영상/번호 변화의 결합을 설명한다. 한 번의 불일치를 바로 전송 승인으로 사용하지 않는 이유를 포함한다. P34 보강. 근거: `video/opaque_identity.py`, `video/engine.py`.
5. **동일 프레임 좌우 분리·곡면 보정 — 필수.** 다른 시각의 좌우 혼합 방지, 책등 경계 화소 보존, UVDoc 보정 후 양쪽 검사를 설명한다. P35~36 유지. 근거: `detect/spine_seam.py`, `correct/uvdoc_adapter.py`, `video/spread_preparer.py`.
6. **전송과 자료 완성의 구분 — 필수.** outbox·manifest·해시·멱등성·receipt, 재전송과 재촬영의 차이, 마감 순번까지 처리한 뒤 READY를 게시하는 과정을 설명한다. P37 확장. 근거: `delivery.py`, `server/v4_upload.py`, `server/s1_assembler.py`.
7. **문서 인식과 중간 표현 — 필수.** 본문·수식·표의 원문/위치/순서를 Page IR에 보관한 뒤 읽기 항목으로 변환한다. P40~49 정확화. 근거: `serialization/vl_page_ir.py`, `accessibility/flattening/structure_nodes.py`.
8. **문제 구성 분류 — 필수.** 문제 코드·출처·보기·조건·선택지의 문자 표식을 사용해 문제를 묶고 탐색 항목으로 펼친다. P48 교체 후보. 근거: `document-parser/src/document_parser/structure/problem_units.py`.
9. **수식 AST 사용처와 이유 — 필수.** LaTeX를 분자/분모·밑/지수·등호 관계로 파싱하고 같은 구조에 음성과 점자 규칙을 각각 적용한다. 수식을 풀거나 정답을 검증하는 기능은 아니다. P53~58 유지·정확화. 근거: `math/latex_ast.py`, `accessibility/naturalization/korean_math_speech.py`, `accessibility/braille/math_translator.py`.
10. **불확실한 인식의 출력 정책 — 필수.** VALID/PARTIAL/INVALID의 차이, 불확실 안내와 점자 비움, VALID여도 미지원 점역 기호가 있을 수 있음을 설명한다. P61~80 정리.
11. **페이지·항목·수식·점자 창 탐색 — 필수.** 각 이동 단위, 10칸 viewport, 마지막 창의 0 padding, 같은 수식 안 창 이동은 무음이라는 정책을 설명한다. P83~118 유지. 근거: `accessibility/braille/viewport.py` 및 읽기 명령 처리.
12. **현재 내용에 맞는 두 출력 — 필수.** cursor/focus/generation과 취소 권한으로 과거 음성을 중단하고 늦은 결과를 배제한다. P118 보강. 근거: Device Runtime 음성 controller 및 `adapters/stm_serial.py`.
13. **점자 데이터와 실제 모터 연결 — 필수.** 0~63의 6비트 cell → 좌우 3비트 상태 → 모터별 실측 펄스표 → PCA PWM. V3 입력 ACK와 점자 FRAME을 구분한다. P114~117 정확화. 근거: `hardware/stm32/kitel2026final/Core/Src/main.c`.
14. **실제 배포와 복구 — 필수.** Pi 부팅 자동 실행, 같은 device ID의 서버 cursor 복구, 카메라 재연결, draft/READY 차이를 간단히 설명한다. P119 뒤 신규 절 후보.
15. **검증 결과와 조건 — 필수.** 선정 교재, 실제 촬영·게시·읽기·전원 복구, 조명과 45초 조건을 작은 표로 제시한다. 로그 확인과 사용자 관측을 구분한다.
16. **기술 스택 요약 — 선택.** Python, OpenCV, Paddle 하단 인식, UVDoc, PaddleOCR-VL, Piper, SQLite, HTTP, Bluetooth, C/HAL, systemd의 역할을 한 표로 정리한다. 라이브러리 나열보다 책임 분담을 보여준다.

## 5. 첨부 초안의 정정 후보

| 위치 | 점검 사항 | 반영 후보 |
|---|---|---|
| P19·82 | ‘세 가지’ 이후 출력까지 4단계이며 마지막 소절도 3번 | 현재 설명과 맞게 4단계로 일치 |
| P31~33 | threshold, 후보 제외, 최종 선택이 혼재; `selecr_best()` 오기 | 필터와 순위 비교를 구분. 실제 `select_best`는 여백→mask 점수→clipping→조명→선명도→최신 시각 순서 |
| P34 | 28/29 반복 관측을 ‘계속 전송됨’으로 표현 | 관측은 판단 근거이며 전송 완료가 아님. 후속 gate·보정·receipt 필요 |
| P46 | Page IR과 문서 AST를 동일시 | Page IR은 문서 중간 표현, 수식 AST는 그 안의 수식 구조 |
| P48 | 폰트·색상·위치에 따른 확률 분류 | 실제 엔진은 `text-pattern-problem-unit-detector`. 문자 표식과 읽기 순서 기반 규칙으로 설명 |
| P60 | 2017 점자 규정 인용 | 현재 `cell_encoding.py`는 2024 자료/고시 제2024-0005호를 구현 출처로 명시. 실제 사용 원본과 참고문헌을 맞춰 확정. 규정 전체 완전 준수 주장과 구분 |
| P61~80 | 불완전 해석을 모두 INVALID로 설명; PARITAL 오기 | PARTIAL/INVALID의 음성 차이를 유지하고 두 상태 모두 수식 점자를 비운다고 설명 |
| P44·조작표 | 수식·표 점역을 무제한 지원처럼 읽을 가능성 | 일반 문서의 글은 음성 중심이며 복잡한 표 수식·그림 등 지원 한계를 명시 |
| P116 | 모터 목표 각도만 언급 | 현재는 모터별 실측 `pulse_us` LUT를 선택해 PWM count로 변환 |
| P119 이후 | 최근 Pi 운용·복구 결과 누락 | 부팅과 카메라 복구를 보강. 서버 cursor 복구를 Pi 내부의 독립 저장 복구로 오해하지 않게 표현 |

P5의 대체자료 제작 기간·가격과 교육효과 등 외부 사실은 이번 SW 점검에서 검증하지 않았다. source나 시연으로 증명된 수치처럼 사용하지 않고 별도 문헌 확인 대상으로 남긴다. 본문은 수정하지 않았다.

## 6. 4장 문제 요인과 해결방안 후보

1. **영상 조건과 Pi 처리 속도.** 동일 ROI의 Pi/Laptop 비교로 CPU 차이만으로 미인식을 설명할 수 없음을 확인했다. ARM 단일 추론 스레드, 촬영 조건 조정, 로그 기반 45초 수집 시험을 거쳐 생성에 성공했다. 세 조치를 하나의 원인·해결로 합치거나 CLAHE 실험안을 채택한 것처럼 서술하지 않는다.
2. **카메라 종료와 데이터 보존.** 두 spread는 receipt로 보존됐지만 3회 연결 실패 후 fatal 및 서비스 재시작으로 목록에 돌아갔다. 재시도 지속·backoff 수정과 회귀검사, 사용자 복구 관측을 정리한다. 실제 retry 표식의 계측 한계는 검증 기록에 남긴다.
3. **Bluetooth·펌웨어 통합.** 불완전 line 수락 방지, host read 상한, V3 handshake/press-release, 셀 순서 매핑을 분리해 설명한다. 모터 펄스는 하드웨어팀의 실측 결과이며 SW는 이를 적용한 경계를 명시한다.
4. **부팅과 읽던 위치 복구.** 수동 Laptop 실행에서 Pi 서비스로 이식하고, 장치 준비·새 boot-id·동일 cursor·실제 출력을 각각 확인했다. 읽기 상태 전원 복구 1회와 쓰기 중 강제 차단 내구성을 구분한다.
5. **연속 입력 중 음성 lifecycle — 선택.** native stream 소유자와 취소 순서·generation을 정리한 수정, deterministic race 검사와 실제 음성 결과를 설명한다. 과거 crash dump의 정확한 원인까지 확정한 것으로 표현하지 않는다.

권장 분량은 3~4사례다. 근거: `H123_IMPLEMENTATION_RESULT_20260908.md`, `H123_FOLLOWUP_TCLOSE_HOST_READ_RESULT_20260908.md`, V3/R2 문서와 최근 Pi 시험 결과.

## 7. 그림·표·예시 후보

- **전체 흐름도 1개:** Pi를 현재 단말로 표시하고 receipt와 READY를 별도 지점으로 구분한다. 기존 Overview의 ‘Laptop 현재/Pi 예정’ 그림은 그대로 복사하지 않는다.
- **실제 촬영 변환 그림 1개:** 원본 → 페이지 외곽/책등 → 좌우 추출 → UVDoc. 동일 source_frame의 산출물만 묶는다.
- **문서 구조 표 1개:** 인식 영역 → Page IR → 읽기 focus. 지문·수식·선택지의 관계를 보여준다.
- **수식 예시 1개:** 검증된 `(x+1)^2=9`의 LaTeX → AST → 한국어 발화 → 점자 창. `docs/technical-overview/evidence/equation-revision-validation.json` 재사용 후보. 통제 예시이며 실물 교재 OCR 결과가 아님을 표시한다. 첨부 분수 예시를 유지하면 해당 식의 별도 실행 결과가 필요하다.
- **출력 대응 표 1개:** 6점 bit 배치, 10칸 창, FRAME 필드, STM 실측 pulse LUT. 실제 패킷과 설명용 예시를 구분한다.
- **검증표 1개:** 촬영·게시·읽기·전원·카메라 재연결의 조건/결과/증거 종류. 테스트 개수를 정확도나 속도 지표로 사용하지 않는다.

## 8. 남은 정리 작업의 우선순위

1. SW 본문 사실관계를 먼저 정리한 뒤 그림과 표를 선택한다. 이번에는 후보만 작성했고 본문 수정은 하지 않았다.
2. Pi·Desktop·Android·조명·45초 설정을 시연 기준으로 고정하고, 시작 시 모드 확인과 자료 저장 마감 절차를 운용 요약으로 정리한다.
3. 제출·배포 snapshot에는 승인된 변경 파일, Pi 해시, firmware 배포 기록을 묶는다. 기존 작업트리에 관련·무관 변경이 있으므로 전체 일괄 staging은 하지 않는다. 이번에 commit/push하지 않았다.
4. 시간이 허용되면 같은 배치에서 두 spread 촬영을 반복해 지연을 기록하고, 실제 단절의 waiting/restored 표식을 남긴다. 기본 기능의 새 개발보다 재현성·계측 보강에 해당한다.

기존 Technical Overview는 2026-09-10 기준이다. 알고리즘 설명은 재사용할 수 있으나 Pi 이식 계획, 과거 camera fatal 정책, 부팅·미완료 판정은 최신 기록으로 보완해야 한다. 이번에는 Overview도 수정하지 않았다.

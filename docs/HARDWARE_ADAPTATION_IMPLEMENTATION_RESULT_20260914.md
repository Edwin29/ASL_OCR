# 실측 펄스·GPIO 반영 및 PCA 역할 교환 결과

2026-09-14. 기존 통합 펌웨어에 한정한 구현과 소프트웨어 검증을 완료했다. 보드 flash, COM 개방, 서보 구동은 수행하지 않았다. H2/H3/H4는 아직 수용 전이다.

## 1. PCA 교환의 타당성

**왼쪽 열=0x41, 오른쪽 열=0x40으로 주소 역할을 교환하는 것은 과거 관측에 부합한다.** [기존 시험 기록](H2_H3_FIRMWARE_SERIAL_PHYSICAL_STATUS_20260908.md)의 C1/C2/C5/C10, 즉 CH0/1/4/9에서 이전 PCA1(0x40) 명령은 오른쪽 열만, 이전 PCA2(0x41) 명령은 왼쪽 열만 변화시켰다. 비대상 셀은 그대로였다. 단일 셀의 불확실한 잔류 패턴만으로 내린 추정이 아니다. C10 coupling 주장은 잘못된 CLEAR 기준 때문에 철회된 기록도 반영했다.

첨부 임시 코드의 PCA1=0x41, PCA2=0x40은 이 방향과 일치한다. 따라서 주소 역할을 교환하고 해당 주소에 첨부 표의 같은 채널 행을 연결했다. 채널 순서나 셀 순서를 뒤집지 않았고, 기존 오른쪽 열의 `BOTTOM_REVERSE_LUT`도 유지했다. PCA 주소 교환과 세 점의 비트 순서 보정은 서로 다른 문제다.

이 판정은 **교환 방향의 근거**이지 재정렬된 현재 하드웨어의 물리 정확성 인증은 아니다. 회로도만으로 U3/U4와 실제 I2C 주소를 연결할 수 없으며, 새 배선에서 모터/채널/실측표 행 대응이 달라졌을 가능성도 남는다. R2의 10셀 좌우 열 및 8상태 관측으로 닫는다. 현재 모터 대응이 다르면 실패한 채널과 실제 대응을 기록하고 그 범위만 재검토한다.

## 2. 반영 범위와 유지한 계약

| 변경 위치 | 반영 내용 |
|---|---|
| [main.c](../hardware/stm32/kitel2026final/Core/Src/main.c) | 공통 선형 펄스 계산을 20모터별 실측값 조회로 대체. PCA 왼쪽 0x41/오른쪽 0x40. 새 GPIO init 및 해당 설명 동기화 |
| [main.h](../hardware/stm32/kitel2026final/Core/Inc/main.h) | PAGE PREVIOUS=PB2, CONFIRM=PC0, MODE=PC8 |
| [.ioc](../hardware/stm32/kitel2026final/kitel2026final.ioc) | 위 GPIO input/pull-up/label 및 핀 목록 동기화 |
| [GPIO 계약 시험](../device-runtime/tests/integration/test_stm_mode_contract.py) | 기존 3개 기대 핀 번호를 새 배선으로 갱신. 나머지 계약 assertion 유지 |

Product source 3개와 기존 시험 파일 1개를 변경했다. 원본 첨부는 수정하지 않았다. 실측값은 원본의 20×9=180개와 정확히 일치하며, 기존 state 0..7이 사용하는 값은 160개다. 위치 8(180도)은 데이터만 보존하고 활성화하지 않았다. CLEAR는 이전 상태와 무관하게 기존 위치 0을 사용한다. PWM tick 변환은 기존 정수 내림 방식과 50Hz를 유지했다. 실측 μs와 실제 출력 파형 사이의 양자화·주파수 오차까지 측정한 결과는 아니다.

통신·버튼·구동 계약은 유지했다: V3 및 V2 호환 handshake, ACK/dedupe, DOWN press/release, 다른 방향의 반복, CONFIRM release 판정, MODE LOW=capture/HIGH=reading, IRQ ring 및 오류 후 재동기화, 엄격한 FRAME parser, PCA 실패 시 cache 미갱신과 다음 요청 재시도. 관련 13개 함수 본문이 변경 전과 동일함을 검사했다. 임시 코드의 UART 경로, 새 timeout, 부팅 자동 CLEAR, 180도 wrap CLEAR, MODE polarity 반전은 이식하지 않았다.

## 3. 검증과 한계

| 검사 | 결과와 증거 | 증명하지 않는 것 |
|---|---|---|
| 실측표·기존 C 함수/HAL stub | 180값 일치, 160 모터 상태, 640 셀 패턴, GPIO init, 잘못된 FRAME 7개 거절, 실패 채널만 재시도, high→CLEAR 위치0, cache PASS. [결과](evidence/hardware-adaptation-20260914/fixture-result.json) / [재현 코드](evidence/hardware-adaptation-20260914/verify_adaptation.py) | 실제 I2C/PWM/서보·배선 정확성 |
| 기존 RX ring fixture | queued order, UART error resync, overflow resync 3개 PASS. [결과](evidence/hardware-adaptation-20260914/rx-ring-fixture/result.json) | HC-05 실제 전송 무손실 |
| Host 단위·통합 계약 | STM serial, operation identity, mode contract 43개 PASS. [최종 JUnit](evidence/hardware-adaptation-20260914/host-contract-tests-final.xml) | 실제 버튼·오디오·물리 셀 결합 |
| STM32F446RE clean target build | STM32CubeIDE 2.2.0, exit0, 0 errors/0 warnings, ELF 생성. [로그](evidence/hardware-adaptation-20260914/target-build.log), [source/import/artifact manifest](evidence/hardware-adaptation-20260914/target-build-result.json) | flash 및 보드 실행 |
| Diff | `git diff --check` PASS | 전체 G3-A 재실행 |

첫 Host 실행은 다른 설치 parser를 가져와 collection error가 났다. checkout의 세 src 경로를 명시한 두 번째 실행은 40 PASS, 구 GPIO 기대값 1 FAIL, 기본 temp 경로 접근 거절 2 ERROR였다. 이 기록은 각각 [초기](evidence/hardware-adaptation-20260914/host-contract-tests.xml), [경로 정렬 후](evidence/hardware-adaptation-20260914/host-contract-tests-aligned.xml)에 보존했다. GPIO 기대값을 승인된 배선으로 동기화하고 새 isolated basetemp를 지정한 최종 실행이 43 PASS다. 이 환경 문제 및 기대값 갱신을 제품의 새로운 런타임 결함으로 집계하지 않는다.

실제 빌드는 Laptop의 `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\hardware-adaptation-20260914`에서 수행했다. 기존 integration source의 main.c hash 불변과 Python interpreter 및 세 package import의 `C:\ASL_OCR_INTEGRATION` 경로를 확인했다. 기존 integration source 배포는 하지 않았다. Laptop D:에 접근하지 않았다.

최종 ELF: 위 run의 `source\kitel2026final\Debug\kitel2026final.elf`, SHA-256 `4e415e19ffcdbcc845d2b8f27d6e719812dcbc4ed6e26082c2478e4334d4220e`.

최종 product hash:

- main.c: `16664d246b17d2385c552400efb19fc571ad113fc4a31fd07b95ab08f1b04b81`
- main.h: `79bb199dc49a9f2d4c8e74ac9d328ccd0cc978eaac4defcb137f16c30fe30ac4`
- .ioc: `6877dfc4249fb8ecaccf497c8bb86e5841e35d3c312e4b3f17317bd76d6713f6`

## 4. 다음 절차

1. Flash 전에 현 보드의 임시 image 복구 방법과 전체 전원 차단 수단을 확인한다. 새 배선/실측표에 맞지 않는 옛 선형 펄스 ELF를 무조건 rollback으로 쓰지 않는다. 필요하면 현재 flash를 읽어 별도 보존하는 절차를 준비한다. 서보만 끄려고 STM→PCA VCC/GND를 분리하지 않는다.
2. 새 run manifest에 source→ELF→flash verify, COM 소유자, 전원, startup/handshake FRAME 수를 고정한다. 정확한 송신 CSV·상한·stop condition·evidence 위치를 제시한 뒤 R2-O를 시작한다. 이번 턴에는 packet을 보내지 않았다.
3. CLEAR → C1..C10 좌우 열 → 각 모터 8상태와 CLEAR 복귀 순서로 실제 관측한다. [시험 계획 R2](HARDWARE_HANDOFF_REVIEW_AND_TEST_RESUMPTION_PLAN_20260914.md)의 기본 73 FRAME를 사용하되 실제 handshake 추가분은 실행 전 합산한다. 자동 타이머 대신 사용자의 `완료`로 다음 패턴에 진행한다. 걸림·발열·비정상 공급 등 구동상 위험은 중단하고, 독립 가능한 남은 입력 검사는 별도로 진행한다.
4. R2-I 일곱 버튼+MODE, R2-T 실제 Bluetooth 및 RX/reconnect를 독립 검증한다. 이후 fresh H2(콘솔 입력+실제 음성/셀), H3(물리 입력+실제 출력), 변경 checkpoint의 G3-A와 Pi 이식/H4 순서로 진행한다. 과거 H1 완료 범위는 유지하며 최종 장치의 camera preflight와 physical capture/finalize는 H4에서 다시 확인한다.

현재 남은 핵심 미검증 항목은 실제 보드에서의 주소/채널/점 대응, CLEAR 복귀, 새 GPIO의 버튼 의미·hold/release, 실제 transport와 audio/braille 결합이다. 컴파일 및 모의 회귀 PASS를 이 항목의 PASS로 대체하지 않는다.

## 5. 후속 실물 시험 결과 — 동일 날짜

위 내용은 flash 전 구현 보고다. 이후 사용자 승인으로 같은 ELF를 하드웨어팀 검증 보드(ST-LINK `066EFF505071655067246025`)에 download/verify/reset했다. 상세 경과와 원시 로그는 [R2-O 기록](evidence/hardware-resume-20260914-r2o/STATUS.md), [manifest](evidence/hardware-resume-20260914-r2o/manifest.json)에 보존한다.

- **실측값 출력 검증 PASS:** 사용자 요청으로 모든 모터의 8상태를 2초 간격으로 함께 표시하고 마지막 CLEAR를 적용했다. 9개 FRAME의 정상 파싱과 사용자의 전체 기대 패턴 일치·전체 수납 확인을 확보했다. 모터별 PWM 파형 측정이나 각 중간 상태 뒤 CLEAR 복귀 시험까지 통과한 것은 아니다.
- **셀 순서 불일치:** 논리 C1→물리 C10, C2→C9 및 C3의 같은 역순 양상을 관측했다. 사용자는 나머지 순서 검사를 생략하고 전체 역순으로 판정하도록 지시했다. 미관측 채널은 개별 PASS가 아닌 표본 기반 판단으로 남긴다. 향후 논리 셀→채널 보정 시 실측표는 실제 모터/채널에 유지한다. 아직 해당 코드는 수정하지 않았다.
- **첫 FRAME 수신 실패:** 최초 handshake 직후 `FRAME`의 `FR`이 누락되어 STM에서 거절됐다. 이후 연결 준비를 확인한 경로에서는 정상 파싱됐다. 원인 확정 및 production 초기 연결 재검증은 남아 있다. 진단 도구의 재연결 대기 방식 때문에 발생한 별도 전송 미확인/0-FRAME timeout도 원시 기록에 구분했다.
- 현재21 FRAME 송신, 마지막 CLEAR 유지, COM 포트 종료. 새 flash나 product 변경 없이 이번 관측을 기록했다. R2-O 전체, H2/H3/H4를 PASS로 선언하지 않는다. 다음 독립 경계는 버튼/MODE 시험이며, fresh H2 진입 전 셀 순서와 초기 수신 경계 수정·재검증이 필요하다.

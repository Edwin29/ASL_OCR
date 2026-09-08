# Repository checkpoint — 2026-09-08

사용자 요청에 따라 `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e` 이후 누적 working-tree 변경을 보존하는 로컬 Git 체크포인트다. 새 product correction, Laptop 배포, firmware flash 또는 integration acceptance 선언이 아니다.

## 포함 범위

- 기존 S-01/S-02 parser 안정화, H1/H2/H3 camera/audio/input/serial/CLI 수정과 targeted regression.
- Firmware `hardware/stm32/kitel2026final/Core/Src/main.c`, `stm32f4xx_it.c`, `Core/Inc/main.h`, `stm32f4xx_it.h`: 기존 승인된 RX interrupt/ring-buffer 변경 포함. FRAME/V3 계약 및 물리 mapping 변경 없이 현재 작업본 보존.
- 진단, architecture assurance, 우선순위, work packets, 실행 상태, 하드웨어팀 인계, H1 read-only 후속 조사 및 새 진단 스크립트.
- 선별된 text/JSON/log evidence 및 작은 이미지. 전체 원본 경로·크기·SHA-256은 `evidence/REPOSITORY_EVIDENCE_INDEX_20260908.json` 참조.

대용량 원본 캡처와 generated pytest/build 산출물은 Desktop 기존 경로에 보존하며 Git에는 넣지 않았다. 해시 목록은 원본 백업을 대체하지 않는다. 일부 image replay에는 이 로컬 원본이 필요하다. 해시는 Git 줄바꿈 정규화 전 working-copy bytes 기준이다. 선택된 텍스트에 credential 패턴 검사를 수행했으며 일치 항목은 없었다.

Windows 예약 파일명 `com5.txt`인 로그 7개는 원본을 그대로 보존하고 같은 디렉터리의 `trace-com5.txt` 사본을 Git에 포함했다. 내용은 byte-identical이며 해시 목록에 양쪽 경로가 기록되어 있다. 전체 staged whitespace 검사에는 기존 product EOF 빈 줄 외에 문서의 Markdown hard break 및 원본 로그 공백도 검출됐다. 증거 원문을 정리 목적으로 수정하지 않았다.

## 이번 체크포인트 검증

| 범위 | 결과 |
|---|---|
| Scanner engine / v3a5 / camera recovery | 38 passed |
| Device audio lifecycle, boundary, follow-up, serial, scanner adapter, operation identity, mode, composition | 94 passed |
| Parser problem units / VL page IR | 30 passed |

합계 162 passed. 전체 repository suite 재실행 또는 물리 검증 결과가 아니다. 기존 전체 Scanner suite의 P030 3 FAIL은 `H1_UP_FOLLOWUP_IMPLEMENTATION_RESULT_20260908.md`의 기록을 유지한다. `git diff --check`는 기존 `adapters/reading_audio.py` EOF 빈 줄 1건을 보고했다. 이번 작업에서는 product source를 추가 수정하지 않았다. Firmware 재빌드/flash는 하지 않았다.

## 배포 및 acceptance 경계

- Desktop engine SHA-256: `6ee44d42cae3456544e58c183c193f970b1467ef26a616feeb9ad6e563dfc380`.
- 최근 확인된 Laptop engine SHA-256: `f223f744fe2fd6a6818ea7bed4ed4f522e27f90590fc2c477fcb40fdbe8e427f`. 최신 Desktop 두 engine correction은 아직 Laptop에 배포하지 않았다. 동일 source로 간주하지 않는다.
- 현재 firmware main.c SHA-256: `f0b93413f352be398dac62db6a64b2d17c19f1b8e14faf874371beddaf6ba1c1`. 기존 firmware alignment/flash evidence와 이번 Git checkpoint는 구분한다.
- 조정된 camera scene에서 26/27 23/23, 28/29 21/22 exact pair와 recorded engine replay 7.385초 N5 DIFFERENT를 확보했다. 별도 phase 수집 및 fixture replay이므로 continuous live capture, 두 durable receipts, fresh READY 통과가 아니다.
- UP/PREV/CONFIRM/MODE 및 NEXT 간헐 입력, physical CLEAR 잔류는 관련 보고서/하드웨어팀 인계 상태를 유지한다. H4는 BLOCKED다.

다음 작업은 `H1_READ_ONLY_FOLLOWUP_INVESTIGATION_20260908.md`의 연속 Scanner lifecycle 관측이다. 이번 저장 작업은 실행 중단점 보존이며 새 실험을 시작하지 않는다.

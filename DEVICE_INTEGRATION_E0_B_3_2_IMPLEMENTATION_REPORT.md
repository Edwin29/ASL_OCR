# Device Integration E0-B.3.2 구현 보고서

작성일: 2026-09-02
작업 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_3_2_IDENTITY_ROLE_REPORT_CONTRACT_CORRECTION_WORK_PACKET.md`
상태: **구현 및 local 전체 회귀 완료**

## 결과

candidate identity와 전송 후 page-change identity를 explicit role로 구분하고 E0-B replay report를 schema
v2로 교정했다. 실제 Laptop 성공 로그에 없던 314/315 4/5 hard-reject와 318 1/5 EOF abort를 필수
성공 조건에서 제거했다. Scanner threshold, collector decision, artifact 수와 delivery ordering은 변경하지
않았다.

## 변경 내용

- Book Scanner `OpaqueIdentityRole`
  - `candidate_verification`
  - `page_change`
- candidate selected 및 opaque collection started/observed/decided/aborted에 bounded role
- ACK/duplicate suppression 뒤 page-change monitoring 시작 event
- Device Runtime feedback role whitelist
- report schema v2
  - candidate attempts와 page-change checks 분리
  - explicit role missing/unknown failure
  - candidate 2개 각각 5/5 `different`
  - spread `[1,2]`, EOF 2/2
  - 새 datapack/scan/save revision 1/reading 4페이지 lineage
  - Server 2/4/0 final evidence
- Quickstart, Laptop 문서, E0-B.3 packet/report와 handoff 정정

## 검증

| 범위 | 결과 |
|---|---:|
| Book Scanner role/events 집중 | 14 passed |
| Device adapter/report 집중 | 11 passed |
| Book Scanner 전체 | 299 passed |
| Device Runtime 전체 | 107 passed, 3 skipped |

Document Parser 제품 코드는 변경하지 않았다. 최신 기준선 602 passed, 4 skipped를 유지하며 실제 Server
summary 결합은 다음 E0-B.4-L에서 수행한다.

첫 전체 suite의 공용 `tmp` basetemp 권한 오류는 각 프로젝트 내부의 전용 ASCII basetemp로 재실행해
해소했다. 제품 assertion failure가 아니며 전용 임시 디렉터리는 제거했다.

## 남은 경계

- 실제 Laptop에서 E0-B.3.2 role이 포함된 transcript 재수집
- Desktop Server summary 2/4/0 보존
- report v2 final `passed` 산출물 생성
- physical camera/STM/audio acceptance
- production OCR/TTS/braille content acceptance

위 항목은 각각 외부 환경 또는 별도 품질 authority가 필요하므로 이 local 교정 패킷에 포함하지 않았다.

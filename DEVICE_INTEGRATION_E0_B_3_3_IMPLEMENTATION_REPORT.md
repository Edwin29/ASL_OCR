# Device Integration E0-B.3.3 구현 보고서

작성일: 2026-09-02
작업 패킷: `DEVICE_INTEGRATION_E0_B_3_3_ACK_CALLBACK_DIAGNOSTIC_FORWARDING_WORK_PACKET.md`
상태: **구현 및 local 전체 회귀 완료**

## 결과

Book Scanner ACK callback이 생성한 page-change `identity_collection_started`가 Device adapter에서
버려지던 전달 경계를 복구했다. ScannerRuntime port가 callback Scanner events를 명시적으로 반환하고,
Coordinator는 `spread_sent`를 먼저 방출한 뒤 bounded callback diagnostic을 기존 feedback 경로로
처리한다.

새 기대 순서는 다음과 같다.

```text
candidate_verification decided different 5/5
spread_sent sequence=N
identity_collection_started identity_role=page_change spread_id=<accepted spread>
identity_collection_progress identity_role=page_change ...
```

Scanner candidate/page-change 판단, identity N/K, artifact, durable queue, ACK, sequence와 save/read 동작은
변경하지 않았다.

## 변경 내용

- `ScannerRuntime.apply_delivery_update()` 반환 계약을 `tuple[ScannerEvent, ...]`로 변경
- Book Scanner adapter가 delivery callback raw event를 기존 `_convert_event()` whitelist로 변환
- session/event ID lineage와 raw token/digest 비노출 유지
- Coordinator가 ACK feedback 뒤 callback diagnostic 처리
- terminal delivery 및 stable event ID dedup으로 중복 feedback 방지
- report page-change check에 `explicit_start`와 accepted spread/start frame lineage 보존
- progress-only E0-B.3.2 로그 호환 유지
- replay wrapper와 Laptop 문서에 E0-B.3.3 기대 순서 추가

## 검증

| 범위 | 결과 |
|---|---:|
| Device adapter/Coordinator/report targeted | 37 passed |
| Book Scanner 전체 | 299 passed |
| Device Runtime 전체 | 109 passed, 3 skipped |

첫 전체 suite 명령은 저장소 root에서 pytest target을 생략해 `tmp`에 보관된 외부 dependency test와 세
프로젝트를 함께 수집한 실행 오류로 중단됐다. 제품 assertion failure가 아니다. Book Scanner와 Device
Runtime 각각의 작업 디렉터리 및 전용 ASCII basetemp를 지정해 재실행한 위 결과는 통과했다.

Document Parser 제품 코드는 변경하지 않았다. 실제 Laptop replay와 Server evidence 재수집은 이 local
패킷에 포함하지 않았다.

## 남은 경계

- E0-B.3.3 revision으로 fresh datapack Laptop transcript 보존
- 각 `spread_sent` 뒤 explicit page-change start와 accepted spread lineage 확인
- pinned source report와 Desktop Server summary 2/4/0 보존
- schema v2 final `passed` report 생성
- physical camera/STM/audio acceptance
- production OCR/TTS/braille content acceptance

위 첫 네 항목은 다음 E0-B.4 actual evidence closure에서 수행한다. commit·push는 별도 승인 경계다.

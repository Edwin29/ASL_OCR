# Camera 종료 후 초기화처럼 보이는 현상

## 확인 결과

사용자는 spread2개 생성 뒤 Android IP Camera 앱 종료로 초기화처럼 보였다고 보고했다. read-only 조사 결과 **데이터 삭제가 아니라 camera fatal 뒤 systemd 자동 재시작으로 capture 카탈로그에 복귀한 현상**이다.

- 이전 PID997 로그: monotonic1410.446에 `fatal_error(reason=camera_unavailable)`.
- 새 PID2040 로그: monotonic1438.611에 capture datapack_selection. 약28.17초 뒤 화면 복귀.
- `asl-production` active/NRestarts1. 현재 ExecMainStatus0은 새 프로세스 상태이므로 이전 종료코드0의 증거로 해석하지 않는다. source fatal exit는2지만 이전 프로세스 실제 exit status를 별도 journal로 확보하지는 못했다.
- boot supervisor 정책은 Restart=on-failure, RestartSec15. 제품 세션을 자동 재선택하는 정책은 없다.

## 데이터 보존

데이터팩 `새 데이터팩 2026-09-16 01:12 #31`, ID `datapack-652b416b2bc84a2ca9ca59c881327bb3`.
세션 `scan-ff28551c66cc4d0b92e1140772b2be05`.

| 순서 | 로컬 outbox | 서버 응답 | receipt |
|---|---|---|---|
|1|acked, attempt1|201|spread-receipt-8e95c94da2fbf597d96b608a19ec7ee9|
|2|acked, attempt1|201|spread-receipt-0b2cca401ca6b9eefcb53e3fc7c76d52|

서버 세션open, ready fragments2, processing/error/rejected0. finalization=null, published_revision=null, catalog=draft. `scan_stopping`/`finalizing`/`datapack_saved`는 해당 실행에 없다. 즉 수신·처리 완료와 READY 게시를 구분해야 한다. 두 spread의 원본 쪽번호 재검수는 이번 조사 범위에 포함하지 않았다.

## source 경로 및 판정

- `book-scanner/src/book_scanner/video/engine.py`: camera read/transport failure의 `_fail_snapshot`/`_fail` 경로.
- `device-runtime/src/asl_device/coordinator.py:388`: scanner FATAL을 coordinator fatal로 전달.
- `device-runtime/src/asl_device/application.py:148`: fatal_reason 존재 시 exit2.
- `docs/evidence/pi-boot-20260916/asl-production.service`: 실패 시 재시작. 새 프로세스는 기존 CLI capture catalog에서 시작한다.
- `document-parser/src/document_parser/server/s0_services.py:214`: 같은 datapack/device의 open 또는 sealing 세션이 있으면 기존 세션을 반환한다.
- `device-runtime/src/asl_device/coordinator.py:307`: 선택 후 open 세션의 known_status를 읽고 마지막 sequence를 복원한다.

Pi에서 실제 실행된 coordinator/application/engine 해시는 Desktop과 모두 일치했다. 각각49dc06104a944559c0d7ecfdce9953a405ddc8a55c66285f37a688d481282661 / 244dda03e6fe5f11daabbeac93f0c136fd17edc4d8c7e162834b20a91b7890fe / 6ee44d42cae3456544e58c183c193f970b1467ef26a616feeb9ad6e563dfc380.

분류: 카메라 앱 종료는 사용자 보고와 camera_unavailable에 부합하는 environment_failure. fatal 및 supervisor 재시작은 현 정책의 expected_behavior. 자동 세션 재개가 없는 UX 제약은 명시해야 한다. 원시 HTTP 예외가 최종 feedback에 보존되지 않아 timeout/connection refused/기타 전송 실패 중 구체 원인은 insufficient_evidence. 데이터 손실 결함 증거는 없다. 이번 조사에서 재현을 위해 카메라를 추가로 끄거나 제품을 수정하지 않았다.

## 복구 및 시연 운용

새 데이터팩을 만들 필요는 없다. Android source를 복구한 뒤 capture catalog에서 기존 #31을 선택하면 source상 동일 open 세션/sequence를 복원할 수 있다. 두 건으로 마칠 목적이면 재진입 후 추가 촬영을 기다리지 않고 CONFIRM LONG으로 finalize하는 경로를 사용하고 through_sequence2 및 새 READY를 실제 로그로 확인해야 한다. 이 복구 경로는 아직 이번 incident에서 실실행 검증하지 않았다. 자동 중복 방지 reference bank까지 완전히 복구된다고 확대 해석하지 않는다.

시연에서는 카메라 앱을 `datapack_saved`/READY 게시까지 유지한다. 앱을 끄는 행위는 capture 완료 명령을 대체하지 않는다. 향후 보완 후보는 camera 오류 시 같은 세션의 재연결 또는 명확한 재개 안내이며 이번에는 적용하지 않는다. 기존 부팅·idle reading 전원 복구 PASS를 capture 중 카메라 장애의 자동 세션 복구 PASS로 확대하지 않는다.

Evidence: [incident files](evidence/pi-camera-restart-20260916/): interrupted.log, restarted.log, audit.json. 기존 runtime/state 보존. 제품 수정0.

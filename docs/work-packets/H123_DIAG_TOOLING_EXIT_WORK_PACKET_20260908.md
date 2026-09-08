# Proposed bounded implementation packet T — Tooling / exit semantics

상태: **제안만 작성; 구현 미승인/미실행**. 근거: [진단 보고서](../H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md).

## T1 Android source preflight — confirmed_product_defect / 기존 P1

현재 `_probe_e0b_profile`은 Android HTTP profile을 거부하고 `_probe_camera`는 OpenCV webcam branch로 들어간다. Strict Android readiness와 무관한640×480 camera PASS가 생성된다. Actual Device factory는 strict source를 사용하므로 production fallback과 혼동하지 않는다.

최소 변경: `device-runtime/src/asl_device/laptop_acceptance.py`1파일 우선. 필요하면 existing factory의 작고 읽기 쉬운 source selection 재사용만 허용한다. Config→실제 source class/endpoint identity/requested·effective resolution을 동일 계약으로 검사하고 Android profile에서 OpenCV constructor 호출0을 보장한다.

Targeted tests: Android/UVC/PC profile 분기, authenticated secret-file reference, self-signed TLS가 Android profile에만 적용됨, wrong auth/timeout/permanent failure가 올바른 failed check, camera read 후 close, 보고서 secret 값0. Fake test 후 real strict read-only snapshot probe를 새 C: diagnostic root에서 실행하며 speaker/serial/upload는 열지 않는다.

## T2 Fatal result propagation — confirmed_product_defect / D01 Deferred 유지

Real Coordinator fatal_error→STOPPED 뒤 Application.run이 정상 return하면 CLI는0을 반환한다. Production supervisor가 이를 health/restart contract로 사용한다는 증거가 없어 이번 진단에서 P1로 자동 승격하지 않는다.

최소 변경: coordinator/application/CLI 중 terminal outcome을 보존·반환하는 데 필요한 최소 경로, 최대3 production파일. 정상 operator stop과 fatal exit를 구분한다. 기존 feedback 이벤트/상태전이·durable lineage/cleanup semantics 유지. Exception 전체를 fatal0으로 swallow하지 않는다.

사용 중인 launcher는 최대1개 작은 변경을 별도로 검토한다. PowerShell `-NoExit`와 child exit code, scheduled task의 result는 서로 다르다. Child nonzero가 task policy에서 무엇을 의미하는지 문서화하고 exit-only 판단을 넣을 때만 severity 재검토한다. SSH credential/task 권한/서비스 architecture 변경은 범위 밖이다.

Targeted tests: 실제 Coordinator startup/scanner fatal→Application→CLI child nonzero; 정상 stop0; KeyboardInterrupt 정책; unhandled exception nonzero; cleanup이 원 fatal reason을 덮지 않음. Wrapper가 명시 child exit를 전달하고 event log와 supervisor-visible result가 일치한다. 사전에 실제 supervisor health/restart contract 사용 여부를 확인한다.

## Evidence tooling correction — 별도 docs/runtime 수준

H1 transcript 조각과 summary event_count0을 complete event log로 쓰지 않는다. H2는 verified4,369-byte prefix 뒤 재실행 로그가 append됐다. 새 실행에는 unique run/boot ID, parsed config와 injected composition 차이, initial mode·actual restored cursor, log encoding, exit outcome을 기록한다. 기존 evidence를 재작성하거나 삭제하지 않는다.

Scope는 small launcher/evidence reporting이고 new monitoring architecture가 아니다. Report에 production adapter와 harness override를 따로 기록한다. SSH interactive task를 actual speaker acceptance로 간주하려면 실제 device context+human observation이 있어야 한다.

## Validation / stop / deliverable

새 evidence 위치 `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\tooling-<fresh-id>`. Expected serial packet0, servo motion0, production upload0. Snapshot probe는 read-only source readiness만 검증한다.

정상/실패 분기를 의도적으로 발생시키는 fake tests→관련 device subsystem→combined G3-A 검증. Live source probe는 invariant/횟수/상한을 먼저 보고한다. Credential 노출, webcam fallback, 다른 runtime 경로 또는 source identity drift가 있으면 중단하고 증거 보존한다.

최종 diff·before/after 결과·현재 severity·supervisor contract 설명을 제출한다. T1/T2는 independent subcommit으로 리뷰 가능해야 한다. 이 packet은 camera liveness engine/audio/STM correction을 포함하지 않으며 H4 readiness를 선언할 수 없다.

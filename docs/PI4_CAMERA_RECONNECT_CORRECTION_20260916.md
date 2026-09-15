# 카메라 연결 끊김 중 세션 유지 수정

## 변경

사용자가 카메라 비정상 연결 해제 시 앱을 종료하지 않고 계속 재연결하도록 변경을 승인했다. 원인은 HTTP snapshot adapter가 retryable 오류도3회 연속이면 terminal error로 올리는 정책이었다. 새 장기 장애 회귀검사는 수정 전 세 번째 시도에서 실패하여 이를 재현했다.

`book-scanner/src/book_scanner/video/sources.py` 한 제품 파일을 변경했다. retryable timeout/connection 및 기존408/429/500/502/503/504 정책은 계속 재시도한다. 대기 간격은0.25→0.5→1→2→4→5초로 증가하고 이후 최대5초를 유지한다. 각 요청의 기존 timeout은 유지되므로 실제 요청 시작 간격은 요청 소요시간+backoff+scanner poll 간격이다. 5초 안의 복구를 보장한다는 뜻은 아니다.

read는 대기 중None을 반환하고 sleep/추가 transport loop를 실행하지 않는다. 동일 source/session/frame counter를 유지하고 성공 시 실패 횟수와 backoff를 초기화한다. 시작 장애1회와 복구1회만 `snapshot_connection_waiting`/`snapshot_connection_restored`로 기록하며 URL/credential/원시 exception은 넣지 않는다. stop과 generation 기반 늦은 프레임 폐기는 유지한다.

영구 오류(인증/TLS/잘못된 endpoint 등), 이미지 decode 실패의 기존 처리는 유지한다. 이번 패치는 연결 끊김으로 분류된 retryable transport의 연속 실패 상한만 제거한다. camera fallback, N/K/identity45초, FRAME/V3, state/credential 변경 없음. Coordinator/Scanner architecture 변경이나 세션 재생성 없음. 요청이 진행 중이면 기존 request timeout 동안 입력 반응이 지연될 가능성은 남으며 이번 변경은 비동기 입력 구조 개편이 아니다.

## 검증

- 수정 전 새 long-outage test: 세 번째Timeout에서 FAIL.
- 수정 후 Scanner video216개 + Device application/coordinator/scanner adapter55개 = **271 PASS**.
- 초기 전체검사38 setup error는 기존 Windows TEMP 접근권한 문제. 뒤의 합동 실행3 collection error는 두 subsystem의 동일 tests package 이름 충돌. 새 전용 temp 및 별도 프로세스로 실행하여 통과했고 초기 XML도 보존했다.
- 장시간 장애150초 이상, rate bound, 회복 후 실제 decoded frame 및 counter 연속, backoff reset, stop 후 요청 없음, TLS/auth permanent 유지 검사.
- receipt 이후 장애150초 및 복구에서 accepted identity bank 불변, 같은 페이지 추가 artifact0, cancel 가능 확인. 이는 deterministic fake adapter/frames 증거로 실제 촬영 성공과 구분한다.
- Pi 실제 Python3.13 runtime의 독립 fake-transport 검사:40회 장애/가상182.75초 후 복구·stop·TLS 구분 PASS. pytest 추가 설치 없음.

## Pi 반영 및 현재 상태

제품 source1파일 반영. 변경 전 SHA256 `1a5cef671561654060cbf573de15c2620b56f52219f7ab3ca161fa6314a28f47`, 변경 후 `be7f3c57c262c2ca24b17a4c0f64972b39f4ea630029daff3c294b57a6ba73c0`.

Pi `runtime/camera-reconnect-20260916/sources.before.py`에 원본 보존. 앱 stop/exit0 확인 후 원본 해시 일치 assertion, 새 파일 compile, atomic replace를 수행했다. 재시작 후 PID2576 active/restart0 및 catalog 안내 audio completion 확인. config/state/#31의 기존2개 receipt를 초기화하지 않았다. 새 run은 `runtime/boot-20260916/20260915T163658Z-2576`.

Desktop과 Pi에 반영했고 Laptop source는 이번에 배포하지 않았다. 되돌리기는 서비스를 멈춘 뒤 보존 원본으로 이 파일만 복원하고 다시 시작한다. 상태와 evidence는 삭제하지 않는다.

## 남은 실제 관측

실제 Android 앱 종료→재실행 상황에서 동일 PID/scan session 유지, 재연결 로그, 기존2건 receipt 유지와 CONFIRM LONG finalize를 확인해야 한다. 실제 카메라 끊김의 새 테스트 결과는 아직pending이다. 사용자의 기존 촬영 배치/조명은 유지하며 반복 장애 시험을 무단 실행하지 않았다.

근거: [evidence](evidence/pi-camera-reconnect-20260916/), scanner-r2.xml, device-r2.xml, probe.log, deployment.json. 제품 수정1파일, 회귀 test1파일 및 진단/문서 추가.

## 후속 실제 관측 및 서버 확인

사용자: “카메라 연결 끊김 수정의 경우 끊었다 돌아옴을 확인함. 데이터팩 생성 완료.” 실제 카메라 복구는 사용자 관측 PASS로 기록한다.

확인 시 새 boot-id `abc831ca-63fd-4712-bb0b-7ef87d9e434d`, PID1007, NRestarts0, active였다. 수정 직후 PID2576와 동일하다는 주장은 하지 않는다. 재부팅 후 run `20260915T163819Z-1007`에서 수정 후 source SHA256 일치를 재확인했다. 이번 run에 fatal_error는 없으나 `snapshot_connection_waiting/restored`도 기록되지 않았다. 따라서 실제 transport retry가 발생한 정확한 구간/횟수는 사용자 관측만으로 확정할 수 없다. 카메라 끊김 시점이 read 사이였거나 촬영 외 상태였는지 추가로 검증하지 않았으며, 실제 retry branch의 자동 계측 PASS와 구분한다.

로그와 서버 read-only DB 대조 결과:

- 기존 #31: 같은 `scan-ff28551c66cc4d0b92e1140772b2be05`를 이어받아 sequence3을 추가했고 through_sequence3으로 sealed, READY revision1 게시. 기존2건 뒤 순서 연속성 회복 증거다. 추가 spread의 페이지 내용/중복 여부는 이번 확인에서 검사하지 않았다.
- #31 재선택 후 through_sequence0으로 한 번 더 seal된 것은 기존 revision1 유지이며 추가 촬영 성공으로 세지 않는다.
- 새 `01:46 #32` (`datapack-0384e9aab35a4d43a926e8dae0e6f050`): sequence1/2 전송 완료 → through_sequence2 → datapack_saved revision1. 서버 sealed/ready revision1, error 없음. 게시시각 한국시간2026-09-16 01:57:21.

근거 파일 `live-validation.log`, `live-server-status.json`. 이번 관측 반영에 추가 제품 변경 없음. 새 #32의 실제 읽기 내용/출력 품질은 이번 생성 보고와 구분한다.

# Pi production 시연 시험 전환 — 2026-09-15

사용자는 문자열 일치를 중복 차단에만 쓰더라도 불안정한 입력 때문에 과도하게 보류될 위험이 있다고 지적했다. 이 우려를 열린 risk로 유지한다. K_same=1의 비대칭 목적(같은 페이지의 재전송 방지가 우선)은 유지하며, 새 쪽 승인용 문자열 조건 분리 실험은 실행하지 않고 보류한다. 현재 실패를 timeout 단독 원인으로 확정하지 않는다.

개별 진단 테스트를 생략하고 실제 시연 환경의 Pi production module로 검증한다. 생략한 테스트를 PASS로 기록하지 않는다. 기존 소스·승인된 ARM cpu_threads=1 correction·V3-only·실측 펄스/셀 매핑을 유지하고 상태/데이터를 초기화하지 않는다.

1. 기존 READY로 읽기: 실제 물리 MODE/버튼 → Pi DeviceApplication/Coordinator → Desktop S0 → 인증 음성 → Pi AUX 및 실제 점자. 시작은 production CLI `--initial-mode reading`; 초기 firmware MODE 보고로 화면이 바뀌면 그 사실을 기록한다.
2. 사용자가 읽기 확인 후 capture: 같은 production 구성에서 Android live camera, 새 datapack, 26/27 및 28/29 두 spread, 각 durable receipt와 전송 완료 안내, CONFIRM LONG finalize, fresh READY, 다시 읽기.
3. 1차는 현재 설정 그대로. N5/K/8초 및 OCR 후보·confidence·입력 해상도 정책 변경 없음. 사용자 앵글/초점 조정은 시각과 결과를 기록한다.
4. 2차는 1차 로그의 유효 관측·missing·timeout·실제 처리 간격에 근거해 필요하면 collection timeout 등 runtime 설정의 제한된 조정을 별도 run/config hash로 수행한다. 변경 전 값·선정 근거·정해진 관측 budget을 기록한다. 후보/identity/protocol 기준 변경까지 포괄 승인된 것으로 해석하지 않는다.

Laptop에 재사용한 비례 미리보기와 좌우 footer 확대 창을 유지한다. footer의 빨간 박스는 사용하지 않는다. 독립 camera client이므로 Pi와 같은 물리 배치를 보여주지만 동일 프레임 증거가 아니고 추가 camera 요청 부하가 포함된다. 실제 Pi 프레임 스트리밍을 위해 product adapter를 교체하지 않는다.

run root: `/home/user/ASL_OCR_PI/runtime/production-demo-20260915-r1`; Desktop evidence: `docs/evidence/pi-production-demo-20260915-r1`. launcher는 production subprocess, 출력 로그, exit code 기록만 담당한다. 제품 adapter 주입/대체 없음. 동일 stable device ID와 기존 runtime state를 유지한다. 기존 source를 다시 배포할 필요가 있는지는 identity 확인 후 판단한다.

물리 동작: 연결 시 수납 FRAME, 읽기 선택/이동 시 동일 focus의 FRAME과 AUX 음성. 중단은 해당 앱 SIGINT 또는 사용자 종료 요청으로 수행하고 별도 servo diagnostic/frame sequence를 삽입하지 않는다. 부팅 자동 시작과 공동 전원 차단/복구는 최소 기능 검증 후 수행하는 기존 순서를 유지한다.

## 1차 시작 상태

- 기존 Pi runtime 사용. 세 package import가 `/home/user/ASL_OCR_PI/source` 아래임을 확인했다. ARM OCR correction hash `18d287218c164164a61266612c01e694966cf1a7d1e51efce919355f1ab43596` 확인. 새 product source 배포/수정 없음.
- config hash `2cb0cd6948369117855556a9b17a662e6a3168cdca1117d9f811681439a05aa8`; STM `/dev/rfcomm0`, 9600 baud, 실제 audio enabled, Android profile, headless Pi preview=false. N5/8000ms 유지. 전체 effective policy 및 source hashes는 run manifest에 보존했다.
- authenticated catalog 28개 조회 성공, default AUX 출력 index0. 사용자 관측 가능 응답 후 production module PID13464, supervisor13462로 시작했다.
- `screen_changed: datapack_selection, mode: reading`, catalog/system audio 재생 완료 로그 확인. rfcomm `connected [tty-attached]`. 이 사실만으로 wire V3 handshake 또는 물리 셀 적용을 확인했다고 기록하지 않는다.
- Laptop 수동 실행 task `ASL_Pi_ProductionPreview_20260915_R1`, runtime `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\pi-production-preview-20260915-r1`. 창 실행 후 첫 실제 영상 이전에 SnapshotTransportError가 기록됐다. 사용자에게 Android 앱 및 영상 갱신을 확인 요청했다. 상시 영상 제공 완료는 아직 아니다. source 실패를 webcam으로 대체하지 않았다.
- 읽기 물리 버튼/음성/점자 묶음 절차를 안내했다. 사용자 결과 대기. capture 시작은 아직 요청하지 않았다.
- 시작 약85초 후 `screen_changed: mode=capture`가 기록됐다. 수동 조작인지 초기 MODE 보고인지 로그만으로 확정하지 않는다. CONFIRM 전에 물리 레버를 읽기 쪽으로 설정하고 읽기 안내를 확인하도록 알렸다. CLI initial-mode는 이후 physical MODE를 무시하지 않는다.

읽기·촬영·receipt·READY·사용자 청취·물리 점자 적용은 각각 판정한다. 미확인 상태에서 H4/integration ready를 선언하지 않는다.

## 읽기 완료 및 capture 준비

사용자는 읽기 모드 복합 시험 전부 정상이라고 보고하고 capture 진행을 요청했다. 안내한 기존 READY/물리 입력/AUX/점자 subset을 사용자 관측 PASS로 기록한다. `stdout-reading-complete.log`에는 reading_resumed 2회, audio started125/completed25/interrupted107회가 있다. catalog/system 및 추가 사용자 조작이 포함된 전체 스냅샷 수치이므로 개별 버튼별 횟수나 일대일 audio completion으로 해석하지 않는다. 해당 앱 PID13464 생존을 확인했다.

사용자는 Android 앱 및 26/27 준비 완료를 확인했다. 오류 상태로 남은 Laptop 미리보기01은 stop marker 정상 종료 후, 같은 설정·동일 동작의 미리보기02를 새 로그 디렉터리로 시작했다. 초기 오류 evidence는 보존한다. 제품 또는 timeout 변경 없이 capture 1차로 진행한다. 실제 영상 갱신을 확인한 뒤 새 데이터팩을 선택하도록 안내한다.

미리보기02는 가로4000×3000의 실제 영상6개를 받은 후 OpenCV `error`로 갱신이 중단됐다. 기존 실행기는 상세 cv_error를 기록하지 않아 원인은 미확정이다. 정상 stop 후 새 진단 미리보기03에서만 OpenCV thread1, cv_error/code/func 기록, worker 종료가 확인된 decode/OpenCV/명시적 retryable transport 오류의 5초 간격 최대3회 연속 재연결을 적용했다. 성공 프레임 후 재연결 횟수는 초기화한다. 인증/permanent 오류는 자동 재시도하지 않는다. 마지막 영상 경과시간/오류 표시는 유지하며 frozen 영상은 성공으로 기록하지 않는다. 이는 별도 Laptop viewer 변경이며 Pi production source, N5·8000ms, 카메라 TLS/인증·해상도에는 변경이 없다. 새 viewer는 py_compile 통과 후 실행했다.

미리보기03 PID41132에서 가로4000×3000의 연속 영상19개와 최신 heartbeat를 확인했다. 이 확인은 viewer 수신 경계에 한하며 Pi identity/전송 성공을 의미하지 않는다. 창을 유지하고 capture 묶음 절차를 안내한다. 각 spread 전송 안내가 2분 동안 없으면 페이지/세션을 초기화하지 않고 현재 상태를 보고받아 로그와 대조한다. 이는 실패 보고 시점이며 production timeout 변경이나 전체 시험 자동 중단 조건이 아니다.

## 1차 capture 결과 및 2차 전환

사용자는 5분 이상 상황에 맞는 안내는 들렸지만 spread가 생성되지 않았다고 보고했다. 첫 로그 스냅샷은 후보11회/timeout11회였고, 최종 보존 로그에서는 후보16회였다. 실패 경계는 candidate_verification identity collection: 유효 관측이0~2개에 머물러 unknown timeout이 반복됐다. 기록된 관측 처리 간격 중앙값은 약5334ms이며 N5는 누락이 없어도 약27초가 필요한 처리속도다. 이 값은 실제 촬영의 preview 동시 부하 및 현재 환경을 포함하고 순수 CPU 시간은 아니다. 문자열 쌍 누락도 존재하므로 시간만 늘리면 해결된다고 확정하지 않는다.

실제 scan_session은 `scan-51dfd9e927284b5e8da61ab139bdf7b6`, 선택한 대상은 기존 `datapack-b7d5a769ad5347738d491f1b39e5e909`였다. 새 데이터팩 생성 수용은 아니며 fidelity 차이를 기록한다. 최종 outbox를 read-only 조회하여 해당 세션 row0개, spread_sent0회를 확인했다. 이후 through_sequence0으로 finalize되어 기존 revision1의 datapack_saved가 기록됐으나 새 spread 수신/게시 증거가 아니다. 기존 데이터와 모든 로그는 보존했다.

종료 과정에서 nohup/background 실행으로 SIGINT가 무시됨(`/proc/13464/status` SigIgn `0000000001001007`)을 확인했다. 첫 SIGINT 후40초 종료 대기는 실패했고 앱은 계속 실행됐다. 이는 `test_harness_artifact`로 분리한다. 이후 capture가 종료되어 카탈로그 상태이며 through_sequence0임을 확인한 뒤 해당 PID에만 SIGTERM으로 종료했다. exit=-15이므로 정상 graceful shutdown PASS가 아니다. 2차 launcher는 자식 실행 전 부모의 SIGINT handler를 복원하여 자식이 SIGINT 무시를 상속하지 않도록 했다. production source 변경은 없다.

2차 run: `/home/user/ASL_OCR_PI/runtime/production-demo-20260915-r2`. 별도 config `config/device-app.stm-capture-round2-20260915.toml`, SHA256 `16742b412a125541f991a10afce55ca043d66ba9aeb1f0cd51f4590412ea62c3`. 원본 config를 보존하고 parsed config 및 effective policy를 비교하여 **opaque_footer_identity.max_collection_ms만8000→45000**임을 assert했다. N5/K_same1/K_different0, camera request timeout, auth/TLS/해상도, 나머지 scanner 조건과 state 경로는 동일하다. 45초는 약27초의 무누락 수집에 일부 누락 여유를 주는 bounded trial이며 검증된 production 기본값이 아니다.

2차 production PID14182/supervisor14180, initial-mode capture, 카탈로그 안내 재생 시작 확인. 미리보기03은 같은 실행을 계속 유지하며 samples307/최신4000×3000 heartbeat 확인. 2차에서는 카탈로그 끝의 정확한 항목명 **새 데이터팩 추가**를 선택하도록 안내한다. 날짜가 붙은 기존 데이터팩 제목과 구분한다. 새 데이터팩 확인 후26/27→첫 receipt→28/29→두 번째 receipt→CONFIRM LONG→fresh READY 절차를 수행한다. 첫 spread가 계속 보류되면2분 후 로그를 확인하며 이후 의존 단계는 미실행으로 기록한다.

근거: r1의 `capture-result.json`, `stdout-final.log`, `shutdown-limitation.json`, `exit.json`; r2의 `config-change.json`, `manifest.json`, production launcher. product source modification count0, runtime timeout field1개 변경 및 launcher signal 처리 보완.

## 2차 카메라 중단 후 동일 조건 재실행

후속 완료 결과: [2026-09-16 capture 로그 검토](PI4_PRODUCTION_CAPTURE_RESULT_20260916.md). 실제26/27·28/29·30/31 세 spread durable 수신과 새 READY revision1 게시를 확인했다. 세 번째는 사용자 페이지 넘김에 따른 추가 촬영이다. 조명 조정 및45초 조건의 성공이다. 이후 사용자가 새 데이터팩의 읽기 품질이 이전과 큰 차이 없고 모든 기능이 정상이라고 확인하여 실제 읽기 사용자 관측 PASS를 추가했다. 반복 재현성과 시연 부팅/전원 복구 검증은 남아 있다.

사용자가 시험 중 Android IP Camera 앱 중지로 연결이 끊긴 것으로 보고하고 재실행을 요청했다. r2 실제 로그는 `camera_unavailable` fatal, exit2(2026-09-15T14:51:45Z)를 기록했다. 같은 증상이 사용자 보고와 부합하나 구체적인 전송 오류 원인은 이 feedback만으로 더 좁히지 않는다. `scan_started` 대상은 새 `datapack-f0212a15aee24747b2f09558e991b7c6`; 로그상 spread_sent/datapack_saved 없음. r2 로그와 exit는 Desktop evidence에 복사하고 기존 데이터팩/상태를 보존했다.

새 run `/home/user/ASL_OCR_PI/runtime/production-demo-20260915-r2-retry1`에서 같은 launcher·45초 config를 사용한다. config SHA256은 `16742b412a125541f991a10afce55ca043d66ba9aeb1f0cd51f4590412ea62c3`로 동일. import 경로 재확인 및 catalog29개 조회 성공. Laptop preview03은 실제4000×3000 영상 samples457/최신 heartbeat로 회복된 것을 확인했으므로 별도 재시작하거나 camera 설정을 바꾸지 않았다. 카메라 중단으로 끊긴 r2를 45초 정책의 완료된 비교 시험으로 판정하지 않는다.
